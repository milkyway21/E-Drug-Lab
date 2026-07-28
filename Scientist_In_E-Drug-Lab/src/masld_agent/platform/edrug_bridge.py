"""Lazy import bridge into /data/ye/e-drug-lab/backend app.* modules.

Avoids full FastAPI ``get_settings()`` (which reads cwd ``.env`` and fails under
Scientist_In_E-Drug-Lab). Constructs ``DiffDynamicSettings`` / Schrödinger
facades directly; Schrödinger path prefers ``schrodinger_local`` to skip
sqlalchemy-only imports on ``schrodinger_service``.
"""
from __future__ import annotations

import sys
import types
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from masld_agent.platform.paths import (
    DIFFDYNAMIC_CONDA_NAME,
    DIFFDYNAMIC_ROOT,
    EDRUG_BACKEND,
    SCHRODINGER_HOME,
)


class BridgeError(RuntimeError):
    pass


def ensure_backend_on_path() -> str:
    backend = str(EDRUG_BACKEND.resolve())
    if not EDRUG_BACKEND.is_dir():
        raise BridgeError(f"e-drug-lab backend not found: {backend}")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    return backend


def _diffdynamic_settings():
    from app.config import DiffDynamicSettings  # type: ignore

    return DiffDynamicSettings(
        runtime="local",
        conda_env=DIFFDYNAMIC_CONDA_NAME,
        root=str(DIFFDYNAMIC_ROOT),
    )


def try_import_diffdynamic_runner() -> tuple[Optional[Any], Optional[str]]:
    try:
        ensure_backend_on_path()
        from app.services.diffdynamic_runner import DiffDynamicRunner  # type: ignore

        return DiffDynamicRunner(_diffdynamic_settings()), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


@dataclass
class PipelineLigand:
    molecule_id: str
    smiles: str
    name: str = ""


def _schrodinger_facade() -> types.SimpleNamespace:
    """Minimal facade matching schrodinger_service call surface."""
    from app.pipelines.vav1_rl import schrodinger_local as sch  # type: ignore

    install = str(SCHRODINGER_HOME)

    def local_health(settings: Any = None) -> dict[str, Any]:
        h = sch.health(install_path=install)
        h["use_local"] = True
        h["available"] = bool(h.get("ok"))
        h["install_path"] = install
        return h

    def write_ligands_sdf(ligands: list[PipelineLigand], sdf_path: Path) -> dict[str, str]:
        from rdkit import Chem

        sdf_path.parent.mkdir(parents=True, exist_ok=True)
        title_map: dict[str, str] = {}
        writer = Chem.SDWriter(str(sdf_path))
        try:
            for i, lig in enumerate(ligands):
                mol = Chem.MolFromSmiles(lig.smiles)
                if mol is None:
                    continue
                title = lig.name or lig.molecule_id or f"mol_{i}"
                mol.SetProp("_Name", title)
                writer.write(mol)
                title_map[title] = lig.molecule_id
        finally:
            writer.close()
        return title_map

    def run_pipeline_dock(
        *,
        ligands: list[PipelineLigand],
        receptor_pdb: str,
        output_dir: Optional[str] = None,
        precision: str = "SP",
        ph: float = 7.2,
        ph_threshold: float = 0.2,
        box_center: Optional[tuple[float, float, float]] = None,
        box_size: tuple[int, int, int] = (20, 20, 20),
        poses_per_lig: int = 5,
        postdock_minimize: bool = True,
        run_mmgbsa: bool = False,
        install_path: Optional[str] = None,
        timeout_per_stage: int = 7200,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        if not ligands:
            return {"ok": False, "error": "无有效配体"}
        run_id = f"schrod_{int(__import__('time').time())}_{uuid.uuid4().hex[:6]}"
        out = Path(output_dir) if output_dir else Path("runs") / "platform" / "schrodinger" / run_id
        out.mkdir(parents=True, exist_ok=True)
        ligands_sdf = out / "ligands_input.sdf"
        title_map = write_ligands_sdf(ligands, ligands_sdf)
        if not title_map:
            return {"ok": False, "error": "无法从 SMILES 生成配体 SDF"}
        ipath = install_path or install
        result = sch.end_to_end_dock(
            ligands_sdf=str(ligands_sdf),
            receptor_pdb=receptor_pdb,
            output_dir=str(out),
            install_path=ipath,
            ph=ph,
            ph_threshold=ph_threshold,
            box_center=box_center,
            box_size=box_size,
            precision=precision,
            poses_per_lig=poses_per_lig,
            postdock_minimize=postdock_minimize,
            run_mmgbsa=run_mmgbsa,
            timeout_per_stage=timeout_per_stage,
        )
        return {
            "ok": result.get("all_ok", False),
            "run_id": run_id,
            "output_dir": str(out),
            "precision": result.get("precision", precision.upper()),
            "steps_log": result.get("steps_log", []),
            "output_files": result.get("output_files", {}),
            "glide_scores": result.get("glide_scores", []),
            "mmgbsa_scores": result.get("mmgbsa_scores", []),
            "title_map": title_map,
            "source": "schrodinger_local_facade",
        }

    def run_mmgbsa_on_pose(
        pose_maegz: str,
        *,
        receptor_maegz: Optional[str] = None,
        output_csv: Optional[str] = None,
        install_path: Optional[str] = None,
    ) -> dict[str, Any]:
        pose = Path(pose_maegz)
        if not pose.is_file():
            return {"ok": False, "error": f"Pose 文件不存在: {pose_maegz}"}
        csv_path = output_csv or str(pose.parent / f"mmgbsa_{pose.stem}.csv")
        r = sch.prime_mmgbsa(
            str(pose),
            csv_path,
            install_path=install_path or install,
            receptor_maegz=receptor_maegz,
        )
        scores = sch.parse_mmgbsa_scores(csv_path) if r.ok else []
        return {
            "ok": r.ok,
            "scores": scores,
            "csv_path": csv_path if r.ok else None,
            "stderr": r.stderr if not r.ok else None,
            "source": "schrodinger_local_facade",
        }

    return types.SimpleNamespace(
        PipelineLigand=PipelineLigand,
        local_health=local_health,
        write_ligands_sdf=write_ligands_sdf,
        run_pipeline_dock=run_pipeline_dock,
        run_mmgbsa_on_pose=run_mmgbsa_on_pose,
        _install_path=install,
    )


def try_import_schrodinger() -> tuple[Optional[Any], Optional[str]]:
    """Return module-like facade with local_health / run_pipeline_dock / PipelineLigand.

    Uses ``schrodinger_local`` facade by default so Scientist venv need not install
    sqlalchemy / load backend ``.env`` via ``get_settings()``.
    """
    try:
        ensure_backend_on_path()
        return _schrodinger_facade(), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def try_import_schrodinger_local() -> tuple[Optional[Any], Optional[str]]:
    try:
        ensure_backend_on_path()
        from app.pipelines.vav1_rl import schrodinger_local as sch  # type: ignore

        return sch, None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
