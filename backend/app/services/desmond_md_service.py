"""Schrödinger Desmond MD service for affinity /md routes.

Modes
-----
- dry_prep (default): check $SCHRODINGER + multisim, write job_dir + msj + STATUS.json.
  Never submits production MD. Safe for UI/agent smoke tests.
- smoke: short loadtest protocol (~1 ns). Requires confirm=true to submit.
- short: 2 ns eq + 50 ns production. Requires confirm=true to submit.

Statuses: queued | running | completed | failed | gated | unavailable

Completion criteria (production PASS — documented for agent/harness):
  cms (*.cms) + traj dir + md_summary + done flag (.done_desmond / STATUS completed).
  smoke/dry_prep gate ≠ production PASS.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({"dry_prep", "smoke", "short"})
TERMINAL = frozenset({"completed", "failed", "gated", "unavailable"})

# Minimal Desmond auto protocol templates (times in ps).
_MSJ_SMOKE = """# smoke / loadtest ~1 ns — NOT production
task {
   task = "desmond:auto"
   set_family = {
      desmond = { checkpt.write_last_step = no }
      simulate.temperature = 310.15
   }
}
simulate {
   title       = "Brownian NVT 10K restraints 50ps"
   annealing   = off
   time        = 50
   timestep    = [0.001 0.001 0.003]
   temperature = 10.0
   ensemble = {
      class = "NVT"
      method = "Brownie"
      brownie = { delta_max = 0.1 }
   }
   restraints.new = [{
      name = posre_harm
      atoms = solute_heavy_atom
      force_constants = 50.0
   }]
}
simulate {
   title       = "NPT 310.15K unrestrained ~1ns smoke"
   annealing   = off
   time        = 1000
   temperature = 310.15
   ensemble = {
      class = NPT
      method = Langevin
      thermostat.tau = 0.1
      barostat.tau = 2.0
   }
   eneseq.interval = 10.0
   trajectory.interval = 200.0
   trajectory.center = solute
}
"""

_MSJ_SHORT = """# short: 2 ns eq + 50 ns production — requires confirm=true
task {
   task = "desmond:auto"
   set_family = {
      desmond = { checkpt.write_last_step = no }
      simulate.temperature = 310.15
   }
}
simulate {
   title       = "Brownian NVT 10K restraints 50ps"
   annealing   = off
   time        = 50
   timestep    = [0.001 0.001 0.003]
   temperature = 10.0
   ensemble = {
      class = "NVT"
      method = "Brownie"
      brownie = { delta_max = 0.1 }
   }
   restraints.new = [{
      name = posre_harm
      atoms = solute_heavy_atom
      force_constants = 50.0
   }]
}
simulate {
   title       = "NPT equilibration 2ns"
   annealing   = off
   time        = 2000
   temperature = 310.15
   ensemble = {
      class = NPT
      method = Langevin
      thermostat.tau = 0.1
      barostat.tau = 2.0
   }
   eneseq.interval = 10.0
   trajectory.interval = 200.0
   trajectory.center = solute
}
simulate {
   title       = "NPT production 50ns"
   annealing   = off
   time        = 50000
   temperature = 310.15
   ensemble = {
      class = NPT
      method = Langevin
      thermostat.tau = 0.1
      barostat.tau = 2.0
   }
   eneseq.interval = 10.0
   trajectory.interval = 200.0
   trajectory.center = solute
}
"""

_MSJ_DRY = """# dry_prep only — NOT submitted. Copy/edit before confirm submit.
# Prefer smoke (loadtest) or short (2+50ns) msj from this service when confirm=true.
task {
   task = "desmond:auto"
   set_family = {
      desmond = { checkpt.write_last_step = no }
      simulate.temperature = 310.15
   }
}
# Placeholder: replace with production stages after confirm.
simulate {
   title       = "DRY_PREP_PLACEHOLDER — do not run without confirm"
   annealing   = off
   time        = 10
   temperature = 310.15
   ensemble = { class = NVT method = Langevin }
}
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def jobs_root() -> Path:
    """Persist under backend/outputs/desmond_md_jobs/."""
    root = Path(__file__).resolve().parents[2] / "outputs" / "desmond_md_jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_schrodinger_home(install_path: Optional[str] = None) -> Optional[Path]:
    candidates: list[str] = []
    if install_path:
        candidates.append(install_path)
    env = os.environ.get("SCHRODINGER", "").strip()
    if env:
        candidates.append(env)
    candidates.append("/opt/schrodinger2023-3")
    for c in candidates:
        p = Path(c)
        if p.is_dir():
            return p
    return None


def find_multisim(schrodinger_home: Path) -> Optional[Path]:
    for rel in ("utilities/multisim", "multisim", "desmond"):
        p = schrodinger_home / rel
        if p.is_file() or p.is_symlink():
            return p
    return None


def check_desmond_env(install_path: Optional[str] = None) -> dict[str, Any]:
    home = resolve_schrodinger_home(install_path)
    if home is None:
        return {
            "ok": False,
            "available": False,
            "schrodinger_home": None,
            "multisim": None,
            "message": "SCHRODINGER install not found. Set $SCHRODINGER or schrodinger.install_path.",
        }
    multisim = find_multisim(home)
    if multisim is None:
        return {
            "ok": False,
            "available": False,
            "schrodinger_home": str(home),
            "multisim": None,
            "message": f"multisim not found under {home}",
        }
    return {
        "ok": True,
        "available": True,
        "schrodinger_home": str(home),
        "multisim": str(multisim),
        "message": "Schrödinger Desmond / multisim ready",
    }


def _write_status(job_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["updated_at"] = _utc_now()
    path = job_dir / "STATUS.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _read_status(job_dir: Path) -> Optional[dict[str, Any]]:
    path = job_dir / "STATUS.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _msj_for_mode(mode: str) -> str:
    if mode == "smoke":
        return _MSJ_SMOKE
    if mode == "short":
        return _MSJ_SHORT
    return _MSJ_DRY


def _production_done_markers(job_dir: Path) -> dict[str, bool]:
    cms = any(job_dir.glob("*.cms")) or any(job_dir.glob("*-out.cms"))
    traj = (job_dir / "trj").is_dir() or any(job_dir.glob("*_trj")) or any(job_dir.glob("**/clickme.dtr"))
    summary = (job_dir / "md_summary.json").is_file() or (job_dir / "md_summary.txt").is_file()
    done = (job_dir / ".done_desmond").is_file() or (job_dir / "DONE").is_file()
    return {"cms": cms, "traj": traj, "md_summary": summary, "done_flag": done}


def evaluate_completion(job_dir: Path, *, mode: str) -> dict[str, Any]:
    """Documented completion criteria for harness / agent."""
    markers = _production_done_markers(job_dir)
    if mode == "dry_prep":
        # STATUS.json is written together with the response; msj is the prep artifact.
        prep_ok = (job_dir / "md.msj").is_file()
        return {
            "production_pass": False,
            "gate_pass": prep_ok,
            "note": "dry_prep gate ≠ production PASS",
            "markers": markers,
        }
    if mode == "smoke":
        # smoke: STATUS completed + msj present is gate; full traj optional
        status = _read_status(job_dir) or {}
        gate = status.get("status") == "completed"
        return {
            "production_pass": False,
            "gate_pass": gate,
            "note": "smoke gate ≠ production PASS (need cms+traj+md_summary+done)",
            "markers": markers,
        }
    production = all(markers.values())
    return {
        "production_pass": production,
        "gate_pass": production,
        "note": "production PASS requires cms + traj + md_summary + done flag",
        "markers": markers,
    }


def get_task(task_id: str) -> Optional[dict[str, Any]]:
    job_dir = jobs_root() / task_id
    if not job_dir.is_dir():
        return None
    status = _read_status(job_dir)
    if status is None:
        return {
            "task_id": task_id,
            "status": "failed",
            "job_dir": str(job_dir),
            "message": "STATUS.json missing or corrupt",
        }
    # Refresh running jobs from filesystem heuristics
    if status.get("status") == "running":
        mode = str(status.get("mode") or "dry_prep")
        markers = _production_done_markers(job_dir)
        log_path = job_dir / "logs" / "multisim.log"
        failed_flag = (job_dir / "FAILED").is_file()
        if failed_flag:
            status = _write_status(
                job_dir,
                {**status, "status": "failed", "message": "FAILED flag present", "markers": markers},
            )
        elif markers.get("done_flag") or (
            markers.get("cms") and markers.get("traj") and mode in {"smoke", "short"}
        ):
            # Mark completed when done flag or cms+traj appear
            if markers.get("done_flag") or (markers.get("cms") and markers.get("traj")):
                status = _write_status(
                    job_dir,
                    {
                        **status,
                        "status": "completed",
                        "message": "Desmond job appears complete (filesystem markers)",
                        "markers": markers,
                        "completion": evaluate_completion(job_dir, mode=mode),
                    },
                )
        elif log_path.is_file():
            status = {**status, "log_tail": _tail(log_path, 20), "markers": markers}
    status.setdefault("job_dir", str(job_dir))
    status.setdefault("task_id", task_id)
    return status


def _tail(path: Path, n: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def submit_desmond_md(
    *,
    structure_path: Optional[str] = None,
    mode: str = "dry_prep",
    confirm: bool = False,
    simulation_time_ns: Optional[float] = None,
    host: Optional[str] = None,
    install_path: Optional[str] = None,
    molecule_id: Optional[str] = None,
    target_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a Desmond MD job. Default mode=dry_prep never submits production MD."""
    mode = (mode or "dry_prep").strip().lower()
    if mode not in VALID_MODES:
        return {
            "task_id": None,
            "status": "failed",
            "job_dir": None,
            "message": f"Invalid mode={mode!r}; expected one of {sorted(VALID_MODES)}",
        }

    env = check_desmond_env(install_path)
    task_id = str(uuid.uuid4())[:8]
    job_dir = jobs_root() / task_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "logs").mkdir(exist_ok=True)

    base: dict[str, Any] = {
        "task_id": task_id,
        "job_dir": str(job_dir),
        "mode": mode,
        "confirm": bool(confirm),
        "structure_path": structure_path,
        "simulation_time_ns": simulation_time_ns,
        "host": host or "localhost",
        "molecule_id": molecule_id,
        "target_id": target_id,
        "engine": "schrodinger_desmond",
        "created_at": _utc_now(),
        "env": env,
        "stub": False,
    }

    if not env.get("ok"):
        return _write_status(
            job_dir,
            {
                **base,
                "status": "unavailable",
                "message": env.get("message") or "Schrödinger Desmond unavailable",
            },
        )

    # Write protocol
    msj_path = job_dir / "md.msj"
    msj_path.write_text(_msj_for_mode(mode), encoding="utf-8")
    (job_dir / "README.md").write_text(
        "\n".join(
            [
                f"# Desmond MD job `{task_id}`",
                "",
                f"- mode: `{mode}`",
                f"- confirm: `{confirm}`",
                f"- structure: `{structure_path or '(none)'}`",
                "",
                "## Completion criteria",
                "- **dry_prep / smoke gate** ≠ production PASS",
                "- **production PASS**: cms + traj + md_summary + done flag",
                "",
                "Do not treat unavailable/gated/stub as success.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Stage structure if provided
    staged: Optional[str] = None
    if structure_path:
        src = Path(structure_path)
        if src.is_file():
            dest = job_dir / src.name
            try:
                if not dest.exists():
                    shutil.copy2(src, dest)
                staged = str(dest)
            except OSError as exc:
                logger.warning("Failed to stage structure: %s", exc)
                staged = structure_path
        else:
            return _write_status(
                job_dir,
                {
                    **base,
                    "status": "failed",
                    "message": f"structure_path not found: {structure_path}",
                    "msj": str(msj_path),
                },
            )
    base["staged_structure"] = staged

    # dry_prep: prepare only
    if mode == "dry_prep":
        completion = evaluate_completion(job_dir, mode=mode)
        return _write_status(
            job_dir,
            {
                **base,
                "status": "completed",
                "message": (
                    "Desmond dry_prep complete: job_dir + md.msj written. "
                    "No multisim submitted. Use mode=smoke|short with confirm=true for real MD."
                ),
                "msj": str(msj_path),
                "completion": completion,
            },
        )

    # Real modes require confirm
    if not confirm:
        return _write_status(
            job_dir,
            {
                **base,
                "status": "gated",
                "message": (
                    f"mode={mode} requires confirm=true to submit Desmond. "
                    "Job directory and md.msj prepared; not submitted."
                ),
                "msj": str(msj_path),
                "completion": evaluate_completion(job_dir, mode=mode),
            },
        )

    # Submit multisim asynchronously
    cms_input = staged
    if cms_input and not str(cms_input).endswith((".cms", ".mae", ".maegz")):
        return _write_status(
            job_dir,
            {
                **base,
                "status": "failed",
                "message": "Desmond submit expects .cms / .mae / .maegz structure_path",
                "msj": str(msj_path),
            },
        )
    if not cms_input:
        return _write_status(
            job_dir,
            {
                **base,
                "status": "failed",
                "message": "structure_path required for confirmed smoke/short submit",
                "msj": str(msj_path),
            },
        )

    status = _write_status(
        job_dir,
        {
            **base,
            "status": "queued",
            "message": f"Desmond {mode} queued for multisim submit",
            "msj": str(msj_path),
        },
    )
    thread = threading.Thread(
        target=_run_multisim,
        kwargs={
            "job_dir": job_dir,
            "msj_path": msj_path,
            "cms_input": cms_input,
            "multisim": env["multisim"],
            "host": host or "localhost",
            "mode": mode,
            "base": base,
        },
        daemon=True,
        name=f"desmond-md-{task_id}",
    )
    thread.start()
    return status


def _run_multisim(
    *,
    job_dir: Path,
    msj_path: Path,
    cms_input: str,
    multisim: str,
    host: str,
    mode: str,
    base: dict[str, Any],
) -> None:
    log_path = job_dir / "logs" / "multisim.log"
    jobname = f"edrug_md_{job_dir.name}"
    cmd = [
        multisim,
        "-HOST",
        host,
        "-maxjob",
        "1",
        "-JOBNAME",
        jobname,
        "-m",
        str(msj_path.name),
        Path(cms_input).name if Path(cms_input).parent == job_dir else cms_input,
        "-mode",
        "umbrella",
    ]
    _write_status(
        job_dir,
        {
            **base,
            "status": "running",
            "message": f"multisim started: {' '.join(cmd)}",
            "msj": str(msj_path),
            "command": cmd,
        },
    )
    try:
        with log_path.open("w", encoding="utf-8") as logf:
            logf.write(f"# cmd: {' '.join(cmd)}\n")
            logf.flush()
            proc = subprocess.run(
                cmd,
                cwd=str(job_dir),
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=None if mode == "short" else 86400,
                env={**os.environ, "SCHRODINGER": str(Path(multisim).resolve().parents[1])},
            )
        markers = _production_done_markers(job_dir)
        if proc.returncode == 0:
            (job_dir / ".done_desmond").touch()
            # Write a minimal summary for smoke/short
            summary = {
                "returncode": proc.returncode,
                "mode": mode,
                "markers": markers,
                "finished_at": _utc_now(),
            }
            (job_dir / "md_summary.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
            _write_status(
                job_dir,
                {
                    **base,
                    "status": "completed",
                    "message": f"Desmond {mode} multisim finished (rc=0)",
                    "msj": str(msj_path),
                    "command": cmd,
                    "markers": markers,
                    "completion": evaluate_completion(job_dir, mode=mode),
                },
            )
        else:
            (job_dir / "FAILED").write_text(f"rc={proc.returncode}\n", encoding="utf-8")
            _write_status(
                job_dir,
                {
                    **base,
                    "status": "failed",
                    "message": f"multisim failed rc={proc.returncode}",
                    "msj": str(msj_path),
                    "command": cmd,
                    "log_tail": _tail(log_path),
                    "markers": markers,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Desmond multisim failed")
        (job_dir / "FAILED").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        _write_status(
            job_dir,
            {
                **base,
                "status": "failed",
                "message": f"{type(exc).__name__}: {exc}",
                "msj": str(msj_path),
                "command": cmd,
                "log_tail": _tail(log_path),
            },
        )
