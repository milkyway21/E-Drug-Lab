"""薛定谔本地对接服务 — 供主工作流 affinity 路由调用。"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rdkit import Chem
from sqlalchemy.orm import Session

from app.config import SchrodingerSettings, get_settings
from app.services.docking_prep import resolve_receptor_pdb

logger = logging.getLogger(__name__)

SCHRODINGER_WORK_DIR = Path("data/schrodinger")


@dataclass
class PipelineLigand:
    molecule_id: str
    smiles: str
    name: str = ""


def local_health(settings: Optional[SchrodingerSettings] = None) -> dict[str, Any]:
    """本地 Schrödinger 安装健康检查。"""
    from app.pipelines.vav1_rl import schrodinger_local as sch

    s = settings or get_settings().schrodinger
    h = sch.health(install_path=s.install_path)
    h["use_local"] = s.use_local
    h["ph"] = s.ph
    h["available"] = bool(h.get("ok"))
    return h


def write_ligands_sdf(ligands: list[PipelineLigand], sdf_path: Path) -> dict[str, str]:
    """将 SMILES 列表写入 SDF，返回 title→molecule_id 映射。"""
    sdf_path.parent.mkdir(parents=True, exist_ok=True)
    title_map: dict[str, str] = {}
    writer = Chem.SDWriter(str(sdf_path))
    try:
        for i, lig in enumerate(ligands):
            mol = Chem.MolFromSmiles(lig.smiles)
            if mol is None:
                logger.warning("跳过无效 SMILES: %s", lig.smiles)
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
) -> dict[str, Any]:
    """流水线友好：SMILES 列表 → LigPrep → PrepWizard → Glide → 可选 MM-GBSA。"""
    from app.pipelines.vav1_rl import schrodinger_local as sch

    if not ligands:
        return {"ok": False, "error": "无有效配体"}

    run_id = f"schrod_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    out = Path(output_dir) if output_dir else SCHRODINGER_WORK_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)

    ligands_sdf = str(out / "ligands_input.sdf")
    title_map = write_ligands_sdf(ligands, Path(ligands_sdf))
    if not title_map:
        return {"ok": False, "error": "无法从 SMILES 生成配体 SDF"}

    ipath = install_path or get_settings().schrodinger.install_path
    result = sch.end_to_end_dock(
        ligands_sdf=ligands_sdf,
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

    # 将 Glide/MM-GBSA 分数映射回 molecule_id
    molecule_results: list[dict[str, Any]] = []
    glide_by_title = {g["title"]: g for g in result.get("glide_scores", [])}
    mmgbsa_by_title = {m["title"]: m for m in result.get("mmgbsa_scores", [])}

    for title, mol_id in title_map.items():
        g = glide_by_title.get(title, {})
        m = mmgbsa_by_title.get(title, {})
        molecule_results.append({
            "molecule_id": mol_id,
            "title": title,
            "glide_score": g.get("glide_xp_score"),
            "glide_rmsd": g.get("glide_rmsd"),
            "mmgbsa_dg": m.get("mmgbsa_dg"),
            "success": g.get("glide_xp_score") is not None,
        })

    return {
        "ok": result.get("all_ok", False),
        "run_id": run_id,
        "output_dir": str(out),
        "precision": result.get("precision", precision.upper()),
        "steps_log": result.get("steps_log", []),
        "output_files": result.get("output_files", {}),
        "molecule_results": molecule_results,
        "glide_scores": result.get("glide_scores", []),
        "mmgbsa_scores": result.get("mmgbsa_scores", []),
    }


def resolve_receptor_for_target(
    *,
    target_id: Optional[str] = None,
    target_pdb_id: Optional[str] = None,
    receptor_path: Optional[str] = None,
    db: Optional[Session] = None,
) -> Path:
    if receptor_path and Path(receptor_path).is_file():
        return Path(receptor_path).resolve()
    return resolve_receptor_pdb(
        target_pdb_id=target_pdb_id,
        target_id=target_id,
        db=db,
    )


def run_mmgbsa_on_pose(
    pose_maegz: str,
    *,
    receptor_maegz: Optional[str] = None,
    output_csv: Optional[str] = None,
    install_path: Optional[str] = None,
) -> dict[str, Any]:
    """对已有 Glide pose 运行 Prime MM-GBSA。"""
    from app.pipelines.vav1_rl import schrodinger_local as sch

    pose = Path(pose_maegz)
    if not pose.is_file():
        return {"ok": False, "error": f"Pose 文件不存在: {pose_maegz}"}

    ipath = install_path or get_settings().schrodinger.install_path
    csv_path = output_csv or str(pose.parent / f"mmgbsa_{pose.stem}.csv")
    r = sch.prime_mmgbsa(str(pose), csv_path, install_path=ipath, receptor_maegz=receptor_maegz)
    scores = sch.parse_mmgbsa_scores(csv_path) if r.ok else []
    return {
        "ok": r.ok,
        "scores": scores,
        "csv_path": csv_path if r.ok else None,
        "stderr": r.stderr if not r.ok else None,
    }
