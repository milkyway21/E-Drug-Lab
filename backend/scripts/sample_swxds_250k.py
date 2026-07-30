#!/usr/bin/env python3
"""从 swxds 500万分子库随机采样 250k，RDKit 清洗去重。

输入: /home/user/Desktop/Ye/DiffDynamic/data/swxds/swxds_smiles.tsv (5,357,738 SMILES)
输出: backend/outputs/vav1_rl_project/validation/glare_e41_al/swxds_250k_smiles.csv

策略: 多采 10% (275k) → RDKit 过滤 → 保留前 250k
"""
import sys, os, random
import pandas as pd
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import Descriptors

SEED = 42
TARGET = 250_000
OVERSAMPLE = 275_000
TSV_PATH = "/home/user/Desktop/Ye/DiffDynamic/data/swxds/swxds_smiles.tsv"
OUTPUT_DIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e41_al")
OUTPUT_FILE = OUTPUT_DIR / "swxds_250k_smiles.csv"

random.seed(SEED)

def norm(smi: str) -> str:
    """RDKit 标准化: 去盐、去同位素、canonical SMILES"""
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return ""
    # 去除同位素信息
    for atom in mol.GetAtoms():
        atom.SetIsotope(0)
    # 去盐 (取最大碎片)
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
    if not frags:
        return ""
    mol = max(frags, key=lambda m: m.GetNumHeavyAtoms())
    try:
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return ""


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 确定总行数，随机选行号 ──
    print(f"Counting lines in {TSV_PATH}...")
    with open(TSV_PATH) as f:
        total = sum(1 for _ in f)
    print(f"  Total: {total:,} lines")

    selected = set(random.sample(range(total), min(OVERSAMPLE, total)))
    print(f"  Selected {len(selected):,} random indices")

    # ── 2. 流式读取，只保留选中行 ──
    print("Reading and filtering...")
    seen = set()
    kept = []
    rejected = 0
    with open(TSV_PATH) as f:
        for i, line in enumerate(f):
            if i not in selected:
                continue
            parts = line.strip().split("\t")
            # TSV 格式: line_number \t SMILES \t compound_name
            if len(parts) < 2:
                rejected += 1
                continue
            smi_raw = parts[1].strip()  # SMILES 在第二列
            title = parts[2].strip() if len(parts) > 2 else ""
            canon = norm(smi_raw)
            if not canon or canon in seen:
                rejected += 1
                continue
            # 基本过滤：分子量 150-800，重原子 >= 8
            mol = Chem.MolFromSmiles(canon)
            if mol is None:
                rejected += 1
                continue
            mw = Descriptors.MolWt(mol)
            ha = mol.GetNumHeavyAtoms()
            if mw < 150 or mw > 800 or ha < 8:
                rejected += 1
                continue
            seen.add(canon)
            kept.append({"smiles": canon, "original_title": title, "original_smiles": smi_raw})
            if len(kept) >= TARGET:
                break
            if len(kept) % 50000 == 0:
                print(f"  Kept {len(kept):,} / rejected {rejected:,}...")

    print(f"Final: {len(kept):,} molecules (rejected {rejected:,})")

    # ── 3. 保存 ──
    df = pd.DataFrame(kept)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved: {OUTPUT_FILE}")
    print(f"  {len(df)} rows, {df['smiles'].nunique()} unique SMILES")

    # 采样统计
    mols = [Chem.MolFromSmiles(s) for s in df["smiles"]]
    mws = [Descriptors.MolWt(m) for m in mols]
    print(f"  MW range: {min(mws):.0f} - {max(mws):.0f}, mean: {sum(mws)/len(mws):.1f}")
    print("✅ Done.")

if __name__ == "__main__":
    main()
