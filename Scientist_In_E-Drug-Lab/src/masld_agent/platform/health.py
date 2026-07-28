"""Probe DiffDynamic / e-drug-lab / Schrödinger health."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from masld_agent.platform.edrug_bridge import (
    try_import_diffdynamic_runner,
    try_import_schrodinger,
    try_import_schrodinger_local,
)
from masld_agent.platform.paths import (
    DIFFDYNAMIC_CONDA,
    DIFFDYNAMIC_ROOT,
    EDRUG_BACKEND,
    EDRUG_ROOT,
    SCHRODINGER_HOME,
)


def _file_ok(p: Path) -> bool:
    return p.is_file()


def _dir_ok(p: Path) -> bool:
    return p.is_dir()


def check_diffdynamic() -> dict[str, Any]:
    root = DIFFDYNAMIC_ROOT
    conda = DIFFDYNAMIC_CONDA
    weight = root / "pretrained_models" / "pretrained_diffusion.pt"
    sample_py = root / "scripts" / "sample_diffusion.py"
    python_bin = conda / "bin" / "python"
    details = {
        "root": str(root),
        "root_ok": _dir_ok(root),
        "conda": str(conda),
        "conda_python_ok": _file_ok(python_bin),
        "weight_ok": _file_ok(weight),
        "sample_script_ok": _file_ok(sample_py),
        "weight_path": str(weight),
    }
    runner, err = try_import_diffdynamic_runner()
    details["edrug_runner_import"] = err is None
    details["edrug_runner_error"] = err
    if runner is not None:
        try:
            st = runner.status()
            details["runner_status"] = st if isinstance(st, dict) else {"raw": str(st)}
        except Exception as exc:  # noqa: BLE001
            details["runner_status_error"] = f"{type(exc).__name__}: {exc}"
    ok = bool(
        details["root_ok"]
        and details["conda_python_ok"]
        and details["weight_ok"]
        and details["sample_script_ok"]
    )
    return {
        "system": "dd",
        "ok": ok,
        "catalog_ids": ["dd.env", "ed.svc.diffdynamic"],
        "details": details,
    }


def check_edrug() -> dict[str, Any]:
    details = {
        "root": str(EDRUG_ROOT),
        "root_ok": _dir_ok(EDRUG_ROOT),
        "backend": str(EDRUG_BACKEND),
        "backend_ok": _dir_ok(EDRUG_BACKEND),
        "diffdynamic_runner_py": _file_ok(
            EDRUG_BACKEND / "app" / "services" / "diffdynamic_runner.py"
        ),
        "schrodinger_service_py": _file_ok(
            EDRUG_BACKEND / "app" / "services" / "schrodinger_service.py"
        ),
        "schrodinger_local_py": _file_ok(
            EDRUG_BACKEND
            / "app"
            / "pipelines"
            / "vav1_rl"
            / "schrodinger_local.py"
        ),
    }
    _, dd_err = try_import_diffdynamic_runner()
    _, sz_err = try_import_schrodinger()
    _, loc_err = try_import_schrodinger_local()
    details["import_diffdynamic_runner"] = dd_err is None
    details["import_diffdynamic_error"] = dd_err
    details["import_schrodinger_service"] = sz_err is None
    details["import_schrodinger_error"] = sz_err
    details["import_schrodinger_local"] = loc_err is None
    details["import_schrodinger_local_error"] = loc_err
    details["integrations_stub_note"] = (
        "api/integrations/* remote stubs are NOT production — see ed.integrations.stub"
    )
    ok = bool(
        details["backend_ok"]
        and details["diffdynamic_runner_py"]
        and details["schrodinger_service_py"]
        and details["import_diffdynamic_runner"]
        and details["import_schrodinger_service"]
    )
    return {
        "system": "ed",
        "ok": ok,
        "catalog_ids": ["ed.root", "ed.svc.diffdynamic", "ed.svc.schrodinger", "ed.integrations.stub"],
        "details": details,
    }


def check_schrodinger() -> dict[str, Any]:
    home = SCHRODINGER_HOME
    run_bin = home / "run"
    glide = home / "glide"
    ligprep = home / "ligprep"
    prepwizard = home / "utilities" / "prepwizard"
    env_set = bool(os.environ.get("SCHRODINGER") or os.environ.get("MASLD_SCHRODINGER"))
    details = {
        "SCHRODINGER": str(home),
        "env_explicitly_set": env_set,
        "home_ok": _dir_ok(home),
        "run_ok": _file_ok(run_bin) or bool(shutil.which("run")),
        "glide_ok": _file_ok(glide),
        "ligprep_ok": _file_ok(ligprep),
        "prepwizard_ok": _file_ok(prepwizard),
        "SCHRODINGER_TEMPDIR": os.environ.get("SCHRODINGER_TEMPDIR"),
    }
    sch, err = try_import_schrodinger()
    details["edrug_service_import"] = err is None
    details["edrug_service_error"] = err
    if sch is not None and hasattr(sch, "local_health"):
        try:
            details["local_health"] = sch.local_health()
        except Exception as exc:  # noqa: BLE001
            details["local_health_error"] = f"{type(exc).__name__}: {exc}"
    ok = bool(details["home_ok"] and details["run_ok"] and details["glide_ok"])
    return {
        "system": "sz",
        "ok": ok,
        "catalog_ids": ["sz.env", "sz.bin.run", "sz.bin.glide", "ed.svc.schrodinger"],
        "details": details,
    }


def platform_health() -> dict[str, Any]:
    dd = check_diffdynamic()
    ed = check_edrug()
    sz = check_schrodinger()
    systems = [dd, ed, sz]
    return {
        "status": "ok" if all(s["ok"] for s in systems) else "degraded",
        "systems": {s["system"]: s for s in systems},
        "warnings": [
            "Never invent docking scores or generated molecules.",
            "Large jobs require confirm=true (see gates).",
            "api/integrations/* stubs are not production paths.",
        ],
        "catalog_ids_used": ["dd.env", "ed.root", "sz.env"],
    }
