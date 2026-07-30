"""UI command queue for Agent → web frontend (separate from edrug_bridge compute)."""
from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

_lock = __import__("threading").Lock()
_queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
_MAX_PER_SESSION = 200

# Exact POST paths allowed for edrug_ui_start_task (must match backend routers).
TASK_WHITELIST = frozenset(
    {
        # screening
        "/api/v1/screening/start",
        # pipeline
        "/api/v1/pipeline/runs",
        # targets
        "/api/v1/targets",
        "/api/v1/targets/download",
        "/api/v1/targets/predict",
        "/api/v1/targets/upload-protein",
        "/api/v1/targets/upload-ligand",
        # libraries
        "/api/v1/libraries",
        "/api/v1/libraries/upload",
        "/api/v1/libraries/scaffolds/extract",
        # admet
        "/api/v1/admet/predict",
        "/api/v1/admet/predict/single",
        "/api/v1/admet/filter",
        # diffdynamic
        "/api/v1/diffdynamic/generate",
        "/api/v1/diffdynamic/evaluate",
        "/api/v1/diffdynamic/extract",
        "/api/v1/diffdynamic/ingest",
        # molecules
        "/api/v1/molecules/generate",
        # affinity / docking
        "/api/v1/affinity/docking/vina",
        "/api/v1/affinity/docking/vina/batch",
        "/api/v1/affinity/docking/glide",
        "/api/v1/affinity/schrodinger/dock",
        "/api/v1/affinity/mmgbsa",
        "/api/v1/affinity/md",
        "/api/v1/affinity/dock",
        "/api/v1/affinity/dock/batch",
        # ranking
        "/api/v1/ranking/orthogonal-rescore",
        # wetlab
        "/api/v1/wetlab/analyze",
        "/api/v1/wetlab/export-order-pack",
        # molecule database
        "/api/v1/molecule-db/sync",
        # glare
        "/api/v1/glare/screen",
        "/api/v1/glare/train",
        "/api/v1/glare/import-wetlab",
        # drugclip
        "/api/v1/drugclip/service/start",
        "/api/v1/drugclip/service/stop",
        "/api/v1/drugclip/smoke-test",
        "/api/v1/drugclip/pipeline-screen",
        "/api/v1/drugclip/screen",
        # diffgui
        "/api/v1/diffgui/generate",
        "/api/v1/diffgui/ingest",
        # tame-vs
        "/api/v1/tame-vs/build-image",
        "/api/v1/tame-vs/prepare-library",
        "/api/v1/tame-vs/smoke-test",
        "/api/v1/tame-vs/full-50k-screen",
        "/api/v1/tame-vs/ingest-results",
        "/api/v1/tame-vs/service/start",
        "/api/v1/tame-vs/service/stop",
        "/api/v1/tame-vs/service/restart",
        # vav1-rl / rl-rounds
        "/api/v1/vav1-rl/run",
        "/api/v1/rl-rounds",
    }
)

# Parameterized POST paths (prefix + suffix action).
TASK_PREFIX_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("/api/v1/pipeline/runs/", ("/steps/", "/resume")),
    ("/api/v1/targets/", ("/preprocess",)),
    ("/api/v1/libraries/", ("/filter",)),
    ("/api/v1/screening/", ("/cancel",)),
    ("/api/v1/tasks/", ("/cancel", "/retry")),
    ("/api/v1/molecules/", ("/rank",)),
    ("/api/v1/rl-rounds/", ("/advance",)),
    ("/api/v1/vav1-rl/steps/", ("/run",)),
)

NAV_WHITELIST = frozenset(
    {
        "/",
        "/workflow",
        "/workflow/target-prep",
        "/workflow/virtual-screening",
        "/workflow/admet-filter",
        "/workflow/candidate-rank",
        "/database",
        "/records",
        "/models",
        "/docs",
    }
)


def is_task_path_whitelisted(api_path: str) -> bool:
    if api_path in TASK_WHITELIST:
        return True
    for prefix, suffixes in TASK_PREFIX_RULES:
        if not api_path.startswith(prefix):
            continue
        for suffix in suffixes:
            if api_path.endswith(suffix) or suffix in api_path:
                return True
    return False


def enqueue_ui_command(session_id: str, command: dict[str, Any]) -> dict[str, Any]:
    sid = session_id or "default"
    cmd = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        **command,
    }
    with _lock:
        q = _queues[sid]
        q.append(cmd)
        while len(q) > _MAX_PER_SESSION:
            q.popleft()
    return {"status": "ok", "command": cmd}


def drain_ui_commands(session_id: str, *, since_id: str | None = None) -> list[dict[str, Any]]:
    sid = session_id or "default"
    with _lock:
        items = list(_queues[sid])
    if since_id:
        try:
            idx = next(i for i, c in enumerate(items) if c.get("id") == since_id)
            items = items[idx + 1 :]
        except StopIteration:
            pass
    return items


def ui_navigate(session_id: str, path: str) -> dict[str, Any]:
    path = path if path.startswith("/") else f"/{path}"
    if path not in NAV_WHITELIST:
        return {"status": "error", "error": f"path not in whitelist: {path}"}
    return enqueue_ui_command(session_id, {"type": "navigate", "path": path})


def ui_highlight(session_id: str, entity_type: str, entity_id: str) -> dict[str, Any]:
    return enqueue_ui_command(
        session_id,
        {"type": "highlight", "entity_type": entity_type, "entity_id": entity_id},
    )


def ui_open_molecule(session_id: str, molecule_id: str, smiles: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": "open_molecule", "molecule_id": molecule_id}
    if smiles:
        payload["smiles"] = smiles
    return enqueue_ui_command(session_id, payload)


def ui_set_target(session_id: str, target_id: str, name: str | None = None) -> dict[str, Any]:
    return enqueue_ui_command(
        session_id,
        {"type": "set_target", "target_id": target_id, "name": name},
    )


def ui_start_task(session_id: str, api_path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    api_path = api_path if api_path.startswith("/") else f"/{api_path}"
    if not is_task_path_whitelisted(api_path):
        return {"status": "error", "error": f"api_path not whitelisted: {api_path}"}
    return enqueue_ui_command(
        session_id,
        {"type": "start_task", "api_path": api_path, "body": body or {}},
    )
