"""Agent tools: Schrödinger Desmond MD via e-drug-lab HTTP API (single semantics).

Prefer POST/GET http://127.0.0.1:8001/api/v1/affinity/md to avoid dual
implementations. Falls back to importing desmond_md_service only if HTTP fails.

Completion criteria
-------------------
- production PASS: cms + traj + md_summary + done flag
- dry_prep / smoke gate ≠ production PASS
- never treat stub / unavailable as success
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

PKG_ROOT = Path(__file__).resolve().parents[3]
MEMORY_ROOT = PKG_ROOT / "memory"
DEFAULT_API = os.environ.get("EDRUG_API_BASE", "http://127.0.0.1:8001").rstrip("/")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _md_jobs_path(target_id: Optional[str]) -> Path:
    tid = (target_id or "").strip() or "_unset_"
    d = MEMORY_ROOT / "targets" / tid
    d.mkdir(parents=True, exist_ok=True)
    return d / "MD_JOBS.jsonl"


def append_md_job(record: dict[str, Any], *, target_id: Optional[str] = None) -> str:
    path = _md_jobs_path(target_id)
    line = json.dumps({**record, "ts": record.get("ts") or _utc()}, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return str(path)


def _http_json(method: str, url: str, body: Optional[dict] = None, timeout: float = 60.0) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return {"status": "failed", "http_status": exc.code, "error": parsed, "message": str(parsed)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}", "message": str(exc)}


def _local_submit(**kwargs: Any) -> dict[str, Any]:
    """Fallback: import backend service directly."""
    try:
        from masld_agent.platform.edrug_bridge import ensure_backend_on_path

        ensure_backend_on_path()
        from app.services.desmond_md_service import submit_desmond_md  # type: ignore

        return submit_desmond_md(**kwargs)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "message": f"HTTP and local Desmond service unavailable: {exc}",
            "stub": False,
        }


def _local_status(task_id: str) -> dict[str, Any]:
    try:
        from masld_agent.platform.edrug_bridge import ensure_backend_on_path

        ensure_backend_on_path()
        from app.services.desmond_md_service import get_task  # type: ignore

        job = get_task(task_id)
        if not job:
            return {"status": "failed", "message": f"task not found: {task_id}"}
        return job
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "message": str(exc)}


def schrodinger_md_submit(
    *,
    structure_path: Optional[str] = None,
    mode: str = "dry_prep",
    confirm: bool = False,
    simulation_time_ns: Optional[float] = None,
    host: Optional[str] = None,
    molecule_id: Optional[str] = None,
    target_id: Optional[str] = None,
    api_base: Optional[str] = None,
) -> dict[str, Any]:
    """Submit / prepare Desmond MD. Default dry_prep; never treats stub as success."""
    mode = (mode or "dry_prep").strip().lower()
    tid = (target_id or "").strip() or None
    payload = {
        "structure_path": structure_path,
        "mode": mode,
        "confirm": bool(confirm),
        "simulation_time_ns": simulation_time_ns,
        "host": host,
        "molecule_id": molecule_id,
    }
    if tid is not None:
        payload["target_id"] = tid
    # Drop Nones for cleaner HTTP body
    body = {k: v for k, v in payload.items() if v is not None}

    base = (api_base or DEFAULT_API).rstrip("/")
    result = _http_json("POST", f"{base}/api/v1/affinity/md", body)
    via = "http"
    if result.get("status") in {None, "unavailable"} and "task_id" not in result:
        result = _local_submit(
            structure_path=structure_path,
            mode=mode,
            confirm=confirm,
            simulation_time_ns=simulation_time_ns,
            host=host,
            molecule_id=molecule_id,
            target_id=tid,
        )
        via = "local_service"

    # Normalize forbidden stub
    if result.get("status") == "stub" or result.get("stub") is True:
        result = {
            **result,
            "status": "failed",
            "message": result.get("message")
            or "Stub MD response is forbidden; use Desmond dry_prep/unavailable/gated.",
            "stub": False,
        }

    mem_target = tid or "_unset_"
    mem_path = append_md_job(
        {
            "event": "submit",
            "via": via,
            "task_id": result.get("task_id"),
            "status": result.get("status"),
            "mode": mode,
            "confirm": bool(confirm),
            "job_dir": result.get("job_dir"),
            "structure_path": structure_path,
            "message": result.get("message"),
            "completion_note": (
                "production PASS needs cms+traj+md_summary+done; "
                "smoke/dry_prep gate ≠ production"
            ),
        },
        target_id=mem_target,
    )
    return {
        **result,
        "tool": "schrodinger_md_submit",
        "via": via,
        "md_jobs_path": mem_path,
        "catalog_ids_used": ["sz.desmond", "ed.http.affinity"],
        "warnings": [
            "Never treat stub/unavailable as success.",
            "dry_prep/smoke gate ≠ production PASS (need cms+traj+md_summary+done).",
            "Do not submit 50ns/200ns without confirm=true.",
        ],
    }


def schrodinger_md_status(
    *,
    task_id: str,
    target_id: Optional[str] = None,
    api_base: Optional[str] = None,
) -> dict[str, Any]:
    base = (api_base or DEFAULT_API).rstrip("/")
    result = _http_json("GET", f"{base}/api/v1/affinity/md/{task_id}")
    via = "http"
    if result.get("status") == "unavailable" and "task_id" not in result:
        result = _local_status(task_id)
        via = "local_service"

    tid = (target_id or "").strip() or "_unset_"
    mem_path = append_md_job(
        {
            "event": "status",
            "via": via,
            "task_id": task_id,
            "status": result.get("status"),
            "job_dir": result.get("job_dir"),
            "message": result.get("message"),
            "completion": result.get("completion"),
        },
        target_id=tid,
    )
    return {
        **result,
        "tool": "schrodinger_md_status",
        "via": via,
        "md_jobs_path": mem_path,
        "catalog_ids_used": ["sz.desmond", "ed.http.affinity"],
    }
