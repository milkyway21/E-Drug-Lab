"""Agent BFF gateway — Scientist surface proxy + thin UI adapters.

Float window = E-Drug Lab Scientist chat UI surface. Main path transmits real
agent output via hermes serve JSON-RPC/WS (preferred) or recoverable CLI.
Never use empty stub echo 「【收到】…」 as the default brain. Offline = explicit
「E-Drug Lab Scientist 未连接」. Thin adapters only for target retarget + navigate.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.services import hermes_serve_rpc as serve_rpc

logger = logging.getLogger(__name__)

SCIENTIST_ROOT = Path("/data/ye/e-drug-lab/Scientist_In_E-Drug-Lab")
MEMORY_ROOT = SCIENTIST_ROOT / "memory"
HERMES_BIN = SCIENTIST_ROOT / ".venv" / "bin" / "hermes"
HERMES_HOME = SCIENTIST_ROOT / ".hermes"
BACKEND_ROOT = Path(__file__).resolve().parents[2]

HERMES_SERVE_HOST = os.environ.get("HERMES_SERVE_HOST", "127.0.0.1")
HERMES_SERVE_PORT = int(os.environ.get("HERMES_SERVE_PORT", "9119"))
# Recoverable CLI turn — short timeouts caused false offline (agent+tools often >120s).
HERMES_CHAT_TIMEOUT = int(os.environ.get("HERMES_CHAT_TIMEOUT", "300"))

BridgeMode = Literal["live-serve", "live-cli", "ui-intent", "offline"]

OFFLINE_MESSAGE = (
    "卡点：环境（Scientist / hermes serve 未连通）。\n"
    "需要人类：① 在 Scientist 目录启动 hermes serve；② 提供与 BFF 一致的 token。\n"
    "  cd /data/ye/e-drug-lab/Scientist_In_E-Drug-Lab && source .venv/bin/activate\n"
    "  export HERMES_DASHBOARD_SESSION_TOKEN=${HERMES_DASHBOARD_SESSION_TOKEN:-edrug-local}\n"
    "  HERMES_HOME=$PWD/.hermes hermes serve --skip-build --host 127.0.0.1 --port 9119\n"
    "BFF 环境变量：HERMES_SERVE_TOKEN / HERMES_DASHBOARD_SESSION_TOKEN（须与上相同）。\n"
    "或使用可恢复 CLI：`scientist chat`（BFF 会走 live-cli）。"
)

_sessions: dict[str, dict[str, Any]] = {}
_last_bridge_mode: BridgeMode = "offline"
_BRIDGE_TOKEN_KEYS = (
    "HERMES_DASHBOARD_SESSION_TOKEN",
    "HERMES_SERVE_TOKEN",
    "HERMES_CHAT_TIMEOUT",
    "HERMES_SERVE_TURN_TIMEOUT",
    "HERMES_SERVE_HOST",
    "HERMES_SERVE_PORT",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
            val = val[1:-1]
        out[key] = val
    return out


def _bootstrap_bridge_env() -> None:
    """Load Scientist/BFF dotenv into process env for serve token + CLI secrets.

    Pydantic only maps known Settings fields from backend .env — HERMES_* never
    reached os.environ, so live-serve always skipped (empty token) and CLI relied
    solely on hermes reading $HERMES_HOME/.env itself.
    """
    for path in (HERMES_HOME / ".env", SCIENTIST_ROOT / ".env"):
        for key, val in _parse_env_file(path).items():
            os.environ.setdefault(key, val)
    for key, val in _parse_env_file(BACKEND_ROOT / ".env").items():
        if key.startswith("HERMES_") or key in _BRIDGE_TOKEN_KEYS:
            os.environ.setdefault(key, val)
    # Local lab default — matches hermes_integration.md
    os.environ.setdefault("HERMES_DASHBOARD_SESSION_TOKEN", "edrug-local")
    os.environ.setdefault(
        "HERMES_SERVE_TOKEN",
        os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN", "edrug-local"),
    )


_bootstrap_bridge_env()
# Refresh module-level timeout after bootstrap (env may have HERMES_CHAT_TIMEOUT).
try:
    HERMES_CHAT_TIMEOUT = int(os.environ.get("HERMES_CHAT_TIMEOUT", str(HERMES_CHAT_TIMEOUT)))
except ValueError:
    pass


class HermesOfflineError(RuntimeError):
    """Raised when Hermes is unreachable; callers must surface offline, never stub."""

    def __init__(self, message: str = OFFLINE_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class AgentSession:
    id: str
    target_id: str
    created_at: str
    messages: list[ChatMessage] = field(default_factory=list)
    context_summary: str = ""
    hermes_session_id: str | None = None  # CLI resume id / serve stored_session_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "created_at": self.created_at,
            "message_count": len(self.messages),
            "context_summary": self.context_summary,
            "hermes_session_id": self.hermes_session_id,
        }


def get_last_bridge_mode() -> BridgeMode:
    return _last_bridge_mode


def _read_excerpt(path: Path, max_chars: int = 4000) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars]


def _load_campaign_excerpt(target_id: str, max_chars: int = 4000) -> str:
    return _read_excerpt(MEMORY_ROOT / "targets" / target_id / "CAMPAIGN.md", max_chars)


def _load_global_history_excerpt(max_chars: int = 2000) -> str:
    return _read_excerpt(MEMORY_ROOT / "GLOBAL_HISTORY.md", max_chars)


def _load_playbook_excerpt(max_chars: int = 6000) -> str:
    return _read_excerpt(MEMORY_ROOT / "MAIN_PLAYBOOK.md", max_chars)


def _playbook_toc(max_chars: int = 1200) -> str:
    raw = _load_playbook_excerpt(12000)
    if not raw:
        return "(MAIN_PLAYBOOK missing)"
    lines = []
    for ln in raw.splitlines():
        if ln.startswith("## ") or ln.startswith("| H") or "`funnel-" in ln:
            lines.append(ln)
        if sum(len(x) + 1 for x in lines) >= max_chars:
            break
    return "\n".join(lines)[:max_chars] or raw[:max_chars]


def _is_unset_target(target_id: str | None) -> bool:
    t = (target_id or "").strip()
    return t in {"", "_unset_", "unset", "none", "null"}


def _build_memory_context(target_id: str) -> str:
    if _is_unset_target(target_id):
        return (
            "[Memory] target=_unset_\n"
            "未加载任务状态（CAMPAIGN.md）。请先在悬浮窗选择靶点，再推进漏斗阶段。"
            f" MAIN_PLAYBOOK 路径：{MEMORY_ROOT / 'MAIN_PLAYBOOK.md'}（按需读取）。"
            " 对用户说「任务」，不要说「战役」。"
        )
    global_hist = _load_global_history_excerpt(800)
    campaign = _load_campaign_excerpt(target_id, max_chars=800)
    toc = _playbook_toc(1000)
    return "\n".join(
        [
            f"[Memory loaded] target={target_id}",
            f"任务状态文件 CAMPAIGN.md: {MEMORY_ROOT / 'targets' / target_id / 'CAMPAIGN.md'}",
            "--- 任务状态 CAMPAIGN excerpt (≤800) ---",
            campaign or "(missing — may be a new target)",
            "--- GLOBAL_HISTORY excerpt ---",
            global_hist or "(empty)",
            "--- MAIN_PLAYBOOK TOC (full file via campaign_memory tools) ---",
            toc,
            "runtime memory_enabled=false; use campaign_memory_* for structured writes.",
            "对用户说「任务」，不要说「战役」（内部 ID/文件名保持 CAMPAIGN / campaign_memory_*）。",
        ]
    )


def create_session(target_id: str = "_unset_") -> AgentSession:
    tid = (target_id or "").strip() or "_unset_"
    sid = str(uuid.uuid4())
    ctx = _build_memory_context(tid)
    session = AgentSession(
        id=sid,
        target_id=tid,
        created_at=datetime.now(timezone.utc).isoformat(),
        context_summary=ctx,
    )
    _sessions[sid] = session.__dict__
    _sessions[sid]["_obj"] = session
    return session


def get_session(session_id: str) -> AgentSession | None:
    raw = _sessions.get(session_id)
    if not raw:
        return None
    obj = raw.get("_obj")
    if isinstance(obj, AgentSession):
        return obj
    return None


def read_memory_preview(target_id: str) -> dict[str, Any]:
    base = MEMORY_ROOT / "targets" / target_id
    campaign_path = base / "CAMPAIGN.md"
    decisions_path = base / "DECISIONS.jsonl"
    out: dict[str, Any] = {
        "target_id": target_id,
        "main_playbook": str(MEMORY_ROOT / "MAIN_PLAYBOOK.md"),
        "global_history": str(MEMORY_ROOT / "GLOBAL_HISTORY.md"),
        "campaign_exists": campaign_path.is_file(),
        "bridge_mode": _last_bridge_mode,
    }
    if campaign_path.is_file():
        out["campaign"] = campaign_path.read_text(encoding="utf-8")
    if decisions_path.is_file():
        lines = [ln for ln in decisions_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        out["decisions_tail"] = lines[-10:]
    return out


def _hermes_env() -> dict[str, str]:
    """Subprocess env for `hermes chat`: HERMES_HOME + Scientist secrets + venv PATH.

    Credentials come only from process env / local gitignored `.env` files.
    Do not hardcode third-party relay URLs or read host auth stores here.
    """
    env = dict(os.environ)
    for path in (HERMES_HOME / ".env", SCIENTIST_ROOT / ".env"):
        for key, val in _parse_env_file(path).items():
            env.setdefault(key, val)
    env["HERMES_HOME"] = str(HERMES_HOME)
    src = str(SCIENTIST_ROOT / "src")
    prev_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{prev_pp}" if prev_pp else src
    venv_bin = str(SCIENTIST_ROOT / ".venv" / "bin")
    env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def _serve_token_configured() -> bool:
    return bool(
        os.environ.get("HERMES_SERVE_TOKEN")
        or os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN")
    )


def resolve_bridge_mode() -> BridgeMode:
    """Prospective bridge capability (not sticky last-failure offline)."""
    last = _last_bridge_mode
    if last in {"live-serve", "live-cli", "ui-intent"}:
        return last
    if _probe_hermes_serve() and _serve_token_configured():
        return "live-serve"
    if HERMES_BIN.is_file():
        return "live-cli"
    return "offline"


def _is_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_hermes_serve() -> bool:
    if not _is_port_open(HERMES_SERVE_HOST, HERMES_SERVE_PORT):
        return False
    for path in ("/api/status", "/api/health", "/api/sessions/stats", "/"):
        try:
            req = Request(f"http://{HERMES_SERVE_HOST}:{HERMES_SERVE_PORT}{path}", method="GET")
            with urlopen(req, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except (URLError, OSError, TimeoutError):
            continue
    return False


def hermes_reachable() -> bool:
    """True if serve is up or hermes CLI binary exists (live-cli possible)."""
    if _probe_hermes_serve():
        return True
    return HERMES_BIN.is_file()


def _build_chat_prompt(
    user_message: str,
    target_id: str,
    context: str,
    page_path: str | None = None,
) -> str:
    """Inject page/target as context prefix — not as mechanical stub body."""
    page = page_path or "/"
    return (
        f"{context}\n\n"
        f"[UI context] page_path={page} target_id={target_id}\n"
        f"--- User ---\n{user_message}\n\n"
        "Output rules (mandatory):\n"
        "1) Put any private reasoning inside <thinking>...</thinking> only.\n"
        "2) After </thinking>, write ONLY the user-facing answer in Chinese.\n"
        "3) Do NOT narrate planning in English outside <thinking>.\n"
        "4) Do NOT repeat the same paragraph twice.\n"
        "5) If target_id is _unset_, ask user to select a target before funnel steps."
    )


# ── Thinking / reply split (Hermes-mapped UI) ──────────────────────────

_THINK_TAG_RE = re.compile(
    r"<thinking>(.*?)</thinking>|<think>(.*?)</think>",
    re.DOTALL | re.IGNORECASE,
)
_THINKING_LINE_RE = re.compile(
    r"^(The user said|I will |I'll |Let me |I've |I need to |Looking at |"
    r"已明确|接下来将|我将|我需要)"
)


def _dedupe_paragraphs(text: str) -> str:
    parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    out: list[str] = []
    for p in parts:
        if out and out[-1] == p:
            continue
        if out and p in out[-1] and len(p) > 40:
            continue
        out.append(p)
    joined = "\n\n".join(out)
    half = len(joined) // 2
    if half > 80 and joined[:half].strip() == joined[half:].strip():
        return joined[:half].strip()
    return joined


def split_thinking_and_reply(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if not text:
        return "", ""

    thinking_chunks: list[str] = []
    for m in _THINK_TAG_RE.finditer(text):
        thinking_chunks.append((m.group(1) or m.group(2) or "").strip())
    without_tags = _THINK_TAG_RE.sub("", text).strip()
    without_tags = _dedupe_paragraphs(without_tags)

    lines = without_tags.splitlines()
    think_lines: list[str] = []
    reply_lines: list[str] = []
    saw_reply = False
    for line in lines:
        stripped = line.strip()
        if not saw_reply and (
            _THINKING_LINE_RE.match(stripped)
            or (stripped.startswith("The user") and "respond" in stripped.lower())
        ):
            think_lines.append(line)
            continue
        if not saw_reply and think_lines and stripped and not _THINKING_LINE_RE.match(stripped):
            saw_reply = True
        if saw_reply or not think_lines:
            reply_lines.append(line)
        else:
            think_lines.append(line)

    thinking = "\n".join(thinking_chunks + think_lines).strip()
    reply = "\n".join(reply_lines).strip() if reply_lines else without_tags
    reply = _dedupe_paragraphs(reply)
    for marker in ("你好。", "你好！", "好的。", "当前靶点"):
        idx = reply.find(marker)
        if idx > 20:
            thinking = (thinking + "\n" + reply[:idx]).strip()
            reply = reply[idx:].strip()
            break
    return thinking, reply


def list_memory_targets() -> list[str]:
    root = MEMORY_ROOT / "targets"
    if not root.is_dir():
        return ["HSD17B13"]
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    return names or ["HSD17B13"]


def retarget_session(session: AgentSession, target_id: str) -> AgentSession:
    target_id = _normalize_target_id(target_id) or "HSD17B13"
    session.target_id = target_id
    session.context_summary = _build_memory_context(target_id)
    # Keep hermes_session_id so conversation continues; context is re-injected per prompt.
    return session


def _normalize_target_id(raw: str | None) -> str | None:
    if not raw:
        return None
    t = raw.strip()
    if not t:
        return None
    aliases = {
        "hsd": "HSD17B13",
        "hsd17b13": "HSD17B13",
        "8g9v": "HSD17B13",
        "8G9V": "HSD17B13",
    }
    key = t.lower()
    if key in aliases:
        return aliases[key]
    # Preserve known casing for listed targets
    for name in list_memory_targets():
        if name.lower() == key:
            return name
    return t.upper() if t.isalnum() or re.match(r"^[A-Za-z0-9_-]+$", t) else t


# ── Thin UI adapters (nav + target) — never replace Hermes answers ─────

_NAV_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(打开|跳转|进入|去|前往).*(workflow|工作流|流水线)", re.I), "/workflow"),
    (re.compile(r"(去工作流|打开流水线|打开工作流|进入流水线)", re.I), "/workflow"),
    (re.compile(r"(打开|跳转|进入|去|前往).*(database|数据库|分子库)", re.I), "/database"),
    (re.compile(r"(去数据库|打开数据库)", re.I), "/database"),
    (re.compile(r"(打开|跳转|进入|去|前往).*(records|记录|运行记录)", re.I), "/records"),
    (re.compile(r"(打开|跳转|进入|去|前往).*(models|模型|工具页)", re.I), "/models"),
    (re.compile(r"(打开|跳转|进入|去|前往).*(docs|文档)", re.I), "/docs"),
    (re.compile(r"(打开|跳转|进入|去|前往).*(首页|home)", re.I), "/"),
]

_TARGET_INTENT_RE = re.compile(
    r"(?:选择|切换|绑定|用|选)\s*(?:靶点\s*)?"
    r"(HSD17B13|HSD|hsd|8G9V|8g9v|[A-Za-z][A-Za-z0-9_-]{1,31})",
    re.I,
)
_TARGET_INTENT_RE2 = re.compile(
    r"(切换靶点|绑定靶点|选择靶点|切换到|绑定到)\s*"
    r"(HSD17B13|HSD|hsd|8G9V|8g9v|[A-Za-z][A-Za-z0-9_-]{1,31})",
    re.I,
)


def _extract_target_intent(user_message: str) -> str | None:
    msg = user_message.strip()
    for pattern in (_TARGET_INTENT_RE2, _TARGET_INTENT_RE):
        m = pattern.search(msg)
        if m:
            return _normalize_target_id(m.group(m.lastindex or 1))
    return None


def _maybe_enqueue_ui_intents(session: AgentSession, user_message: str) -> list[str]:
    scientist_src = str(SCIENTIST_ROOT / "src")
    if scientist_src not in sys.path:
        sys.path.insert(0, scientist_src)
    try:
        from masld_agent.ui_command_bus import ui_navigate, ui_set_target
    except ImportError:
        return []

    acks: list[str] = []
    msg = user_message.strip()

    for pattern, path in _NAV_INTENT_PATTERNS:
        if pattern.search(msg):
            result = ui_navigate(session.id, path)
            if result.get("status") == "ok":
                acks.append(f"已入队 navigate → {path}")
            break

    target_id = _extract_target_intent(msg)
    if target_id:
        result = ui_set_target(session.id, target_id)
        if result.get("status") == "ok":
            acks.append(f"已入队 set_target → {target_id}")

    return acks


def _is_pure_ui_intent(user_message: str) -> bool:
    """True when message is primarily navigate/set_target (thin ack OK)."""
    msg = user_message.strip()
    if len(msg) > 80:
        return False
    has_nav = any(p.search(msg) for p, _ in _NAV_INTENT_PATTERNS)
    has_target = _extract_target_intent(msg) is not None
    if not (has_nav or has_target):
        return False
    # Extra campaign question words → not pure UI
    if any(k in msg for k in ("怎么", "如何", "为什么", "阶段", "漏斗", "playbook", "推进", "完成")):
        return False
    return True


def _thin_ui_ack(session: AgentSession, user_message: str, acks: list[str]) -> str:
    """Short ack for pure nav/target — not a campaign stub brain."""
    parts: list[str] = []
    msg = user_message.strip()
    for pattern, path in _NAV_INTENT_PATTERNS:
        if pattern.search(msg):
            parts.append(f"已理解导航意图，UI 命令已入队 → `{path}`。")
            break
    tid = _extract_target_intent(msg)
    if tid:
        parts.append(f"已切换研究靶标 → **{tid}**（BFF session 已同步）。")
    if not parts:
        parts.append("已处理界面意图。")
    if acks:
        parts.append("\n".join(f"✓ {a}" for a in acks))
    return "\n".join(parts)


# ── Hermes live bridges ────────────────────────────────────────────────

def _parse_hermes_cli_output(stdout: str) -> tuple[str, str | None]:
    lines = stdout.splitlines()
    session_id: str | None = None
    body_lines: list[str] = []
    for line in lines:
        m = re.match(r"^session_id:\s*(\S+)", line.strip())
        if m:
            session_id = m.group(1)
            continue
        if line.strip() in {"OK", ""}:
            continue
        if line.startswith("┌─") or line.startswith("└─") or line.startswith("│"):
            continue
        body_lines.append(line)
    text = "\n".join(body_lines).strip()
    return text, session_id


def _try_hermes_cli(prompt: str, resume_session: str | None = None) -> tuple[str | None, str | None]:
    """Recoverable `hermes chat -Q` with --resume (not stub fallback)."""
    if not HERMES_BIN.is_file():
        return None, None
    provider = os.environ.get("HERMES_INFERENCE_PROVIDER", "openai-relay")
    model = os.environ.get("HERMES_INFERENCE_MODEL", "gpt-5.6-sol")
    cmd = [
        str(HERMES_BIN),
        "chat",
        "--source",
        "edrug-bff",
        "--accept-hooks",
        "--provider",
        provider,
        "-m",
        model,
    ]
    if resume_session:
        cmd.extend(["--resume", resume_session])
    cmd.extend(["-Q", "-q", prompt])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(SCIENTIST_ROOT),
            env=_hermes_env(),
            capture_output=True,
            text=True,
            timeout=HERMES_CHAT_TIMEOUT,
        )
        if proc.returncode != 0:
            logger.warning(
                "hermes chat failed rc=%s stderr=%s",
                proc.returncode,
                (proc.stderr or "")[:500],
            )
            return None, None
        reply, hermes_sid = _parse_hermes_cli_output(proc.stdout or "")
        if not reply:
            reply = (proc.stdout or "").strip() or None
        return reply, hermes_sid
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("hermes chat subprocess error: %s", exc)
        return None, None


async def _try_hermes_serve_turn(
    prompt: str,
    resume_stored_id: str | None = None,
) -> serve_rpc.ServeTurnResult | None:
    if not _probe_hermes_serve():
        return None
    if not _serve_token_configured():
        logger.info("hermes serve up but no shared token; skip WS, prefer live-cli")
        return None
    try:
        return await serve_rpc.run_serve_turn(
            prompt,
            resume_stored_id=resume_stored_id,
            cwd=str(SCIENTIST_ROOT),
        )
    except serve_rpc.HermesServeRpcError as exc:
        logger.warning("hermes serve turn failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("hermes serve unexpected error: %s", exc)
        return None


def _run_coro_sync(coro: Any) -> Any:
    """Run async coroutine from sync code (safe if a loop is already running)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Already inside an event loop — run in a fresh thread with its own loop.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _apply_target_from_message(session: AgentSession, user_message: str) -> str | None:
    """If chat retargets, update session before calling Hermes. Return new target or None."""
    tid = _extract_target_intent(user_message)
    if not tid:
        return None
    if session.target_id != tid:
        retarget_session(session, tid)
    return tid


def generate_reply(
    session: AgentSession,
    user_message: str,
    page_path: str | None = None,
) -> str:
    """Return raw assistant text. Raises HermesOfflineError when bridge is down."""
    global _last_bridge_mode
    session.messages.append(ChatMessage(role="user", content=user_message))

    # Sync target from chat intent before Hermes sees the prompt
    _apply_target_from_message(session, user_message)
    ui_acks = _maybe_enqueue_ui_intents(session, user_message)

    # Pure UI: thin ack only (does not claim to be Hermes campaign answers)
    if ui_acks and _is_pure_ui_intent(user_message):
        reply = _thin_ui_ack(session, user_message, ui_acks)
        _last_bridge_mode = "ui-intent"
        logger.info(
            "hermes_bridge mode=ui-intent target=%s session=%s",
            session.target_id,
            session.id,
        )
        session.messages.append(ChatMessage(role="assistant", content=reply))
        return reply

    prompt = _build_chat_prompt(
        user_message, session.target_id, session.context_summary, page_path=page_path
    )

    # Prefer hermes serve WS
    serve_result: serve_rpc.ServeTurnResult | None = None
    try:
        serve_result = _run_coro_sync(
            _try_hermes_serve_turn(prompt, resume_stored_id=session.hermes_session_id)
        )
    except Exception as exc:
        logger.debug("serve sync bridge failed: %s", exc)
        serve_result = None

    if serve_result and serve_result.text and not serve_result.error:
        reply = serve_result.text
        if serve_result.stored_session_id:
            session.hermes_session_id = serve_result.stored_session_id
        _last_bridge_mode = "live-serve"
        if ui_acks:
            reply = reply.rstrip() + "\n\n" + "\n".join(f"✓ {a}" for a in ui_acks)
        logger.info(
            "hermes_bridge mode=live-serve target=%s session=%s",
            session.target_id,
            session.id,
        )
        session.messages.append(ChatMessage(role="assistant", content=reply))
        return reply

    # Recoverable CLI
    hermes_reply, hermes_sid = _try_hermes_cli(prompt, resume_session=session.hermes_session_id)
    if hermes_reply:
        if hermes_sid:
            session.hermes_session_id = hermes_sid
        reply = hermes_reply
        _last_bridge_mode = "live-cli"
        if ui_acks:
            reply = reply.rstrip() + "\n\n" + "\n".join(f"✓ {a}" for a in ui_acks)
        logger.info(
            "hermes_bridge mode=live-cli target=%s session=%s",
            session.target_id,
            session.id,
        )
        session.messages.append(ChatMessage(role="assistant", content=reply))
        return reply

    _last_bridge_mode = "offline"
    logger.warning(
        "hermes_bridge mode=offline target=%s session=%s",
        session.target_id,
        session.id,
    )
    raise HermesOfflineError(OFFLINE_MESSAGE)


def generate_reply_ui(
    session: AgentSession,
    user_message: str,
    page_path: str | None = None,
) -> dict[str, Any]:
    try:
        raw = generate_reply(session, user_message, page_path=page_path)
    except HermesOfflineError as exc:
        return {
            "reply": "",
            "thinking": "",
            "raw": "",
            "error": exc.message,
            "offline": True,
            "bridge_mode": "offline",
            "target_id": session.target_id,
        }
    thinking, reply = split_thinking_and_reply(raw)
    return {
        "reply": reply or raw,
        "thinking": thinking,
        "raw": raw,
        "error": "",
        "offline": False,
        "bridge_mode": _last_bridge_mode,
        "target_id": session.target_id,
    }


async def stream_reply_events(
    session: AgentSession,
    user_message: str,
    page_path: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE-ready events: delta/thinking/tool/done/error (+ ui_command hints)."""
    global _last_bridge_mode

    session.messages.append(ChatMessage(role="user", content=user_message))
    _apply_target_from_message(session, user_message)
    ui_acks = _maybe_enqueue_ui_intents(session, user_message)

    if ui_acks and _is_pure_ui_intent(user_message):
        reply = _thin_ui_ack(session, user_message, ui_acks)
        _last_bridge_mode = "ui-intent"
        session.messages.append(ChatMessage(role="assistant", content=reply))
        yield {"type": "delta", "text": reply}
        for ack in ui_acks:
            if "navigate" in ack:
                m = re.search(r"→\s*(\S+)", ack)
                if m:
                    yield {"type": "ui_command", "command": "navigate", "path": m.group(1)}
            if "set_target" in ack:
                m = re.search(r"→\s*(\S+)", ack)
                if m:
                    yield {
                        "type": "ui_command",
                        "command": "set_target",
                        "target_id": m.group(1),
                    }
        yield {
            "type": "done",
            "bridge_mode": "ui-intent",
            "thinking": "",
            "target_id": session.target_id,
            "reply": reply,
        }
        return

    prompt = _build_chat_prompt(
        user_message, session.target_id, session.context_summary, page_path=page_path
    )

    # Prefer live-serve streaming
    if _probe_hermes_serve() and _serve_token_configured():
        try:
            streamed_text = ""
            streamed_thinking = ""
            final_text = ""
            final_thinking = ""
            serve_error: str | None = None
            stored_id: str | None = None
            async for item in serve_rpc.iter_serve_turn_events(
                prompt,
                resume_stored_id=session.hermes_session_id,
                cwd=str(SCIENTIST_ROOT),
            ):
                if item.get("type") == "_result":
                    result: serve_rpc.ServeTurnResult = item["result"]
                    final_text = result.text or streamed_text
                    final_thinking = (
                        result.thinking or result.reasoning or streamed_thinking
                    )
                    serve_error = result.error
                    stored_id = result.stored_session_id
                    continue
                if item.get("type") == "error":
                    serve_error = str(item.get("message") or "Scientist 服务错误")
                    continue
                yield item
                if item.get("type") == "delta" and item.get("text"):
                    streamed_text += str(item["text"])
                if item.get("type") == "thinking" and item.get("text"):
                    streamed_thinking += str(item["text"])

            body = final_text or streamed_text
            if body and not serve_error:
                if stored_id:
                    session.hermes_session_id = stored_id
                thinking, reply = split_thinking_and_reply(body)
                if not thinking and (final_thinking or streamed_thinking):
                    thinking = final_thinking or streamed_thinking
                if ui_acks:
                    suffix = "\n\n" + "\n".join(f"✓ {a}" for a in ui_acks)
                    reply = (reply or body).rstrip() + suffix
                    yield {"type": "delta", "text": suffix}
                _last_bridge_mode = "live-serve"
                session.messages.append(
                    ChatMessage(role="assistant", content=reply or body)
                )
                yield {
                    "type": "done",
                    "bridge_mode": "live-serve",
                    "thinking": thinking,
                    "target_id": session.target_id,
                    "reply": reply or body,
                }
                return
            logger.warning("hermes serve stream incomplete: %s", serve_error)
        except Exception as exc:
            logger.warning("hermes serve stream failed: %s", exc)

    # live-cli (recoverable -Q --resume)
    hermes_reply, hermes_sid = await asyncio.to_thread(
        _try_hermes_cli, prompt, session.hermes_session_id
    )
    if hermes_reply:
        if hermes_sid:
            session.hermes_session_id = hermes_sid
        thinking, reply = split_thinking_and_reply(hermes_reply)
        if ui_acks:
            reply = reply.rstrip() + "\n\n" + "\n".join(f"✓ {a}" for a in ui_acks)
        _last_bridge_mode = "live-cli"
        session.messages.append(ChatMessage(role="assistant", content=reply or hermes_reply))
        # Stream as chunks for UI parity
        chunk_size = 48
        body = reply or hermes_reply
        for i in range(0, len(body), chunk_size):
            yield {"type": "delta", "text": body[i : i + chunk_size]}
            await asyncio.sleep(0.01)
        if thinking:
            yield {"type": "thinking", "text": thinking}
        yield {
            "type": "done",
            "bridge_mode": "live-cli",
            "thinking": thinking,
            "target_id": session.target_id,
            "reply": body,
        }
        return

    _last_bridge_mode = "offline"
    yield {"type": "error", "message": OFFLINE_MESSAGE, "bridge_mode": "offline"}
    yield {
        "type": "done",
        "bridge_mode": "offline",
        "thinking": "",
        "target_id": session.target_id,
        "reply": "",
        "error": OFFLINE_MESSAGE,
    }


async def stream_reply_ui(
    session: AgentSession,
    user_message: str,
    page_path: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible: collect stream into one payload."""
    reply_parts: list[str] = []
    thinking_parts: list[str] = []
    error = ""
    bridge_mode: BridgeMode = "offline"
    async for evt in stream_reply_events(session, user_message, page_path):
        t = evt.get("type")
        if t == "delta" and evt.get("text"):
            reply_parts.append(str(evt["text"]))
        elif t == "thinking" and evt.get("text"):
            thinking_parts.append(str(evt["text"]))
        elif t == "error":
            error = str(evt.get("message") or OFFLINE_MESSAGE)
        elif t == "done":
            bridge_mode = evt.get("bridge_mode") or bridge_mode  # type: ignore[assignment]
            if evt.get("thinking"):
                thinking_parts = [str(evt["thinking"])]
            if evt.get("reply"):
                reply_parts = [str(evt["reply"])]
            if evt.get("error"):
                error = str(evt["error"])
    return {
        "reply": "".join(reply_parts),
        "thinking": "".join(thinking_parts) if len(thinking_parts) == 1 else "".join(thinking_parts),
        "raw": "".join(reply_parts),
        "error": error,
        "offline": bool(error) and bridge_mode == "offline",
        "bridge_mode": bridge_mode,
        "target_id": session.target_id,
    }


def get_ui_commands(session_id: str, since_id: str | None = None) -> list[dict[str, Any]]:
    scientist_src = str(SCIENTIST_ROOT / "src")
    if scientist_src not in sys.path:
        sys.path.insert(0, scientist_src)
    try:
        from masld_agent.ui_command_bus import drain_ui_commands

        return drain_ui_commands(session_id, since_id=since_id)
    except ImportError:
        return []
