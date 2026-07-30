#!/usr/bin/env python3
"""round_200 生成分子 vs glaretrain 已知分子胶 相似性比对 + 模型打分关系分析。

数据：
- 生成分子：round_200/merged/round_200_merged_eval.xlsx (922 个, 带 Vina_Dock/QED/SA)
- 已知分子胶：glaretrain/DataSet-GNN-SMILES-pDC50.xlsx (439 个, 带实测 pDC50)
- 已知分子胶 SDF：glaretrain/01-MGDs-Patent-DataBase/*.sdf, 00-MGDs-Synthesis-DataBase/*.sdf

方法：Morgan(ECFP4, r=2, 2048bit) Tanimoto。
每个生成分子的"相似度" = 与 439 个分子胶的最大 Tanimoto (最近邻)。
该最近邻的 pDC50 作为该生成分子的"湿实验活性代理"(nearest-neighbor proxy)。

输出：
- round_200/similarity/gen_vs_mgd_similarity.csv  (每生成分子: max_tani, nn_cpd, nn_pDC50, 模型分)
- round_200/similarity/high_similarity_mols.csv   (相似度>=0.5 的分子明细)
- round_200/similarity/similarity_stats.json
"""
import json
from pathlib import Path
import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit.rdBase import DisableLog

DisableLog("rdApp.*")

ROUND = Path("/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200")
GLARE = Path("/data/ye/e-drug-lab/glaretrain")
OUT = ROUND / "similarity"
OUT.mkdir(exist_ok=True)

# ---------- 1. 读已知分子胶 (带 pDC50) ----------
mgd = pd.read_excel(GLARE / "DataSet-GNN-SMILES-pDC50.xlsx")
print(f"[mgd] {len(mgd)} 个已知分子胶, 列={list(mgd.columns)}")
mgd = mgd.dropna(subset=["SMILES"]).reset_index(drop=True)

# 用 SDF 补充/校验（Synthesis 库的 Cpd. 是 7 位数字如 0228264，无 SMILES 在 pDC50 表里则从 SDF 取）
# pDC50 表已含 SMILES，直接用即可
mgd_mols = []
mgd_fps = []
mgd_meta = []  # (cpd, smiles, pDC50)
for _, r in mgd.iterrows():
    m = Chem.MolFromSmiles(str(r["SMILES"]))
    if m is None:
        continue
    fp = AllChem.GetMorganFingerprintAsBitVect(m, radius=2, nBits=2048)
    mgd_mols.append(m)
    mgd_fps.append(fp)
    mgd_meta.append((str(r["Cpd."]), str(r["SMILES"]), float(r["pDC50"])))
print(f"[mgd] 有效指纹: {len(mgd_fps)}")
print(f"[mgd] pDC50 范围: {min(x[2] for x in mgd_meta):.2f} ~ {max(x[2] for x in mgd_meta):.2f}")

# ---------- 2. 读生成分子 ----------
gen = pd.read_excel(ROUND / "merged" / "round_200_merged_eval.xlsx")
print(f"[gen] {len(gen)} 个生成分子")
gen = gen.dropna(subset=["SMILES"]).reset_index(drop=True)

# ---------- 3. 相似性比对：每个生成分子 vs 全部 MGD，取 max Tanimoto ----------
rows = []
for i, r in gen.iterrows():
    m = Chem.MolFromSmiles(str(r["SMILES"]))
    if m is None:
        continue
    fp = AllChem.GetMorganFingerprintAsBitVect(m, radius=2, nBits=2048)
    sims = DataStructs.BulkTanimotoSimilarity(fp, mgd_fps)
    best_idx = max(range(len(sims)), key=lambda j: sims[j])
    nn_cpd, nn_smi, nn_pdc50 = mgd_meta[best_idx]
    rows.append({
        "gen_idx": i,
        "gen_SMILES": str(r["SMILES"]),
        "source_gpu": r.get("source_gpu", ""),
        "Vina_Dock": float(r["Vina_Dock_亲和力"]),
        "QED": float(r["QED评分"]),
        "SA": float(r["SA评分"]),
        "logP": float(r["logP"]),
        "Lipinski": float(r["Lipinski规则得分"]),
        "max_tani": float(sims[best_idx]),
        "nn_cpd": nn_cpd,
        "nn_SMILES": nn_smi,
        "nn_pDC50": float(nn_pdc50),
    })

res = pd.DataFrame(rows)
res.to_csv(OUT / "gen_vs_mgd_similarity.csv", index=False)
print(f"\n[done] 相似性计算完成: {len(res)} 个生成分子")
print(f"  max_tani 分布: mean={res['max_tani'].mean():.3f} median={res['max_tani'].median():.3f} "
      f"min={res['max_tani'].min():.3f} max={res['max_tani'].max():.3f}")
print(f"  相似度>=0.5: {(res['max_tani']>=0.5).sum()} 个")
print(f"  相似度>=0.4: {(res['max_tani']>=0.4).sum()} 个")
print(f"  相似度>=0.3: {(res['max_tani']>=0.3).sum()} 个")

# 高相似分子明细
hi = res[res["max_tani"] >= 0.5].sort_values("max_tani", ascending=False)
hi.to_csv(OUT / "high_similarity_mols.csv", index=False)
print(f"\n[high] 相似度>=0.5 明细 {len(hi)} 个, 已存 high_similarity_mols.csv")
if len(hi):
    print(hi[["gen_SMILES", "max_tani", "nn_cpd", "nn_pDC50", "Vina_Dock", "QED"]].head(15).to_string(index=False))

# 统计
stats = {
    "n_gen": int(len(res)),
    "n_mgd": int(len(mgd_fps)),
    "tani_mean": float(res["max_tani"].mean()),
    "tani_median": float(res["max_tani"].median()),
    "tani_max": float(res["max_tani"].max()),
    "n_ge_0.5": int((res["max_tani"] >= 0.5).sum()),
    "n_ge_0.4": int((res["max_tani"] >= 0.4).sum()),
    "n_ge_0.3": int((res["max_tani"] >= 0.3).sum()),
    "corr_tani_vina": float(res["max_tani"].corr(res["Vina_Dock"])),
    "corr_tani_qed": float(res["max_tani"].corr(res["QED"])),
    "corr_tani_sa": float(res["max_tani"].corr(res["SA"])),
    "corr_vina_pdc50_hi": float(res[res["max_tani"] >= 0.5]["Vina_Dock"].corr(
        res[res["max_tani"] >= 0.5]["nn_pDC50"])) if (res["max_tani"] >= 0.5).sum() > 2 else None,
}
with open(OUT / "similarity_stats.json", "w") as f:
    json.dump(stats, f, indent=2, ensure_ascii=False)
print(f"\n[stats] {json.dumps(stats, indent=2)}")
