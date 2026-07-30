#!/usr/bin/env python3
"""round_200 生成分子 vs (已知分子胶 + 靶标原配体 9nfrligand) 相似性比对 v2。

参考库 = 439 个带 pDC50 的分子胶 + 9nfrligand(靶标原配体, pDC50=N/A)。
高相似组 = max_tani 的 Top 10% 分位数。
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit.rdBase import DisableLog

DisableLog("rdApp.*")
ROUND = Path("/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200")
GLARE = Path("/data/ye/e-drug-lab/glaretrain")
OUT = ROUND / "similarity"
OUT.mkdir(exist_ok=True)

# ---------- 参考库 ----------
mgd = pd.read_excel(GLARE / "DataSet-GNN-SMILES-pDC50.xlsx").dropna(subset=["SMILES"]).reset_index(drop=True)
ref_fps, ref_meta = [], []  # (cpd, smiles, pDC50 or nan, source)
for _, r in mgd.iterrows():
    m = Chem.MolFromSmiles(str(r["SMILES"]))
    if m is None:
        continue
    ref_fps.append(AllChem.GetMorganFingerprintAsBitVect(m, 2, 2048))
    ref_meta.append((str(r["Cpd."]), str(r["SMILES"]), float(r["pDC50"]), "MGD"))
# 加 9nfrligand
m9 = Chem.MolFromMolFile("/data/ye/e-drug-lab/data/VAV1_degron/9nfrligand.sdf")
ref_fps.append(AllChem.GetMorganFingerprintAsBitVect(m9, 2, 2048))
ref_meta.append(("9nfrligand", Chem.MolToSmiles(m9), float("nan"), "target_ligand"))
print(f"[ref] 参考库 {len(ref_fps)} 个 (MGD {len(mgd)} + 9nfrligand 1)")

# ---------- 生成分子 ----------
gen = pd.read_excel(ROUND / "merged" / "round_200_merged_eval.xlsx").dropna(subset=["SMILES"]).reset_index(drop=True)
print(f"[gen] {len(gen)} 生成分子")

# ---------- 比对 ----------
rows = []
for i, r in gen.iterrows():
    m = Chem.MolFromSmiles(str(r["SMILES"]))
    if m is None:
        continue
    fp = AllChem.GetMorganFingerprintAsBitVect(m, 2, 2048)
    sims = DataStructs.BulkTanimotoSimilarity(fp, ref_fps)
    best = int(np.argmax(sims))
    nn_cpd, nn_smi, nn_pdc50, nn_src = ref_meta[best]
    # 单独记与 9nfrligand 的相似度
    tani_9nfr = sims[-1]
    rows.append({
        "gen_idx": i, "gen_SMILES": str(r["SMILES"]),
        "source_gpu": r.get("source_gpu", ""),
        "Vina_Dock": float(r["Vina_Dock_亲和力"]), "QED": float(r["QED评分"]),
        "SA": float(r["SA评分"]), "logP": float(r["logP"]),
        "Lipinski": float(r["Lipinski规则得分"]),
        "max_tani": float(sims[best]), "nn_cpd": nn_cpd, "nn_SMILES": nn_smi,
        "nn_pDC50": float(nn_pdc50) if nn_src == "MGD" else float("nan"),
        "nn_source": nn_src, "tani_9nfr": float(tani_9nfr),
    })
res = pd.DataFrame(rows)

# Top 10% 分位数定义高相似组
q90 = float(res["max_tani"].quantile(0.90))
res["high_sim_group"] = (res["max_tani"] >= q90).map({True: "Top10%", False: "Other"})
res.to_csv(OUT / "gen_vs_ref_similarity.csv", index=False)

hi = res[res["max_tani"] >= q90].sort_values("max_tani", ascending=False)
hi.to_csv(OUT / "high_similarity_top10pct.csv", index=False)

stats = {
    "n_gen": int(len(res)), "n_ref": int(len(ref_fps)),
    "tani_mean": float(res["max_tani"].mean()), "tani_median": float(res["max_tani"].median()),
    "tani_max": float(res["max_tani"].max()), "q90_threshold": q90,
    "n_top10": int(len(hi)),
    "n_ge_0.5": int((res["max_tani"] >= 0.5).sum()),
    "n_ge_0.4": int((res["max_tani"] >= 0.4).sum()),
    "n_ge_0.3": int((res["max_tani"] >= 0.3).sum()),
    "tani_9nfr_max": float(res["tani_9nfr"].max()),
    "tani_9nfr_mean": float(res["tani_9nfr"].mean()),
    "n_nn_is_9nfr": int((res["nn_source"] == "target_ligand").sum()),
    "corr_tani_vina": float(res["max_tani"].corr(res["Vina_Dock"])),
    "corr_tani_qed": float(res["max_tani"].corr(res["QED"])),
    "corr_tani_sa": float(res["max_tani"].corr(res["SA"])),
    "corr_vina_pdc50_top10": float(hi["Vina_Dock"].corr(hi["nn_pDC50"])) if hi["nn_pDC50"].notna().sum() > 2 else None,
    "corr_tani_pdc50_top10": float(hi["max_tani"].corr(hi["nn_pDC50"])) if hi["nn_pDC50"].notna().sum() > 2 else None,
}
with open(OUT / "similarity_stats.json", "w") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)

print(f"\n=== 结果 ===")
print(f"max_tani: mean={stats['tani_mean']:.3f} median={stats['tani_median']:.3f} max={stats['tani_max']:.3f}")
print(f"Top10% 阈值(q90)={q90:.3f}, 高相似组 {len(hi)} 个")
print(f"≥0.5: {stats['n_ge_0.5']} | ≥0.4: {stats['n_ge_0.4']} | ≥0.3: {stats['n_ge_0.3']}")
print(f"与9nfrligand: max={stats['tani_9nfr_max']:.3f} mean={stats['tani_9nfr_mean']:.3f}, 最近邻是9nfrligand的: {stats['n_nn_is_9nfr']}个")
print(f"corr: tani-Vina={stats['corr_tani_vina']:.3f} tani-QED={stats['corr_tani_qed']:.3f} tani-SA={stats['corr_tani_sa']:.3f}")
print(f"Top10%内 corr: Vina-pDC50={stats['corr_vina_pdc50_top10']} tani-pDC50={stats['corr_tani_pdc50_top10']}")
print(f"\nTop 15 高相似分子:")
print(hi[["gen_SMILES", "max_tani", "nn_cpd", "nn_source", "nn_pDC50", "Vina_Dock", "QED"]].head(15).to_string(index=False))
