"""薛定谉本地 subprocess 集成：LigPrep(pH7.2) / Protein Prep Wizard / Glide XP / prime MM-GBSA。

与 e-drug-lab 的 api/integrations/schrodinger.py（远程 HTTP stub）解耦——本模块直接调
$SCHRODINGER 本地可执行，服务于 VAV1 11 步流水线步骤5。
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _schrodinger_bin(install_path: str, name: str) -> str:
    return str(Path(install_path) / name)


def _run(cmd: list[str], cwd: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    logger.info("SCHROD run: %s (cwd=%s)", " ".join(cmd), cwd)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


@dataclass
class SchrodingerLocalResult:
    ok: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    output_files: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LigPrep — 配体准备 + pH 7.2 离子化
# ---------------------------------------------------------------------------
def ligprep(
    input_smi_or_sdf: str,
    output_sdf: str,
    install_path: str = "/opt/schrodinger2023-3",
    ph: float = 7.2,
    ph_threshold: float = 0.2,
    max_stereo: int = 32,
    timeout: int = 1800,
) -> SchrodingerLocalResult:
    """LigPrep 配体准备：离子化(pH)、立体异构体生成、3D 构象。

    输入 .smi/.sdf，输出 .sdf（多构象）。
    """
    cmd = [
        _schrodinger_bin(install_path, "ligprep"),
        "-ismi" if input_smi_or_sdf.endswith(".smi") or input_smi_or_sdf.endswith(".smiles") else "-isd",
        input_smi_or_sdf,
        "-osd", output_sdf,
        "-epik",                  # 用 Epik 预测离子化状态
        "-ph", str(ph),
        "-pht", str(ph_threshold),
        "-s", str(max_stereo),    # 立体异构体数
        "-t", "1",                # 每分子 1 个构象（对接前）
    ]
    proc = _run(cmd, cwd=str(Path(output_sdf).parent), timeout=timeout)
    return SchrodingerLocalResult(
        ok=proc.returncode == 0 and Path(output_sdf).is_file(),
        returncode=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:],
        output_files={"output_sdf": output_sdf},
    )


# ---------------------------------------------------------------------------
# Protein Preparation Wizard — 受体质子化 (pH 7.2)
# ---------------------------------------------------------------------------
def prepwizard(
    input_pdb: str,
    output_maegz: str,
    install_path: str = "/opt/schrodinger2023-3",
    ph: float = 7.2,
    ph_threshold: float = 0.2,
    minimize: bool = True,
    timeout: int = 3600,
) -> SchrodingerLocalResult:
    """Protein Prep Wizard：预处理 + Epik 质子化(pH) + H 优化 + 最小化。

    通过 CLI `utilities/prepwizard` 调用（Schrödinger 2023-3 本地安装）。
    输出 .maegz（Glide 网格生成所需）。
    """
    out_dir = Path(output_maegz).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        _schrodinger_bin(install_path, "utilities/prepwizard"),
        input_pdb, output_maegz,
        "-epik_pH", str(ph),
        "-epik_pHt", str(ph_threshold),
        "-captermini",
        "-fillsidechains",
        "-disulfides",
        "-propka_pH", str(ph),
        "-WAIT",
    ]
    if not minimize:
        cmd.append("-noimpref")
    proc = _run(cmd, cwd=str(out_dir), timeout=timeout)
    return SchrodingerLocalResult(
        ok=proc.returncode == 0 and Path(output_maegz).is_file(),
        returncode=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:],
        output_files={"output_maegz": output_maegz},
    )


# ---------------------------------------------------------------------------
# Glide 网格生成 + XP 对接
# ---------------------------------------------------------------------------
def glide_grid(
    receptor_maegz: str,
    grid_zip: str,
    box_center: tuple[float, float, float],
    box_size: tuple[int, int, int] = (20, 20, 20),
    install_path: str = "/opt/schrodinger2023-3",
    timeout: int = 1800,
) -> SchrodingerLocalResult:
    """生成 Glide 网格文件 grid.zip。"""
    cx, cy, cz = box_center
    ix, iy, iz = (10, 10, 10)  # innerbox
    ox, oy, oz = box_size
    grid_in = f"""GRID_CENTER   {cx} {cy} {cz}
INNERBOX      {ix} {iy} {iz}
OUTERBOX      {ox} {oy} {oz}
RECEP_FILE    {receptor_maegz}
GRIDFILE      {grid_zip}
"""
    in_path = str(Path(grid_zip).with_suffix(".in"))
    Path(in_path).write_text(grid_in)
    cmd = [_schrodinger_bin(install_path, "glide"), in_path, "-WAIT"]
    proc = _run(cmd, cwd=str(Path(grid_zip).parent), timeout=timeout)
    return SchrodingerLocalResult(
        ok=proc.returncode == 0 and Path(grid_zip).is_file(),
        returncode=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:],
        output_files={"grid_zip": grid_zip},
    )


def glide_dock(
    ligands_sdf: str,
    grid_zip: str,
    output_pose_maegz: str,
    install_path: str = "/opt/schrodinger2023-3",
    precision: str = "XP",
    poses_per_lig: int = 10,
    postdock_minimize: bool = True,
    timeout: int = 7200,
) -> SchrodingerLocalResult:
    """Glide 对接（HTVS / SP / XP）。输出 pose .maegz。"""
    prec = precision.upper().strip()
    if prec not in {"HTVS", "SP", "XP"}:
        prec = "SP"
    dock_in = f"""GRID_FILE      {grid_zip}
LIGANDFILE     {ligands_sdf}
POSES_PER_LIG  {poses_per_lig}
PRECISION      {prec}
POSTDOCK_MINIMIZE  {'yes' if postdock_minimize else 'no'}
NREPORT        1
OUTPOSE        {output_pose_maegz}
"""
    in_path = str(Path(output_pose_maegz).with_suffix(".in"))
    Path(in_path).write_text(dock_in)
    cmd = [_schrodinger_bin(install_path, "glide"), in_path, "-WAIT"]
    proc = _run(cmd, cwd=str(Path(output_pose_maegz).parent), timeout=timeout)
    return SchrodingerLocalResult(
        ok=proc.returncode == 0 and Path(output_pose_maegz).is_file(),
        returncode=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:],
        output_files={"pose_maegz": output_pose_maegz, "precision": prec},
    )


def glide_xp_dock(
    ligands_sdf: str,
    grid_zip: str,
    output_pose_maegz: str,
    install_path: str = "/opt/schrodinger2023-3",
    poses_per_lig: int = 10,
    postdock_minimize: bool = True,
    timeout: int = 7200,
) -> SchrodingerLocalResult:
    """Glide XP 对接（兼容旧接口）。"""
    return glide_dock(
        ligands_sdf, grid_zip, output_pose_maegz,
        install_path=install_path, precision="XP",
        poses_per_lig=poses_per_lig, postdock_minimize=postdock_minimize, timeout=timeout,
    )


def parse_glide_xp_scores(pose_maegz: str, install_path: str = "/opt/schrodinger2023-3") -> list[dict]:
    """从 Glide pose .maegz 解析每分子 Glide XP score（越负越好）。

    用 Schrodinger Python 读 structure，提取 title + Glide_Rmsd + r_i_glide_gscore。
    """
    import os as _os
    script = f"""
from schrodinger import structure
out = []
for st in structure.StructureReader({pose_maegz!r}):
    title = st.title
    gscore = st.property.get('r_i_glide_gscore', None)
    rmsd = st.property.get('r_i_glide_rmsd', None)
    out.append((title, gscore, rmsd))
import json, sys
sys.stdout.write(json.dumps(out))
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name
    try:
        proc = _run([_schrodinger_bin(install_path, "run"), "python3", script_path], cwd=".", timeout=600)
        if proc.returncode != 0:
            logger.error("Glide parse failed: %s", proc.stderr[-1000:])
            return []
        import json
        raw = proc.stdout.strip()
        if not raw:
            return []
        # 取最后一行 JSON（跳过可能的 warnings）
        rows = json.loads(raw.split("\n")[-1])
        return [{"title": r[0], "glide_xp_score": r[1], "glide_rmsd": r[2]} for r in rows]
    except Exception as e:
        logger.error("Glide parse exception: %s", e)
        return []
    finally:
        try:
            _os.unlink(script_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Prime MM-GBSA
# ---------------------------------------------------------------------------
def prime_mmgbsa(
    pose_maegz: str,
    output_csv: str,
    install_path: str = "/opt/schrodinger2023-3",
    receptor_maegz: Optional[str] = None,
    timeout: int = 7200,
) -> SchrodingerLocalResult:
    """Prime MM-GBSA 重打分。ΔG 越负越好。

    若提供 receptor_maegz，用 receptor-ligand 模式（更准）；否则 ligand-only。
    """
    cmd = [
        _schrodinger_bin(install_path, "prime_mmgbsa"),
        pose_maegz,
        "-job_type", "ENERGY",
        "-csv_output", "yes",
        "-out_csv", output_csv,
        "-WAIT",
    ]
    if receptor_maegz:
        cmd.extend(["-receptor", receptor_maegz])
    proc = _run(cmd, cwd=str(Path(output_csv).parent), timeout=timeout)
    return SchrodingerLocalResult(
        ok=proc.returncode == 0 and Path(output_csv).is_file(),
        returncode=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:],
        output_files={"output_csv": output_csv},
    )


def parse_mmgbsa_scores(csv_path: str) -> list[dict]:
    """从 prime_mmgbsa CSV 解析每分子 ΔG。"""
    import csv as _csv
    if not Path(csv_path).is_file():
        return []
    rows = []
    with open(csv_path) as f:
        reader = _csv.DictReader(f)
        for r in reader:
            # prime_mmgbsa CSV 列：title, dG_Bind(/ΔG), ...
            title = r.get("title") or r.get("Title") or r.get("name") or ""
            dg = None
            for k in ("dG_Bind", "dG_bind", "Delta G", "MMGBSA_dG_Bind", "r_psp_MMGBSA_dG_Bind"):
                if k in r and r[k] not in (None, ""):
                    try:
                        dg = float(r[k])
                        break
                    except ValueError:
                        continue
            rows.append({"title": title, "mmgbsa_dg": dg})
    return rows


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------
def health(install_path: str = "/opt/schrodinger2023-3") -> dict:
    """检查本地安装与 license 可用性（所有核心 CLI）。"""
    tools = {}
    for name in ("glide", "ligprep", "prime_mmgbsa", "utilities/prepwizard"):
        bin_path = _schrodinger_bin(install_path, name)
        exists = Path(bin_path).is_file()
        version = ""
        err = None
        if exists:
            try:
                proc = subprocess.run([bin_path, "-v"], capture_output=True, text=True, timeout=20)
                version = (proc.stdout + proc.stderr).strip().splitlines()[-1] if (proc.stdout or proc.stderr) else ""
            except Exception as e:
                err = str(e)
        tools[name.split("/")[-1]] = {"path": bin_path, "installed": exists, "version": version, "error": err}

    all_ok = all(t["installed"] and not t["error"] for t in tools.values())
    return {"installed": True, "ok": all_ok, "install_path": install_path, "tools": tools}


# ---------------------------------------------------------------------------
# 端到端对接流水线（LigPrep → PrepWizard → Glide XP → MM-GBSA）
# ---------------------------------------------------------------------------
def end_to_end_dock(
    ligands_sdf: str,
    receptor_pdb: str,
    output_dir: str,
    install_path: str = "/opt/schrodinger2023-3",
    ph: float = 7.2,
    ph_threshold: float = 0.2,
    box_center: tuple[float, float, float] | None = None,
    box_size: tuple[int, int, int] = (20, 20, 20),
    precision: str = "XP",
    poses_per_lig: int = 10,
    postdock_minimize: bool = True,
    run_mmgbsa: bool = True,
    timeout_per_stage: int = 7200,
) -> dict:
    """完整 Schrödinger 对接流水线（LigPrep → PrepWizard → Glide XP → MM-GBSA）。

    Args:
        ligands_sdf: 配体 SDF 文件路径
        receptor_pdb: 受体 PDB 文件路径（如 VAV1 pocket）
        output_dir: 输出目录（将创建 docking/ 子目录）
        install_path: Schrödinger 安装根目录
        ph: pH 值
        box_center: Glide 对接盒中心 (x,y,z)；为 None 时从受体 PDB 质心自动计算
        box_size: 对接盒尺寸

    Returns:
        {glide_scores, mmgbsa_scores, all_ok, output_files, steps_log}
    """
    out = Path(output_dir) / "docking"
    out.mkdir(parents=True, exist_ok=True)
    steps_log: list[dict] = []

    # ---- 1. LigPrep 配体准备 ----
    step1_out = str(out / "ligands_ligprep.sdf")
    r1 = ligprep(ligands_sdf, step1_out, install_path=install_path, ph=ph, ph_threshold=ph_threshold)
    steps_log.append({"step": "ligprep", "ok": r1.ok, "returncode": r1.returncode})
    if not r1.ok:
        return {"glide_scores": [], "mmgbsa_scores": [], "all_ok": False, "output_files": {}, "steps_log": steps_log}

    # ---- 2. PrepWizard 受体准备 ----
    receptor_maegz = str(out / "receptor_prepwizard.maegz")
    r2 = prepwizard(receptor_pdb, receptor_maegz, install_path=install_path, ph=ph, ph_threshold=ph_threshold)
    steps_log.append({"step": "prepwizard", "ok": r2.ok, "returncode": r2.returncode})
    if not r2.ok:
        return {"glide_scores": [], "mmgbsa_scores": [], "all_ok": False,
                "output_files": {"ligands_sdf": step1_out}, "steps_log": steps_log}

    # ---- 3. Glide 网格生成 ----
    # 自动计算 box_center
    if box_center is None:
        box_center = _compute_pdb_centroid(receptor_pdb)
        logger.info("Auto box_center from PDB centroid: %s", box_center)

    grid_zip = str(out / "grid.zip")
    r3 = glide_grid(receptor_maegz, grid_zip, box_center, box_size, install_path=install_path)
    steps_log.append({"step": "glide_grid", "ok": r3.ok, "returncode": r3.returncode})
    if not r3.ok:
        return {"glide_scores": [], "mmgbsa_scores": [], "all_ok": False,
                "output_files": {"ligands_sdf": step1_out, "receptor_maegz": receptor_maegz}, "steps_log": steps_log}

    # ---- 4. Glide 对接 ----
    pose_maegz = str(out / f"poses_{precision.lower()}.maegz")
    r4 = glide_dock(
        step1_out, grid_zip, pose_maegz,
        install_path=install_path,
        precision=precision,
        poses_per_lig=poses_per_lig,
        postdock_minimize=postdock_minimize,
        timeout=timeout_per_stage,
    )
    steps_log.append({"step": f"glide_{precision.lower()}_dock", "ok": r4.ok, "returncode": r4.returncode})
    glide_scores: list[dict] = []
    if r4.ok and Path(pose_maegz).is_file():
        glide_scores = parse_glide_xp_scores(pose_maegz, install_path=install_path)
    else:
        logger.warning("Glide %s dock failed; skipping MM-GBSA", precision)
        return {
            "glide_scores": glide_scores,
            "mmgbsa_scores": [],
            "all_ok": False,
            "precision": precision.upper(),
            "output_files": {
                "ligands_sdf": step1_out,
                "receptor_maegz": receptor_maegz,
                "grid_zip": grid_zip,
            },
            "steps_log": steps_log,
        }

    # ---- 5. Prime MM-GBSA 重打分（可选）----
    mmgbsa_scores: list[dict] = []
    mmgbsa_csv = str(out / "mmgbsa_scores.csv")
    if run_mmgbsa:
        r5 = prime_mmgbsa(pose_maegz, mmgbsa_csv, install_path=install_path, receptor_maegz=receptor_maegz, timeout=timeout_per_stage)
        steps_log.append({"step": "prime_mmgbsa", "ok": r5.ok, "returncode": r5.returncode})
        mmgbsa_scores = parse_mmgbsa_scores(mmgbsa_csv) if r5.ok else []
    else:
        steps_log.append({"step": "prime_mmgbsa", "ok": True, "skipped": True})

    all_ok = all(s.get("ok") for s in steps_log if not s.get("skipped"))
    return {
        "glide_scores": glide_scores,
        "mmgbsa_scores": mmgbsa_scores,
        "all_ok": all_ok,
        "precision": precision.upper(),
        "output_files": {
            "ligands_sdf": step1_out,
            "receptor_maegz": receptor_maegz,
            "grid_zip": grid_zip,
            "poses_maegz": pose_maegz,
            "mmgbsa_csv": mmgbsa_csv,
        },
        "steps_log": steps_log,
    }


def _compute_pdb_centroid(pdb_path: str) -> tuple[float, float, float]:
    """从 PDB 文件所有重原子（非 H）坐标计算质心。"""
    import statistics as _stats
    xs, ys, zs = [], [], []
    with open(pdb_path) as f:
        for line in f:
            if line.startswith(("ATOM  ", "HETATM")):
                elem = line[76:78].strip()
                if elem and elem.upper() == "H":
                    continue
                try:
                    xs.append(float(line[30:38]))
                    ys.append(float(line[38:46]))
                    zs.append(float(line[46:54]))
                except ValueError:
                    continue
    if not xs:
        logger.warning("No heavy atoms in PDB, using origin as box center")
        return (0.0, 0.0, 0.0)
    return (_stats.mean(xs), _stats.mean(ys), _stats.mean(zs))
