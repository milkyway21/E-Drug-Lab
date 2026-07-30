#!/usr/bin/env python3
"""ALLIN 持续学习：复用 E43 R0/R1/R2，新训 R3，并对各轮库内相似分子做 GLARE 排名。

协议对齐 run_e43_progressive_rl.py：
  R0 = 专利 label_active∈{0,1}（已有）
  R1 = R0 + 第一轮 13 实体（已有）
  R2 = R1 + 第二轮 19 实体（已有）
  R3 = R2 + 第三轮 6 实体真标签（新训）

排名评测（核心）：
  轮 k∈{1,2,3}：用 model_R{k-1} 在当轮全库上 query，
  对每个实验分子的库内相似物记录 glare_rank + carsi_rank。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/data/ye/e-drug-lab/backend")
from app.services.conda_runner import conda_run

# ── 路径 ──
E43_DIR = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e43_progressive"
)
OUTPUT_DIR = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/allin_progressive"
)
ALLIN_DATA = Path("/data/ye/ALLIN/data")
SIM_DIR = OUTPUT_DIR / "similarity"
RANK_DIR = OUTPUT_DIR / "ranks"
LOG_DIR = OUTPUT_DIR / "logs"

for d in (OUTPUT_DIR, SIM_DIR, RANK_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── 标签 ──
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
# 图中记录的 MolFactory / Carsi ID（第三轮库 ID）
R3_FIGURE_SIMILAR = {
    "0230475": 4850, "0230476": 8376, "0230976": 4402,
    "0230488": 603, "0230493": 2627, "0230991": 5340,
}
R3_APPENDIX_IDS = ["LXC-306"]  # 无标签，不进训练

LIB_PATHS = {
    1: ALLIN_DATA / "第一轮生成分子库.csv",
    2: ALLIN_DATA / "第二轮生成分子库.csv",
    3: ALLIN_DATA / "第三轮生成分子库.csv",
}
ENTITY_DIRS = {
    1: ALLIN_DATA / "第一轮分子生成15个实体分子",
    2: ALLIN_DATA / "第二轮动力学指导的分子生成",
    3: ALLIN_DATA / "第三轮限制范围的分子生成",
}

TRAIN_ARGS = [
    "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "train",
    "--epochs", "50", "--ensemble", "3", "--batch_size", "64",
    "--strategy", "grpo", "--l2_lambda", "3e-4", "--lr", "3e-4", "--disable-ig",
]
PYTHONPATH_ENV = {"PYTHONPATH": "/data/ye/e-drug-lab/backend"}


def _canon(smi: str) -> str:
    from rdkit import Chem
    mol = Chem.MolFromSmiles(str(smi))
    if mol is None:
        return ""
    return Chem.MolToSmiles(Chem.RemoveHs(mol))


def _morgan_fp(smi: str, nbits: int = 2048):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    mol = Chem.MolFromSmiles(str(smi))
    if mol is None:
        return None
    mol = Chem.RemoveHs(mol)
    return AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=nbits)


def _tanimoto(fp_a, fp_b) -> float:
    from rdkit import DataStructs
    return float(DataStructs.TanimotoSimilarity(fp_a, fp_b))


def load_sdf_smiles(sdf_path: Path) -> str:
    from rdkit import Chem
    suppl = Chem.SDMolSupplier(str(sdf_path), removeHs=False)
    for mol in suppl:
        if mol is None:
            continue
        return Chem.MolToSmiles(Chem.RemoveHs(mol))
    return ""


def dedup_records(existing, new_records):
    from rdkit import Chem
    seen = set()
    for r in existing:
        mol = Chem.MolFromSmiles(r["smiles"])
        if mol:
            seen.add(Chem.MolToSmiles(mol))
    added = 0
    for r in new_records:
        mol = Chem.MolFromSmiles(r["smiles"])
        if mol:
            can = Chem.MolToSmiles(mol)
            if can not in seen:
                seen.add(can)
                existing.append({
                    "smiles": can,
                    "label": r["label"],
                    "weight": r["weight"],
                })
                added += 1
    return added


# ════════════════════════════════════════════════════════════════
# Step 0: 复用 E43 权重 + 构建 R3 累积集
# ════════════════════════════════════════════════════════════════

def ensure_e43_links():
    for name in ("R0", "R1", "R2"):
        src_ckpt = E43_DIR / f"model_{name}.pt"
        dst_ckpt = OUTPUT_DIR / f"model_{name}.pt"
        if not src_ckpt.exists():
            raise FileNotFoundError(f"E43 checkpoint missing: {src_ckpt}")
        if not dst_ckpt.exists():
            dst_ckpt.symlink_to(src_ckpt)
        src_data = E43_DIR / f"dataset_{name}.json"
        dst_data = OUTPUT_DIR / f"dataset_{name}.json"
        if src_data.exists() and not dst_data.exists():
            dst_data.write_text(src_data.read_text())


def load_r3_entity_records(include_unlabeled: bool = False):
    records = []
    for mid, label in R3_LABELS.items():
        sdf = ENTITY_DIRS[3] / f"{mid}.sdf"
        smi = load_sdf_smiles(sdf)
        if not smi:
            raise RuntimeError(f"Cannot read SMILES from {sdf}")
        records.append({
            "smiles": smi,
            "label": label,
            "weight": 5.0 if label == 1 else 1.0,
            "mol_id": mid,
        })
    if include_unlabeled:
        for mid in R3_APPENDIX_IDS:
            sdf = ENTITY_DIRS[3] / f"{mid}.sdf"
            smi = load_sdf_smiles(sdf)
            if smi:
                records.append({
                    "smiles": smi,
                    "label": None,
                    "weight": 0.0,
                    "mol_id": mid,
                })
    return records


def build_dataset_r3():
    r2_path = OUTPUT_DIR / "dataset_R2.json"
    if not r2_path.exists():
        r2_path = E43_DIR / "dataset_R2.json"
    base = json.loads(r2_path.read_text())
    r3_recs = load_r3_entity_records(include_unlabeled=False)
    recs = [dict(r) for r in base]
    added = dedup_records(recs, r3_recs)
    out = OUTPUT_DIR / "dataset_R3.json"
    out.write_text(json.dumps(recs, indent=2))
    n_pos = sum(1 for r in recs if r["label"] == 1)
    meta = {
        "n_total": len(recs),
        "n_positive": n_pos,
        "n_added_r3": added,
        "r3_labels": R3_LABELS,
        "excluded_unlabeled": R3_APPENDIX_IDS,
        "base": str(r2_path),
    }
    (OUTPUT_DIR / "dataset_R3_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False)
    )
    print(f"  dataset_R3: {len(recs)} mols ({n_pos} pos, +{added} from R3)")
    return out, recs


def train_r3(data_path: Path):
    ckpt = OUTPUT_DIR / "model_R3.pt"
    if ckpt.exists():
        print(f"  SKIP model_R3: exists ({ckpt})")
        return ckpt
    print(f"  Training model_R3 -> {ckpt}")
    proc = conda_run(
        "diffgui_new",
        TRAIN_ARGS + ["--ckpt", str(ckpt), "--data", str(data_path)],
        extra_env=PYTHONPATH_ENV,
    )
    log = LOG_DIR / "train_R3.log"
    log.write_text(
        f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n",
        encoding="utf-8",
    )
    if not ckpt.exists():
        raise RuntimeError(f"R3 training failed; see {log}")
    try:
        result_line = proc.stdout.strip().splitlines()[-1]
        print(f"  Train OK: {result_line[:200]}")
    except Exception:
        print(f"  Train finished; checkpoint exists. Log: {log}")
    return ckpt


# ════════════════════════════════════════════════════════════════
# Step 1: 相似对
# ════════════════════════════════════════════════════════════════

def load_library(round_k: int) -> pd.DataFrame:
    df = pd.read_csv(LIB_PATHS[round_k])
    df["csv_id"] = df["ID"].astype(int)
    # ID 即为按 CarsiScore 的名次（越负越好，ID 越小）
    df["carsi_rank"] = df["csv_id"]
    df["smiles_noH"] = df["smiles"].map(_canon)
    return df


def top1_similar(entity_smi: str, lib_df: pd.DataFrame, topk: int = 1):
    fp_q = _morgan_fp(entity_smi)
    if fp_q is None:
        return []
    # precompute if missing
    if "_fp" not in lib_df.columns:
        fps = []
        for smi in lib_df["smiles_noH"]:
            fps.append(_morgan_fp(smi) if smi else None)
        lib_df["_fp"] = fps
    scores = []
    for i, fp in enumerate(lib_df["_fp"]):
        if fp is None:
            continue
        scores.append((i, _tanimoto(fp_q, fp)))
    scores.sort(key=lambda x: -x[1])
    out = []
    for i, sim in scores[:topk]:
        row = lib_df.iloc[i]
        out.append({
            "similar_csv_id": int(row["csv_id"]),
            "tanimoto": float(sim),
            "similar_smiles": row["smiles_noH"],
            "CarsiScore": float(row["CarsiScore"]) if pd.notna(row["CarsiScore"]) else None,
            "RTMScore": float(row["RTMScore"]) if pd.notna(row["RTMScore"]) else None,
            "carsi_rank": int(row["carsi_rank"]),
        })
    return out


def build_round1_pairs():
    """优先用 molfactory similarity_pairs + wetlab 对照表。"""
    pairs_path = Path("/data/ye/e-drug-lab/molfactory/similarity_pairs_noH_all.csv")
    wet_path = Path(
        "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
        "glare_e32_paper_al_20260630/wetlab_13_ranking/wetlab_13_similar_ranking.csv"
    )
    r1_csv = Path(
        "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
        "glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
    )
    r1_df = pd.read_csv(r1_csv)
    wet = pd.read_csv(wet_path) if wet_path.exists() else None
    sp = pd.read_csv(pairs_path)

    lib = load_library(1)
    rows = []
    for _, er in r1_df.iterrows():
        mid = str(er["SDF_ID"])
        label = 1 if mid in R1_POSITIVE_IDS else 0
        entity_smi = _canon(er["SMILES"])

        # wetlab 表
        wet_hit = None
        if wet is not None:
            m = wet[wet["wetlab_id"].astype(str) == mid]
            if len(m):
                wet_hit = m.iloc[0]

        # similarity_pairs top-1
        sp_hit = sp[
            (sp["excel_id"].astype(str) == mid) & (sp["similarity_rank_for_excel"] == 1)
        ]
        similar_csv_id = None
        tanimoto = None
        similar_smi = None
        source = None
        if len(sp_hit):
            h = sp_hit.iloc[0]
            similar_csv_id = int(h["csv_id"])
            tanimoto = float(h["tanimoto_morgan_r2_2048_noH"])
            similar_smi = str(h["csv_smiles_noH_canonical"])
            source = "similarity_pairs_noH_all"
        elif wet_hit is not None:
            mid_str = str(wet_hit["molfactory_id"]).replace("MolFactory_", "")
            similar_csv_id = int(mid_str)
            tanimoto = float(wet_hit["tanimoto"])
            similar_smi = _canon(wet_hit["canonical_smiles"])
            source = "wetlab_13_similar_ranking"
        else:
            top = top1_similar(entity_smi, lib, topk=1)
            if top:
                similar_csv_id = top[0]["similar_csv_id"]
                tanimoto = top[0]["tanimoto"]
                similar_smi = top[0]["similar_smiles"]
                source = "computed_tanimoto_top1"

        lib_row = lib[lib["csv_id"] == similar_csv_id]
        carsi_rank = int(lib_row.iloc[0]["carsi_rank"]) if len(lib_row) else None
        carsi = float(lib_row.iloc[0]["CarsiScore"]) if len(lib_row) else None
        rtm = float(lib_row.iloc[0]["RTMScore"]) if len(lib_row) else None
        if similar_smi is None and len(lib_row):
            similar_smi = lib_row.iloc[0]["smiles_noH"]

        rows.append({
            "round": 1,
            "ref_id": mid,
            "label": label,
            "ref_smiles": entity_smi,
            "similar_csv_id": similar_csv_id,
            "tanimoto": tanimoto,
            "similar_smiles": similar_smi,
            "carsi_rank": carsi_rank,
            "CarsiScore": carsi,
            "RTMScore": rtm,
            "pair_source": source,
        })
    out = SIM_DIR / "pairs_round1.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  pairs_round1: {len(rows)} -> {out}")
    return out


def build_round2_pairs():
    lib = load_library(2)
    tracking = Path(
        "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
        "glare_e41_al/r2_smiles_tracking.json"
    )
    if tracking.exists():
        r2_map = json.loads(tracking.read_text())["molecules"]
    else:
        r2_map = {}
        for sdf in sorted(ENTITY_DIRS[2].glob("*.sdf")):
            r2_map[sdf.stem] = load_sdf_smiles(sdf)

    rows = []
    for mid, smi in r2_map.items():
        label = R2_LABELS.get(mid, 0)
        entity_smi = _canon(smi) or smi
        top = top1_similar(entity_smi, lib, topk=3)
        if not top:
            continue
        best = top[0]
        rows.append({
            "round": 2,
            "ref_id": mid,
            "label": label,
            "ref_smiles": entity_smi,
            "similar_csv_id": best["similar_csv_id"],
            "tanimoto": best["tanimoto"],
            "similar_smiles": best["similar_smiles"],
            "carsi_rank": best["carsi_rank"],
            "CarsiScore": best["CarsiScore"],
            "RTMScore": best["RTMScore"],
            "pair_source": "computed_tanimoto_top1",
            "top3_csv_ids": ",".join(str(t["similar_csv_id"]) for t in top),
            "top3_tanimoto": ",".join(f"{t['tanimoto']:.4f}" for t in top),
        })
    out = SIM_DIR / "pairs_round2.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  pairs_round2: {len(rows)} -> {out}")
    return out


def build_round3_pairs():
    lib = load_library(3)
    rows = []
    for mid, label in R3_LABELS.items():
        smi = load_sdf_smiles(ENTITY_DIRS[3] / f"{mid}.sdf")
        entity_smi = _canon(smi)
        fig_id = R3_FIGURE_SIMILAR[mid]
        fig_row = lib[lib["csv_id"] == fig_id]
        top = top1_similar(entity_smi, lib, topk=1)
        tanimoto_to_fig = None
        if len(fig_row):
            fp_e = _morgan_fp(entity_smi)
            fp_f = _morgan_fp(fig_row.iloc[0]["smiles_noH"])
            if fp_e is not None and fp_f is not None:
                tanimoto_to_fig = _tanimoto(fp_e, fp_f)
            similar_smi = fig_row.iloc[0]["smiles_noH"]
            carsi = float(fig_row.iloc[0]["CarsiScore"])
            rtm = float(fig_row.iloc[0]["RTMScore"])
            carsi_rank = int(fig_row.iloc[0]["carsi_rank"])
        else:
            similar_smi = None
            carsi = rtm = carsi_rank = None

        rows.append({
            "round": 3,
            "ref_id": mid,
            "label": label,
            "ref_smiles": entity_smi,
            "similar_csv_id": fig_id,
            "tanimoto": tanimoto_to_fig,
            "similar_smiles": similar_smi,
            "carsi_rank": carsi_rank,
            "CarsiScore": carsi,
            "RTMScore": rtm,
            "pair_source": "figure_molfactory_id",
            "tanimoto_top1_csv_id": top[0]["similar_csv_id"] if top else None,
            "tanimoto_top1": top[0]["tanimoto"] if top else None,
            "tanimoto_top1_smiles": top[0]["similar_smiles"] if top else None,
        })

    # appendix LXC-306
    for mid in R3_APPENDIX_IDS:
        smi = load_sdf_smiles(ENTITY_DIRS[3] / f"{mid}.sdf")
        entity_smi = _canon(smi)
        top = top1_similar(entity_smi, lib, topk=1)
        if not top:
            continue
        best = top[0]
        rows.append({
            "round": 3,
            "ref_id": mid,
            "label": None,
            "ref_smiles": entity_smi,
            "similar_csv_id": best["similar_csv_id"],
            "tanimoto": best["tanimoto"],
            "similar_smiles": best["similar_smiles"],
            "carsi_rank": best["carsi_rank"],
            "CarsiScore": best["CarsiScore"],
            "RTMScore": best["RTMScore"],
            "pair_source": "appendix_unlabeled_tanimoto_top1",
            "tanimoto_top1_csv_id": best["similar_csv_id"],
            "tanimoto_top1": best["tanimoto"],
            "tanimoto_top1_smiles": best["similar_smiles"],
        })

    out = SIM_DIR / "pairs_round3.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"  pairs_round3: {len(rows)} -> {out}")
    return out


# ════════════════════════════════════════════════════════════════
# Step 2: GLARE 全库 query + 排名
# ════════════════════════════════════════════════════════════════

def prepare_query_json(round_k: int) -> Path:
    lib = load_library(round_k)
    records = []
    for _, row in lib.iterrows():
        smi = row["smiles_noH"]
        if not smi:
            continue
        records.append({
            "smiles": smi,
            "molecule_id": str(int(row["csv_id"])),
        })
    path = OUTPUT_DIR / f"query_lib_round{round_k}.json"
    path.write_text(json.dumps(records))
    print(f"  query json round{round_k}: {len(records)} -> {path}")
    return path


def run_glare_query(ckpt: Path, smiles_json: Path, tag: str) -> list:
    out_json = RANK_DIR / f"glare_full_{tag}.json"
    if out_json.exists():
        print(f"  SKIP query {tag}: cache exists")
        return json.loads(out_json.read_text()).get("ranked", [])

    print(f"  Querying {ckpt.name} on {smiles_json.name} ...")
    proc = conda_run(
        "diffgui_new",
        [
            "python", "-m", "app.pipelines.vav1_rl.glare_gnn_cli", "query",
            "--ckpt", str(ckpt),
            "--smiles", str(smiles_json),
            "--ensemble", "3",
        ],
        extra_env=PYTHONPATH_ENV,
    )
    (LOG_DIR / f"query_{tag}.log").write_text(
        f"STDOUT_TAIL:\n{proc.stdout[-8000:]}\n\nSTDERR_TAIL:\n{proc.stderr[-4000:]}\n",
        encoding="utf-8",
    )
    try:
        qr = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(
            f"query {tag} parse failed: {e}; see {LOG_DIR / f'query_{tag}.log'}"
        ) from e
    if not qr.get("ok"):
        raise RuntimeError(f"query {tag} failed: {qr}")
    out_json.write_text(json.dumps(qr, indent=2))
    print(f"  Query {tag}: n={qr.get('n')} -> {out_json}")
    return qr["ranked"]


def build_rank_lookup(ranked: list) -> dict:
    """canonical smiles -> glare_rank; also molecule_id -> glare_rank."""
    by_smi = {}
    by_id = {}
    for r in ranked:
        smi = r.get("smiles") or r.get("smiles_raw")
        if smi:
            by_smi[_canon(smi) or smi] = int(r["glare_rank"])
        mid = r.get("molecule_id")
        if mid is not None and str(mid) != "None":
            by_id[str(mid)] = int(r["glare_rank"])
    return {"by_smi": by_smi, "by_id": by_id}


def rank_round(round_k: int, model_name: str, pairs_csv: Path):
    ckpt = OUTPUT_DIR / f"model_{model_name}.pt"
    qjson = prepare_query_json(round_k)
    ranked = run_glare_query(ckpt, qjson, tag=f"R{round_k-1}_lib{round_k}")
    lookup = build_rank_lookup(ranked)
    pairs = pd.read_csv(pairs_csv)
    out_rows = []
    for _, p in pairs.iterrows():
        if pd.isna(p.get("label")) and p["ref_id"] in R3_APPENDIX_IDS:
            # still include appendix but mark
            pass
        sid = p["similar_csv_id"]
        if pd.isna(sid):
            continue
        sid = int(sid)
        smi = p.get("similar_smiles")
        glare_rank = lookup["by_id"].get(str(sid))
        if glare_rank is None and isinstance(smi, str) and smi:
            glare_rank = lookup["by_smi"].get(_canon(smi) or smi)
        out_rows.append({
            "ref_id": p["ref_id"],
            "label": p["label"] if not pd.isna(p["label"]) else "",
            "similar_csv_id": sid,
            "tanimoto": p.get("tanimoto"),
            "carsi_rank": p.get("carsi_rank"),
            f"glare_rank_{model_name}": glare_rank,
            "CarsiScore": p.get("CarsiScore"),
            "RTMScore": p.get("RTMScore"),
            "pair_source": p.get("pair_source"),
            "similar_smiles": smi,
            "ref_smiles": p.get("ref_smiles"),
            "glare_model": model_name,
            "library_round": round_k,
            "library_size": len(ranked),
        })
    out = RANK_DIR / f"rank_round{round_k}.csv"
    pd.DataFrame(out_rows).to_csv(out, index=False)
    print(f"  rank_round{round_k}: {len(out_rows)} -> {out}")
    return out


def write_summary(rank_paths: dict):
    lines = []
    lines.append("# ALLIN 持续学习 + 各轮相似分子排名\n")
    lines.append("## 权重与数据\n")
    lines.append("| 模型 | 训练数据 | 权重路径 |")
    lines.append("|------|----------|----------|")
    lines.append(
        f"| R0 | 专利 label_active∈{{0,1}} (n=352) | "
        f"`{OUTPUT_DIR / 'model_R0.pt'}` → E43 |"
    )
    lines.append(
        f"| R1 | R0 + 第一轮 13 实体 | `{OUTPUT_DIR / 'model_R1.pt'}` → E43 |"
    )
    lines.append(
        f"| R2 | R1 + 第二轮 19 实体 | `{OUTPUT_DIR / 'model_R2.pt'}` → E43 |"
    )
    lines.append(
        f"| R3 | R2 + 第三轮 6 实体真标签 | `{OUTPUT_DIR / 'model_R3.pt'}`（新训） |"
    )
    lines.append("")
    lines.append("### R3 标签")
    lines.append("- 活性(1): `0230475, 0230476, 0230976`")
    lines.append("- 非活性(0): `0230488, 0230493, 0230991`")
    lines.append("- `LXC-306`: 无标签，不进训练集（附录相似物查询）")
    lines.append("")
    lines.append("训练配置与 E43 一致：`glare_gnn_cli` / GRPO / ens=3 / epochs=50 / `disable_ig=True`。")
    lines.append("")
    lines.append("## 排名协议\n")
    lines.append("对轮次 k∈{1,2,3}：加载 `model_R{k-1}`，对当轮全库 GLARE query，")
    lines.append("取实验分子的库内相似物的 `glare_rank`，并对照 `carsi_rank`（库 `ID`）。")
    lines.append("")

    for k, path in sorted(rank_paths.items()):
        df = pd.read_csv(path)
        model = f"R{k-1}"
        lines.append(f"## 第 {k} 轮（模型 {model} → 库 {k}）\n")
        # filter labeled
        labeled = df[df["label"].astype(str).isin(["0", "1", "0.0", "1.0"])].copy()
        if len(labeled) == 0:
            labeled = df.copy()
        labeled["label"] = labeled["label"].astype(float).astype(int)
        gcol = f"glare_rank_{model}"
        if gcol not in labeled.columns:
            # fallback
            gcols = [c for c in labeled.columns if c.startswith("glare_rank_")]
            gcol = gcols[0] if gcols else None
        lines.append("| ref_id | label | similar_csv_id | tanimoto | carsi_rank | glare_rank |")
        lines.append("|--------|-------|----------------|----------|------------|------------|")
        for _, r in labeled.sort_values(["label", gcol] if gcol else ["label"]).iterrows():
            gr = int(r[gcol]) if gcol and pd.notna(r.get(gcol)) else ""
            tn = f"{float(r['tanimoto']):.3f}" if pd.notna(r.get("tanimoto")) else ""
            cr = int(r["carsi_rank"]) if pd.notna(r.get("carsi_rank")) else ""
            lines.append(
                f"| {r['ref_id']} | {int(r['label'])} | {int(r['similar_csv_id'])} | "
                f"{tn} | {cr} | {gr} |"
            )
        if gcol and len(labeled):
            pos = labeled[labeled["label"] == 1][gcol].dropna()
            neg = labeled[labeled["label"] == 0][gcol].dropna()
            lines.append("")
            if len(pos):
                lines.append(f"- 活性相似物 glare 均值名次: **#{pos.mean():.0f}** (n={len(pos)})")
            if len(neg):
                lines.append(f"- 非活性相似物 glare 均值名次: **#{neg.mean():.0f}** (n={len(neg)})")
            if len(pos) and len(neg):
                better = "活性整体更靠前" if pos.mean() < neg.mean() else "非活性整体更靠前/无优势"
                lines.append(f"- 结论: {better}（相对纯 Carsi：见表内 carsi_rank）")
            cpos = labeled[labeled["label"] == 1]["carsi_rank"].dropna()
            cneg = labeled[labeled["label"] == 0]["carsi_rank"].dropna()
            if len(cpos) and len(cneg):
                lines.append(
                    f"- Carsi 对照: 活性均值 #{cpos.mean():.0f} vs 非活性均值 #{cneg.mean():.0f}"
                )
        lines.append("")
        lines.append(f"原始表: `{path}`")
        lines.append("")

    lines.append("## 与 E43 的关系\n")
    lines.append("- R0/R1/R2 权重与 `dataset_R*` **直接复用** `glare_e43_progressive/`（软链）。")
    lines.append("- 本实验新增 `dataset_R3.json` + `model_R3.pt`，并完成三轮库内相似物排名交付。")
    lines.append("- 不使用 293B rl_rounds smoke checkpoint；不把 XGBoost 当作 GLARE 持续学习。")
    lines.append("")

    out = OUTPUT_DIR / "RANK_SUMMARY.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  RANK_SUMMARY -> {out}")
    return out


def main():
    print("=" * 60)
    print("  ALLIN progressive RL + similarity ranking")
    print("=" * 60)

    print("\n[0] Ensure E43 links + build/train R3")
    ensure_e43_links()
    data_r3, _ = build_dataset_r3()
    train_r3(data_r3)

    print("\n[1] Build similarity pairs")
    p1 = build_round1_pairs()
    p2 = build_round2_pairs()
    p3 = build_round3_pairs()

    print("\n[2] GLARE full-library ranking")
    r1 = rank_round(1, "R0", p1)
    r2 = rank_round(2, "R1", p2)
    r3 = rank_round(3, "R2", p3)

    print("\n[3] Write summary")
    write_summary({1: r1, 2: r2, 3: r3})

    print("\n✅ Done:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
