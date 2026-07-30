"""Deterministic file-based campaign memory (no Hermes native memory toolset)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from masld_agent.paths import UnsafePathError, resolve_under

PKG_ROOT = Path(__file__).resolve().parents[2]
MEMORY_ROOT = PKG_ROOT / "memory"

ALLOWED_CAMPAIGN_KEYS = frozenset(
    {
        "current_stage",
        "workspace_root",
        "gpu_policy",
        "last_updated",
        "notes",
        "blocked_reason",
    }
)


def _memory_root() -> Path:
    return MEMORY_ROOT


def read_memory(
    *,
    target_id: str | None = None,
    section: str = "campaign",
    tail: int = 20,
) -> dict[str, Any]:
    root = _memory_root()
    section = (section or "campaign").lower()
    out: dict[str, Any] = {"status": "ok", "section": section}

    if section in ("playbook", "main", "main_playbook"):
        path = root / "MAIN_PLAYBOOK.md"
        out["path"] = str(path)
        out["content"] = path.read_text(encoding="utf-8") if path.is_file() else ""
        return out

    if section in ("global", "global_history"):
        path = root / "GLOBAL_HISTORY.md"
        out["path"] = str(path)
        out["content"] = path.read_text(encoding="utf-8") if path.is_file() else ""
        return out

    if not target_id:
        return {"status": "error", "error": "target_id required for campaign/decisions/session"}

    base = root / "targets" / target_id
    if section == "campaign":
        path = base / "CAMPAIGN.md"
        out["path"] = str(path)
        out["content"] = path.read_text(encoding="utf-8") if path.is_file() else ""
        return out

    if section == "decisions":
        path = base / "DECISIONS.jsonl"
        lines: list[str] = []
        if path.is_file():
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        out["path"] = str(path)
        out["lines"] = lines[-max(1, tail) :]
        return out

    if section == "session":
        path = base / "session.json"
        out["path"] = str(path)
        if path.is_file():
            out["data"] = json.loads(path.read_text(encoding="utf-8"))
        else:
            out["data"] = {}
        return out

    return {"status": "error", "error": f"unknown section: {section}"}


def write_campaign_field(
    *,
    target_id: str,
    field: str,
    value: str,
) -> dict[str, Any]:
    if field not in ALLOWED_CAMPAIGN_KEYS:
        return {
            "status": "error",
            "error": f"field not allowed: {field}",
            "allowed": sorted(ALLOWED_CAMPAIGN_KEYS),
        }
    base = _memory_root() / "targets" / target_id
    base.mkdir(parents=True, exist_ok=True)
    path = base / "CAMPAIGN.md"
    if not path.is_file():
        path.write_text(
            f"# CAMPAIGN — {target_id}\n\n> 编排：memory/MAIN_PLAYBOOK.md\n\n",
            encoding="utf-8",
        )
    text = path.read_text(encoding="utf-8")
    marker = f"| `{field}` |"
    new_line = f"| `{field}` | {value} |"
    if marker in text:
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if marker in ln and ln.strip().startswith("|"):
                lines[i] = new_line
                break
        text = "\n".join(lines) + "\n"
    else:
        if "## 元数据" not in text:
            text += "\n## 元数据\n\n| 字段 | 值 |\n|------|-----|\n"
        text += new_line + "\n"
    path.write_text(text, encoding="utf-8")
    return {"status": "ok", "path": str(path), "field": field, "value": value}


def append_decision(
    *,
    target_id: str,
    stage: str,
    decision: str,
    summary: str,
    evidence: str = "",
) -> dict[str, Any]:
    base = _memory_root() / "targets" / target_id
    base.mkdir(parents=True, exist_ok=True)
    path = base / "DECISIONS.jsonl"
    row = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "stage": stage,
        "decision": decision,
        "summary": summary,
        "evidence": evidence,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"status": "ok", "path": str(path), "row": row}


def append_global_history(line: str) -> dict[str, Any]:
    path = _memory_root() / "GLOBAL_HISTORY.md"
    if not path.is_file():
        return {"status": "error", "error": "GLOBAL_HISTORY.md missing"}
    text = path.read_text(encoding="utf-8")
    anchor = "## 任务摘要（新→旧）"
    if anchor not in text:
        return {"status": "error", "error": "GLOBAL_HISTORY anchor missing"}
    prefix, rest = text.split(anchor, 1)
    entry = f"- {line.strip()}\n"
    body = rest.lstrip("\n")
    if body.startswith("\n"):
        body = body[1:]
    new_text = prefix + anchor + "\n\n" + entry + body
    path.write_text(new_text, encoding="utf-8")
    return {"status": "ok", "path": str(path), "appended": line.strip()}


def update_session(target_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        base = resolve_under(_memory_root(), f"targets/{target_id}")
    except UnsafePathError as exc:
        return {"status": "error", "error": str(exc)}
    base.mkdir(parents=True, exist_ok=True)
    path = base / "session.json"
    data: dict[str, Any] = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.update(patch)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "ok", "path": str(path), "data": data}
