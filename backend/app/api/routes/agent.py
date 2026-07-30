"""Agent BFF — session / chat / memory / UI command bus."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import hermes_gateway as gw

router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


class SessionCreate(BaseModel):
    target_id: str = Field(default="_unset_")


class SessionRetarget(BaseModel):
    target_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    page_path: str | None = None


class UiCommandPost(BaseModel):
    session_id: str = "default"
    type: str
    path: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    molecule_id: str | None = None
    smiles: str | None = None
    target_id: str | None = None
    name: str | None = None
    api_path: str | None = None
    body: dict[str, Any] | None = None


@router.get("/targets")
async def list_agent_targets() -> dict[str, Any]:
    return {"status": "ok", "targets": gw.list_memory_targets()}


@router.get("/bridge")
async def bridge_status() -> dict[str, Any]:
    serve_up = gw._probe_hermes_serve()
    return {
        "status": "ok",
        "bridge_mode": gw.resolve_bridge_mode(),
        "last_bridge_mode": gw.get_last_bridge_mode(),
        "hermes_serve": serve_up,
        "hermes_cli": gw.HERMES_BIN.is_file(),
        "serve_token": gw._serve_token_configured(),
        "reachable": gw.hermes_reachable(),
    }


@router.post("/session")
async def create_session(body: SessionCreate) -> dict[str, Any]:
    session = gw.create_session(body.target_id)
    return {"status": "ok", "session": session.to_dict()}


@router.get("/session/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = gw.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"status": "ok", "session": session.to_dict()}


@router.post("/session/{session_id}/retarget")
async def retarget_session(session_id: str, body: SessionRetarget) -> dict[str, Any]:
    session = gw.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    session = gw.retarget_session(session, body.target_id)
    return {"status": "ok", "session": session.to_dict()}


@router.post("/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    session = gw.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    payload = await asyncio.to_thread(
        gw.generate_reply_ui, session, body.message, body.page_path
    )
    status = "offline" if payload.get("offline") else "ok"
    return {
        "status": status,
        "reply": payload.get("reply") or "",
        "thinking": payload.get("thinking") or "",
        "error": payload.get("error") or "",
        "session_id": body.session_id,
        "target_id": session.target_id,
        "bridge_mode": payload.get("bridge_mode") or gw.get_last_bridge_mode(),
    }


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    session = gw.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    async def event_gen():
        async for evt in gw.stream_reply_events(session, body.message, body.page_path):
            # Normalize to typed SSE payload; keep legacy delta/done keys for older clients.
            out: dict[str, Any] = dict(evt)
            t = evt.get("type")
            if t == "delta" and "delta" not in out and evt.get("text"):
                out["delta"] = evt["text"]
            if t == "done":
                out["done"] = True
            yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/memory/{target_id}")
async def memory_preview(target_id: str) -> dict[str, Any]:
    return {"status": "ok", **gw.read_memory_preview(target_id)}


@router.get("/ui-commands/{session_id}")
async def ui_commands(session_id: str, since_id: str | None = None) -> dict[str, Any]:
    cmds = gw.get_ui_commands(session_id, since_id=since_id)
    return {"status": "ok", "commands": cmds}


@router.post("/ui-commands")
async def post_ui_command(body: UiCommandPost) -> dict[str, Any]:
    import sys
    from pathlib import Path

    scientist_src = Path("/data/ye/e-drug-lab/Scientist_In_E-Drug-Lab/src")
    s = str(scientist_src)
    if s not in sys.path:
        sys.path.insert(0, s)
    from masld_agent.ui_command_bus import (
        ui_highlight,
        ui_navigate,
        ui_open_molecule,
        ui_set_target,
        ui_start_task,
    )

    sid = body.session_id
    if body.type == "navigate" and body.path:
        result = ui_navigate(sid, body.path)
    elif body.type == "highlight" and body.entity_type and body.entity_id:
        result = ui_highlight(sid, body.entity_type, body.entity_id)
    elif body.type == "open_molecule" and body.molecule_id:
        result = ui_open_molecule(sid, body.molecule_id, body.smiles)
    elif body.type == "set_target" and body.target_id:
        result = ui_set_target(sid, body.target_id, body.name)
    elif body.type == "start_task" and body.api_path:
        result = ui_start_task(sid, body.api_path, body.body)
    else:
        raise HTTPException(status_code=400, detail="invalid ui command payload")
    return result
