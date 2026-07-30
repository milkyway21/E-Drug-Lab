"""Thin JSON-RPC / WebSocket client for `hermes serve` (tui_gateway).

Wire protocol matches Hermes desktop / shared JsonRpcGatewayClient:
  request  → {jsonrpc,id,method,params}
  response → {jsonrpc,id,result|error}
  event    → {jsonrpc,method:"event",params:{type,session_id,payload?}}

Does NOT import or modify vendor/hermes-agent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger(__name__)

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def serve_host() -> str:
    return os.environ.get("HERMES_SERVE_HOST", "127.0.0.1")


def serve_port() -> int:
    return _env_int("HERMES_SERVE_PORT", 9119)


def serve_token() -> str:
    """Resolve auth token at call time (not import time — BFF may bootstrap env later)."""
    return (
        os.environ.get("HERMES_SERVE_TOKEN")
        or os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN")
        or ""
    )


# Back-compat aliases (prefer serve_*() helpers for runtime reads).
HERMES_SERVE_HOST = serve_host()
HERMES_SERVE_PORT = serve_port()
HERMES_SERVE_TOKEN = serve_token()
# Full agent turn can be long; prompt.submit ACK is fast, completion is event-driven.
HERMES_SERVE_TURN_TIMEOUT = _env_int("HERMES_SERVE_TURN_TIMEOUT", 300)
HERMES_SERVE_CONNECT_TIMEOUT = _env_float("HERMES_SERVE_CONNECT_TIMEOUT", 8.0)


@dataclass
class ServeTurnResult:
    text: str = ""
    thinking: str = ""
    reasoning: str = ""
    tools: list[str] = field(default_factory=list)
    session_id: str | None = None
    stored_session_id: str | None = None
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


def serve_ws_url(host: str | None = None, port: int | None = None, token: str | None = None) -> str:
    h = host or serve_host()
    p = port if port is not None else serve_port()
    tok = token if token is not None else serve_token()
    base = f"ws://{h}:{p}/api/ws"
    if tok:
        return f"{base}?token={tok}"
    return base


class HermesServeRpcError(RuntimeError):
    pass


class HermesServeClient:
    """One-shot or multi-turn JSON-RPC client over hermes serve /api/ws."""

    def __init__(
        self,
        ws_url: str | None = None,
        turn_timeout: float | None = None,
        connect_timeout: float | None = None,
    ) -> None:
        self.ws_url = ws_url or serve_ws_url()
        self.turn_timeout = float(
            turn_timeout if turn_timeout is not None else _env_int("HERMES_SERVE_TURN_TIMEOUT", 300)
        )
        self.connect_timeout = float(
            connect_timeout
            if connect_timeout is not None
            else _env_float("HERMES_SERVE_CONNECT_TIMEOUT", 8.0)
        )
        self._ws: Any = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False

    def _rid(self) -> int:
        self._next_id += 1
        return self._next_id

    async def connect(self) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise HermesServeRpcError(
                "websockets package missing (uvicorn[standard] should provide it)"
            ) from exc

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    open_timeout=self.connect_timeout,
                    max_size=8 * 1024 * 1024,
                ),
                timeout=self.connect_timeout + 1,
            )
        except Exception as exc:
            raise HermesServeRpcError(f"Scientist 服务连接失败: {exc}") from exc

        self._closed = False
        self._reader_task = asyncio.create_task(self._read_loop())

        # Wait briefly for gateway.ready (optional)
        try:
            await asyncio.wait_for(self._await_ready(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.debug("hermes serve: no gateway.ready within 3s; continuing")

    async def _await_ready(self) -> None:
        while True:
            evt = await self._event_queue.get()
            if evt.get("type") == "gateway.ready":
                return
            # re-queue unrelated early events
            await self._event_queue.put(evt)
            await asyncio.sleep(0.01)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if self._closed:
                    break
                try:
                    frame = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
                except (TypeError, json.JSONDecodeError):
                    continue
                rid = frame.get("id")
                if rid is not None and rid in self._pending:
                    fut = self._pending.pop(rid)
                    if not fut.done():
                        if frame.get("error"):
                            err = frame["error"]
                            msg = err.get("message") if isinstance(err, dict) else str(err)
                            fut.set_exception(HermesServeRpcError(msg or "RPC error"))
                        else:
                            fut.set_result(frame.get("result"))
                    continue
                if frame.get("method") == "event" and isinstance(frame.get("params"), dict):
                    await self._event_queue.put(frame["params"])
        except Exception as exc:
            logger.debug("hermes serve read loop ended: %s", exc)
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(HermesServeRpcError(f"WS closed: {exc}"))
            self._pending.clear()
        finally:
            self._closed = True

    async def request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0) -> Any:
        if self._ws is None or self._closed:
            raise HermesServeRpcError("not connected")
        rid = self._rid()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[rid] = fut
        payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(payload, ensure_ascii=False))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(rid, None)
            raise HermesServeRpcError(f"RPC timeout: {method}") from exc

    async def close(self) -> None:
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def create_or_resume_session(
        self,
        *,
        resume_stored_id: str | None = None,
        title: str = "edrug-float",
        cwd: str | None = None,
    ) -> tuple[str, str | None]:
        """Return (live_session_id, stored_session_id)."""
        if resume_stored_id:
            try:
                result = await self.request(
                    "session.resume",
                    {"session_id": resume_stored_id},
                    timeout=60.0,
                )
                sid = (result or {}).get("session_id") or resume_stored_id
                stored = (result or {}).get("stored_session_id") or resume_stored_id
                return str(sid), str(stored) if stored else None
            except HermesServeRpcError as exc:
                logger.info("session.resume failed (%s); creating new session", exc)

        params: dict[str, Any] = {"title": title, "source": "api"}
        if cwd:
            params["cwd"] = cwd
        result = await self.request("session.create", params, timeout=60.0)
        sid = (result or {}).get("session_id")
        stored = (result or {}).get("stored_session_id")
        if not sid:
            raise HermesServeRpcError("session.create returned no session_id")
        return str(sid), str(stored) if stored else None

    async def submit_and_collect(
        self,
        session_id: str,
        text: str,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> ServeTurnResult:
        """Fire prompt.submit and collect until message.complete / error."""
        out = ServeTurnResult(session_id=session_id)
        await self.request(
            "prompt.submit",
            {"session_id": session_id, "text": text},
            timeout=min(30.0, self.turn_timeout),
        )

        deadline = asyncio.get_running_loop().time() + self.turn_timeout
        reply_parts: list[str] = []
        think_parts: list[str] = []

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                out.error = f"Scientist 服务超时（{self.turn_timeout}s）"
                break
            try:
                evt = await asyncio.wait_for(self._event_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                out.error = f"Scientist 服务超时（{self.turn_timeout}s）"
                break

            etype = evt.get("type") or ""
            payload = evt.get("payload") if isinstance(evt.get("payload"), dict) else {}
            sid = evt.get("session_id")
            if sid and sid != session_id and etype not in {"gateway.ready", "error"}:
                # Ignore events for other sessions on this socket
                continue

            mapped = _map_gateway_event(etype, payload)
            if mapped:
                out.events.append(mapped)
                if on_event:
                    on_event(mapped)

            if etype in {"message.delta", "message.interim"}:
                chunk = str(payload.get("text") or "")
                if chunk:
                    reply_parts.append(chunk)
            elif etype in {"thinking.delta", "reasoning.delta"}:
                chunk = str(payload.get("text") or "")
                if chunk:
                    think_parts.append(chunk)
            elif etype == "tool.start":
                name = str(payload.get("name") or payload.get("tool") or "tool")
                out.tools.append(f"▶ {name}")
            elif etype == "tool.complete":
                name = str(payload.get("name") or payload.get("tool") or "tool")
                out.tools.append(f"✓ {name}")
            elif etype == "message.complete":
                final = str(payload.get("text") or "").strip()
                if final:
                    out.text = final
                elif reply_parts:
                    out.text = "".join(reply_parts).strip()
                reasoning = payload.get("reasoning")
                if isinstance(reasoning, str) and reasoning.strip():
                    out.reasoning = reasoning.strip()
                if think_parts:
                    out.thinking = "".join(think_parts).strip()
                elif out.reasoning:
                    out.thinking = out.reasoning
                status = payload.get("status")
                if status == "error" and not out.error:
                    out.error = out.text or "Hermes turn error"
                break
            elif etype == "error":
                out.error = str(payload.get("message") or "Hermes error")
                break

        if not out.text and reply_parts and not out.error:
            out.text = "".join(reply_parts).strip()
        if not out.thinking and think_parts:
            out.thinking = "".join(think_parts).strip()
        return out


def _map_gateway_event(etype: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if etype in {"message.delta", "message.interim"}:
        text = str(payload.get("text") or "")
        return {"type": "delta", "text": text} if text else None
    if etype in {"thinking.delta", "reasoning.delta"}:
        text = str(payload.get("text") or "")
        return {"type": "thinking", "text": text} if text else None
    if etype == "tool.start":
        name = str(payload.get("name") or payload.get("tool") or "tool")
        return {"type": "tool", "text": f"▶ {name}", "name": name, "status": "start"}
    if etype == "tool.progress":
        name = str(payload.get("name") or payload.get("tool") or "tool")
        detail = str(payload.get("message") or payload.get("text") or "")
        return {
            "type": "tool",
            "text": f"… {name}" + (f" {detail}" if detail else ""),
            "name": name,
            "status": "progress",
        }
    if etype == "tool.complete":
        name = str(payload.get("name") or payload.get("tool") or "tool")
        return {"type": "tool", "text": f"✓ {name}", "name": name, "status": "complete"}
    return None


async def run_serve_turn(
    prompt: str,
    *,
    resume_stored_id: str | None = None,
    cwd: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> ServeTurnResult:
    """Connect → create/resume session → submit prompt → collect → close."""
    if not serve_token():
        # Without a shared token, WS auth will fail on default hermes serve.
        # Caller should fall back to live-cli.
        raise HermesServeRpcError(
            "HERMES_SERVE_TOKEN / HERMES_DASHBOARD_SESSION_TOKEN not set "
            "(required for /api/ws auth)"
        )

    client = HermesServeClient()
    try:
        await client.connect()
        live_sid, stored = await client.create_or_resume_session(
            resume_stored_id=resume_stored_id,
            cwd=cwd,
        )
        result = await client.submit_and_collect(live_sid, prompt, on_event=on_event)
        result.session_id = live_sid
        result.stored_session_id = stored
        return result
    finally:
        await client.close()


async def iter_serve_turn_events(
    prompt: str,
    *,
    resume_stored_id: str | None = None,
    cwd: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield mapped stream events, then a final result event."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def _on_event(evt: dict[str, Any]) -> None:
        queue.put_nowait(evt)

    async def _runner() -> None:
        try:
            result = await run_serve_turn(
                prompt,
                resume_stored_id=resume_stored_id,
                cwd=cwd,
                on_event=_on_event,
            )
            queue.put_nowait(
                {
                    "type": "_result",
                    "result": result,
                }
            )
        except Exception as exc:
            queue.put_nowait({"type": "error", "message": str(exc)})
            queue.put_nowait(None)
        else:
            queue.put_nowait(None)

    task = asyncio.create_task(_runner())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
