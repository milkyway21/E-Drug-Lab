#!/usr/bin/env python3
"""ALLIN = ginl_pc_gl[_md] 持续学习：R0(专利352)→R1(+13)→R2(+19)→R3(+6) + 各轮相似物排名。

与纯 ginl 的 allin_progressive/ 分离。
默认产出 allin_pc_gl_progressive/；可用 --architecture / --output-dir 覆盖。
新库 Glide SP 未齐时勿开 --fail-on-low-coverage。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/data/ye/e-drug-lab/backend")
sys.path.insert(0, str(ROOT))

PY = "/home/user/anaconda3/envs/diffgui_new/bin/python"
DEFAULT_OUTPUT = ROOT / "outputs/vav1_rl_project/validation/allin_pc_gl_progressive"
OLD_SIM = ROOT / "outputs/vav1_rl_project/validation/allin_progressive/similarity"
ALLIN_DATA = Path("/data/ye/ALLIN/data")

R2_LABELS = {
    "0185078(1)": 1, "0228300": 1, "0230953": 1, "0228423": 1, "LXC-201": 1,
    "0228274": 0, "0228325": 0, "0228413": 0, "0228419": 0, "0228429": 0,
    "0230500": 0, "0230853": 0, "0230915": 0, "0230922": 0, "0230994": 0,
    "0231000": 0, "0376960": 0, "LXC-206": 0, "LXC-305": 0,
}
R1_POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}
R3_LABELS = {
    "0230475": 1, "0230476": 1, "0230976": 1,
    "0230488": 0, "0230493": 0, "0230991": 0,
}
R3_APPENDIX = ["LXC-306"]
ENTITY3 = ALLIN_DATA / "第三轮限制范围的分子生成"

# 运行时由 main() 注入
OUTPUT_DIR = DEFAULT_OUTPUT
SIM_DIR = OUTPUT_DIR / "similarity"
RANK_DIR = OUTPUT_DIR / "ranks"
LOG_DIR = OUTPUT_DIR / "logs"
ARCH = "ginl_pc_gl"
FUSION_TYPE = "fixed_residual"
MD_ADV_ETA = 0.0
ENABLE_MD = False
TRAIN_MD_ADAPTER_ONLY = False
FAIL_ON_LOW_COVERAGE = False
MIN_GLIDE_COVERAGE = 0.0


def _env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")
    env.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
    return env


def _canon(smi: str) -> str:
    from rdkit import Chem
    mol = Chem.MolFromSmiles(str(smi))
    if mol is None:
        return ""
    return Chem.MolToSmiles(Chem.RemoveHs(mol))


def load_sdf_smiles(path: Path) -> str:
    from rdkit import Chem
    for mol in Chem.SDMolSupplier(str(path), removeHs=False):
        if mol is not None:
            return Chem.MolToSmiles(Chem.RemoveHs(mol))
    return ""


def dedup_append(existing, new_recs):
    from rdkit import Chem
    seen = set()
    for r in existing:
        m = Chem.MolFromSmiles(r["smiles"])
        if m:
            seen.add(Chem.MolToSmiles(m))
    added = 0
    for r in new_recs:
        m = Chem.MolFromSmiles(r["smiles"])
        if not m:
            continue
        can = Chem.MolToSmiles(m)
        if can in seen:
            continue
        seen.add(can)
        existing.append({
            "smiles": can,
            "label": int(r["label"]),
            "weight": float(r["weight"]),
            "molecule_id": r.get("molecule_id") or r.get("mol_id"),
        })
        added += 1
    return added


def load_patent_352():
    df = pd.read_csv(
        ROOT / "outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
    )
    id_col = "molecule_id" if "molecule_id" in df.columns else "SDF_ID"
    smi_col = "canonical_smiles" if "canonical_smiles" in df.columns else "smiles"
    recs = []
    for _, row in df.iterrows():
        lab = int(row["label_active"])
        if lab not in (0, 1):
            continue
        smi = _canon(row[smi_col])
        if not smi:
            continue
        mid = str(row[id_col])
        recs.append({
            "smiles": smi,
            "label": lab,
            "weight": 5.0 if lab == 1 else 1.0,
            "molecule_id": mid,
        })
    return recs


def load_r1():
    df = pd.read_csv(
        ROOT / "outputs/vav1_rl_project/validation/"
        "glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
    )
    recs = []
    for _, row in df.iterrows():
        mid = str(row["SDF_ID"])
        lab = 1 if mid in R1_POSITIVE_IDS else 0
        recs.append({
            "smiles": _canon(row["SMILES"]) or str(row["SMILES"]),
            "label": lab,
            "weight": 5.0 if lab == 1 else 1.0,
            "molecule_id": mid,
        })
    return recs


def load_r2():
    tracking = (
        ROOT / "outputs/vav1_rl_project/validation/glare_e41_al/r2_smiles_tracking.json"
    )
    r2_map = json.loads(tracking.read_text())["molecules"]
    recs = []
    for mid, smi in r2_map.items():
        lab = R2_LABELS.get(mid, 0)
        recs.append({
            "smiles": _canon(smi) or smi,
            "label": lab,
            "weight": 5.0 if lab == 1 else 1.0,
            "molecule_id": mid,
        })
    return recs


def load_r3():
    recs = []
    for mid, lab in R3_LABELS.items():
        smi = load_sdf_smiles(ENTITY3 / f"{mid}.sdf")
        recs.append({
            "smiles": _canon(smi) or smi,
            "label": lab,
            "weight": 5.0 if lab == 1 else 1.0,
            "molecule_id": mid,
        })
    return recs


def build_datasets():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    patent = load_patent_352()
    r1, r2, r3 = load_r1(), load_r2(), load_r3()
    print(f"patent={len(patent)} r1={len(r1)} r2={len(r2)} r3={len(r3)}")
    datasets = {}
    for name, extra in [("R0", []), ("R1", r1), ("R2", r2), ("R3", r3)]:
        recs = [dict(r) for r in patent]
        # cumulative: R1 adds r1, R2 adds r1+r2, R3 adds r1+r2+r3
        if name in ("R1", "R2", "R3"):
            dedup_append(recs, r1)
        if name in ("R2", "R3"):
            dedup_append(recs, r2)
        if name == "R3":
            dedup_append(recs, r3)
        datasets[name] = recs
        path = OUTPUT_DIR / f"dataset_{name}.json"
        path.write_text(json.dumps(recs, indent=2))
        npos = sum(1 for r in recs if r["label"] == 1)
        print(f"  {name}: n={len(recs)} pos={npos} -> {path}")
    return datasets


def train_one(name: str, prev: Path | None = None):
    ckpt = OUTPUT_DIR / f"model_{name}.pt"
    data = OUTPUT_DIR / f"dataset_{name}.json"
    if ckpt.exists() and ckpt.stat().st_size > 1_000_000:
        print(f"SKIP train {name}: exists")
        return ckpt
    cmd = [
        PY, "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "train",
        "--ckpt", str(ckpt), "--data", str(data),
        "--epochs", "50", "--ensemble", "3", "--batch_size", "64",
        "--strategy", "grpo", "--l2_lambda", "3e-4", "--lr", "3e-4",
        "--disable-ig", "--architecture", ARCH,
        "--fusion_type", FUSION_TYPE,
        "--training_mode", "grpo_style_classifier_regularization",
        "--continual-strategy", "replay_anchor",
        "--min_glide_coverage", str(MIN_GLIDE_COVERAGE),
    ]
    if ENABLE_MD or ARCH.endswith("_md"):
        cmd += ["--enable-md", "--md_adv_eta", str(MD_ADV_ETA or 0.5)]
    if TRAIN_MD_ADAPTER_ONLY:
        cmd += ["--train-md-adapter-only"]
    if FAIL_ON_LOW_COVERAGE:
        cmd += ["--fail_on_low_coverage"]
    if prev and prev.exists():
        cmd += ["--prev", str(prev)]
    print(f"Training {name} arch={ARCH} ...", flush=True)
    p = subprocess.run(cmd, cwd=str(ROOT), env=_env(), capture_output=True, text=True, timeout=7200)
    (LOG_DIR / f"train_{name}.log").write_text(
        f"STDOUT:\n{p.stdout[-8000:]}\n\nSTDERR:\n{p.stderr[-4000:]}\n"
    )
    if not ckpt.exists():
        raise RuntimeError(f"train {name} failed; see {LOG_DIR / f'train_{name}.log'}")
    lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
    if lines:
        print(f"  {name}: {lines[-1][:200]}")
    return ckpt


def ensure_similarity():
    SIM_DIR.mkdir(parents=True, exist_ok=True)
    for k in (1, 2, 3):
        src = OLD_SIM / f"pairs_round{k}.csv"
        dst = SIM_DIR / f"pairs_round{k}.csv"
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text())
        if not dst.exists():
            raise FileNotFoundError(f"missing pairs {dst}; run old similarity builder first")
    return {k: SIM_DIR / f"pairs_round{k}.csv" for k in (1, 2, 3)}


def prepare_query_json(round_k: int) -> Path:
    lib_paths = {
        1: ALLIN_DATA / "第一轮生成分子库.csv",
        2: ALLIN_DATA / "第二轮生成分子库.csv",
        3: ALLIN_DATA / "第三轮生成分子库.csv",
    }
    df = pd.read_csv(lib_paths[round_k])
    records = []
    for _, row in df.iterrows():
        smi = _canon(row["smiles"])
        if not smi:
            continue
        mid = str(int(row["ID"]))
        records.append({"smiles": smi, "molecule_id": mid})
    path = OUTPUT_DIR / f"query_lib_round{round_k}.json"
    path.write_text(json.dumps(records))
    print(f"query round{round_k}: {len(records)}")
    return path


def run_query(ckpt: Path, smiles_json: Path, tag: str) -> list:
    RANK_DIR.mkdir(parents=True, exist_ok=True)
    out_json = RANK_DIR / f"glare_full_{tag}.json"
    if out_json.exists():
        print(f"SKIP query cache {tag}")
        return json.loads(out_json.read_text())["ranked"]
    cmd = [
        PY, "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", str(ckpt), "--smiles", str(smiles_json),
        "--ensemble", "3", "--architecture", ARCH,
    ]
    print(f"Query {tag} ...", flush=True)
    p = subprocess.run(cmd, cwd=str(ROOT), env=_env(), capture_output=True, text=True, timeout=7200)
    (LOG_DIR / f"query_{tag}.log").write_text(
        f"STDOUT_TAIL:\n{p.stdout[-6000:]}\n\nSTDERR_TAIL:\n{p.stderr[-3000:]}\n"
    )
    lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"query {tag} failed")
    qr = json.loads(lines[-1])
    if not qr.get("ok"):
        raise RuntimeError(f"query {tag}: {qr}")
    out_json.write_text(json.dumps(qr))
    return qr["ranked"]


def rank_round(round_k: int, model_name: str, pairs_csv: Path):
    ckpt = OUTPUT_DIR / f"model_{model_name}.pt"
    qjson = prepare_query_json(round_k)
    ranked = run_query(ckpt, qjson, f"{model_name}_lib{round_k}")
    by_id = {}
    by_smi = {}
    for r in ranked:
        if r.get("molecule_id") is not None:
            by_id[str(r["molecule_id"])] = int(r["glare_rank"])
            # also normalized 7-digit
            try:
                by_id[f"{int(r['molecule_id']):07d}"] = int(r["glare_rank"])
            except Exception:
                pass
        smi = r.get("smiles") or r.get("smiles_raw")
        if smi:
            by_smi[_canon(smi) or smi] = int(r["glare_rank"])

    pairs = pd.read_csv(pairs_csv)
    rows = []
    for _, p in pairs.iterrows():
        if pd.isna(p.get("similar_csv_id")):
            continue
        sid = int(p["similar_csv_id"])
        gr = by_id.get(str(sid)) or by_id.get(f"{sid:07d}")
        if gr is None and isinstance(p.get("similar_smiles"), str):
            gr = by_smi.get(_canon(p["similar_smiles"]) or p["similar_smiles"])
        rows.append({
            "ref_id": p["ref_id"],
            "label": p["label"] if not pd.isna(p.get("label")) else "",
            "similar_csv_id": sid,
            "tanimoto": p.get("tanimoto"),
            "carsi_rank": p.get("carsi_rank"),
            f"glare_rank_{model_name}": gr,
            "CarsiScore": p.get("CarsiScore"),
            "RTMScore": p.get("RTMScore"),
            "pair_source": p.get("pair_source"),
            "architecture": ARCH,
            "library_round": round_k,
            "library_size": len(ranked),
        })
    out = RANK_DIR / f"rank_round{round_k}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"rank_round{round_k}: {len(rows)} -> {out}")
    return out


def write_summary(rank_paths: dict):
    lines = [
        "# ALLIN（ginl_pc_gl）持续学习 + 各轮相似分子排名\n",
        "> **ALLIN** = 图 + 101D 理化 + Glide SP（`ginl_pc_gl`）。\n",
        "> 纯 `ginl` 基线见 `validation/allin_progressive/`（非 ALLIN）。\n",
        "## 权重\n",
        "| 模型 | 数据 | 架构 |",
        "|------|------|------|",
        "| R0 | 专利 label∈{0,1} n≈352 | ginl_pc_gl |",
        "| R1 | R0 + 第一轮 13 | ginl_pc_gl |",
        "| R2 | R1 + 第二轮 19 | ginl_pc_gl |",
        "| R3 | R2 + 第三轮 6 | ginl_pc_gl |",
        "",
        f"目录: `{OUTPUT_DIR}`",
        "",
        "第三轮全库已 Glide SP（≤30 核）；库1/库2 query 时 Glide 多为 mask=0。",
        "",
    ]
    for k, path in sorted(rank_paths.items()):
        df = pd.read_csv(path)
        model = f"R{k-1}"
        gcol = f"glare_rank_{model}"
        lines.append(f"## 第 {k} 轮（{model} → 库 {k}）\n")
        lines.append("| ref_id | label | similar_csv_id | tanimoto | carsi_rank | glare_rank |")
        lines.append("|--------|-------|----------------|----------|------------|------------|")
        lab = df[df["label"].astype(str).isin(["0", "1", "0.0", "1.0"])].copy()
        if len(lab) == 0:
            lab = df.copy()
        else:
            lab["label"] = lab["label"].astype(float).astype(int)
        for _, r in lab.iterrows():
            gr = int(r[gcol]) if gcol in r and pd.notna(r.get(gcol)) else ""
            tn = f"{float(r['tanimoto']):.3f}" if pd.notna(r.get("tanimoto")) else ""
            cr = int(r["carsi_rank"]) if pd.notna(r.get("carsi_rank")) else ""
            labv = int(r["label"]) if pd.notna(r.get("label")) and str(r["label"]) != "" else ""
            lines.append(
                f"| {r['ref_id']} | {labv} | {int(r['similar_csv_id'])} | {tn} | {cr} | {gr} |"
            )
        if gcol in lab.columns and len(lab):
            pos = lab[lab["label"] == 1][gcol].dropna()
            neg = lab[lab["label"] == 0][gcol].dropna()
            lines.append("")
            if len(pos):
                lines.append(f"- 活性相似物 ALLIN 均值名次: **#{pos.mean():.0f}** (n={len(pos)})")
            if len(neg):
                lines.append(f"- 非活性相似物 ALLIN 均值名次: **#{neg.mean():.0f}** (n={len(neg)})")
        lines.append(f"\n表: `{path}`\n")
    out = OUTPUT_DIR / "RANK_SUMMARY.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"SUMMARY -> {out}")


def main():
    global OUTPUT_DIR, SIM_DIR, RANK_DIR, LOG_DIR, ARCH, FUSION_TYPE
    global MD_ADV_ETA, ENABLE_MD, TRAIN_MD_ADAPTER_ONLY, FAIL_ON_LOW_COVERAGE, MIN_GLIDE_COVERAGE

    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=["all", "data", "train", "rank", "summary"])
    ap.add_argument("--architecture", default="ginl_pc_gl",
                    choices=["ginl_pc_gl", "ginl_pc_gl_md"])
    ap.add_argument("--fusion-type", default="fixed_residual",
                    choices=["fixed_residual", "learnable_gate"])
    ap.add_argument("--output-dir", default=None,
                    help="默认 validation/allin_pc_gl_progressive；MD 跑建议另目录")
    ap.add_argument("--enable-md", action="store_true", default=False)
    ap.add_argument("--md-adv-eta", type=float, default=0.5)
    ap.add_argument("--train-md-adapter-only", action="store_true", default=False)
    ap.add_argument("--min-glide-coverage", type=float, default=0.0)
    ap.add_argument("--fail-on-low-coverage", action="store_true", default=False)
    args = ap.parse_args()

    ARCH = args.architecture
    if args.enable_md and not ARCH.endswith("_md"):
        ARCH = "ginl_pc_gl_md"
    FUSION_TYPE = args.fusion_type
    ENABLE_MD = bool(args.enable_md or ARCH.endswith("_md"))
    MD_ADV_ETA = float(args.md_adv_eta)
    TRAIN_MD_ADAPTER_ONLY = bool(args.train_md_adapter_only)
    FAIL_ON_LOW_COVERAGE = bool(args.fail_on_low_coverage)
    MIN_GLIDE_COVERAGE = float(args.min_glide_coverage)

    if args.output_dir:
        OUTPUT_DIR = Path(args.output_dir)
    elif ARCH.endswith("_md"):
        OUTPUT_DIR = ROOT / "outputs/vav1_rl_project/validation/allin_pc_gl_md_progressive"
    else:
        OUTPUT_DIR = DEFAULT_OUTPUT
    SIM_DIR = OUTPUT_DIR / "similarity"
    RANK_DIR = OUTPUT_DIR / "ranks"
    LOG_DIR = OUTPUT_DIR / "logs"

    for d in (OUTPUT_DIR, SIM_DIR, RANK_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
    print(f"ARCH={ARCH} fusion={FUSION_TYPE} out={OUTPUT_DIR}", flush=True)

    if args.stage in ("all", "data"):
        build_datasets()
    if args.stage in ("all", "train"):
        build_datasets()
        c0 = train_one("R0")
        c1 = train_one("R1", prev=c0)
        c2 = train_one("R2", prev=c1)
        train_one("R3", prev=c2)
        import torch
        ck = torch.load(OUTPUT_DIR / "model_R0.pt", map_location="cpu", weights_only=False)
        print("R0 arch check:", ck.get("args", {}).get("architecture"),
              "use_glide", ck.get("args", {}).get("use_glide"),
              "has_schema", "feature_schema" in ck)
    if args.stage in ("all", "rank"):
        pairs = ensure_similarity()
        r1 = rank_round(1, "R0", pairs[1])
        r2 = rank_round(2, "R1", pairs[2])
        r3 = rank_round(3, "R2", pairs[3])
        write_summary({1: r1, 2: r2, 3: r3})
    if args.stage == "summary":
        write_summary({
            k: RANK_DIR / f"rank_round{k}.csv" for k in (1, 2, 3)
        })
    print("DONE", OUTPUT_DIR)


if __name__ == "__main__":
    main()
