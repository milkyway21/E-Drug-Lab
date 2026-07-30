#!/usr/bin/env python3
"""构建 GLARE 格式 actives.smi / inactives.smi，并生成 R2 分子追踪文件。

输出:
  data/VAV1/original/actives.smi    — 专利活性(309) + wet-lab活性(3) + R2全部(19)
  data/VAV1/original/inactives.smi  — 专利非活性(94) + wet-lab非活性(10) + swxds 250k
  r2_smiles_tracking.json           — R2 分子的 SMILES 映射，用于追踪发现
"""
import sys, os, json, pandas as pd
from pathlib import Path
from rdkit import Chem

OUTPUT_DIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al")
GLARE_DATA_DIR = Path("/data/ye/diffgui/third_party/GLARE/data/VAV1/original")
SWXDS_CSV = OUTPUT_DIR / "swxds_250k_smiles.csv"
PATENT_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
WETLAB_CSV = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv"
R2_SDF_DIR = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第二轮动力学指导的分子生成"
R1_SDF_DIR = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第一轮分子生成15个实体分子"

POSITIVE_IDS = {"0228390", "0228414", "LXC-106"}  # 3 wet-lab actives

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def extract_smiles_from_sdf(sdf_path):
    suppl = Chem.SDMolSupplier(sdf_path)
    if not suppl or len(suppl) == 0:
        return None
    mol = suppl[0]
    return Chem.MolToSmiles(mol) if mol else None

def main():
    GLARE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    active_smiles = set()
    inactive_smiles = set()
    r2_smiles_map = {}  # mol_id → canonical SMILES

    # ── 1. Patent 403 ──
    patent_df = pd.read_csv(PATENT_CSV)
    for _, row in patent_df.iterrows():
        canon = norm(row["canonical_smiles"])
        if not canon: continue
        if int(row["label_active"]) == 1:
            active_smiles.add(canon)
        else:
            inactive_smiles.add(canon)
    # 去重：同一 SMILES 不能同时在 active 和 inactive 中
    overlap = active_smiles & inactive_smiles
    inactive_smiles -= overlap
    print(f"Patent: {len(active_smiles)} actives, {len(inactive_smiles)} inactives (removed {len(overlap)} overlap)")

    # ── 2. Wet-lab 13 (Round 1) ──
    wetlab_df = pd.read_csv(WETLAB_CSV)
    wl_active, wl_inactive = 0, 0
    for _, row in wetlab_df.iterrows():
        sid = str(row["SDF_ID"])
        smi_csv = str(row["SMILES"])
        canon = norm(smi_csv)
        if not canon: continue
        is_pos = sid in POSITIVE_IDS
        if is_pos:
            active_smiles.add(canon)
            wl_active += 1
        else:
            inactive_smiles.add(canon)
            wl_inactive += 1
    overlap = active_smiles & inactive_smiles
    inactive_smiles -= overlap
    print(f"Wet-lab R1: {wl_active} actives, {wl_inactive} inactives (overlap removed: {len(overlap)})")

    # ── 3. Round-2 19 (全部放 actives，作"hidden gems") ──
    for fname in sorted(os.listdir(R2_SDF_DIR)):
        if not fname.endswith(".sdf"): continue
        sid = fname.replace(".sdf", "")
        canon = extract_smiles_from_sdf(os.path.join(R2_SDF_DIR, fname))
        if canon:
            r2_smiles_map[sid] = canon
            # 检查是否与已存在的 inactive 冲突
            if canon in inactive_smiles:
                inactive_smiles.discard(canon)
            active_smiles.add(canon)
    print(f"Round-2: {len(r2_smiles_map)} molecules (added to actives as hidden gems)")

    # ── 4. swxds 250k ──
    swxds_df = pd.read_csv(SWXDS_CSV)
    swxds_count = 0
    for smi in swxds_df["smiles"]:
        canon = norm(str(smi))
        if not canon: continue
        if canon in active_smiles:
            continue  # 已经在 active 中，跳过
        inactive_smiles.add(canon)
        swxds_count += 1
    print(f"swxds: {swxds_count} added to inactives")

    # ── 5. 写入 GLARE 格式 ──
    with open(GLARE_DATA_DIR / "actives.smi", "w") as f:
        for smi in sorted(active_smiles):
            f.write(f"{smi}\n")

    with open(GLARE_DATA_DIR / "inactives.smi", "w") as f:
        for smi in sorted(inactive_smiles):
            f.write(f"{smi}\n")

    print(f"\n✅ Written to {GLARE_DATA_DIR}:")
    print(f"   actives.smi:   {len(active_smiles)} SMILES")
    print(f"   inactives.smi: {len(inactive_smiles)} SMILES")
    print(f"   Total pool:    {len(active_smiles) + len(inactive_smiles):,}")

    # ── 6. R2 追踪文件 ──
    tracking = {
        "description": "Round-2 19 molecules tracking for E41 active learning",
        "n_molecules": len(r2_smiles_map),
        "molecules": r2_smiles_map,
        "total_actives_in_pool": len(active_smiles),
        "r2_in_actives_count": sum(1 for s in r2_smiles_map.values() if s in active_smiles),
    }
    with open(OUTPUT_DIR / "r2_smiles_tracking.json", "w") as f:
        json.dump(tracking, f, indent=2, ensure_ascii=False)
    print(f"\n✅ R2 tracking: {OUTPUT_DIR / 'r2_smiles_tracking.json'}")

if __name__ == "__main__":
    main()
