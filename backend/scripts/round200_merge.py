#!/usr/bin/env python3
"""合并 round_200 两卡 correct-reconstruct 评估结果，输出 Top 分子 + 分布统计。"""
import sys
from pathlib import Path
import pandas as pd

ROUND = Path("/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200")
MERGED = ROUND / "merged"
MERGED.mkdir(exist_ok=True)

# 找两卡 evaluation_results xlsx
def find_xlsx(gpu):
    hits = list((ROUND / "eval" / gpu).rglob("evaluation_results_*.xlsx"))
    return hits[0] if hits else None

frames = []
for gpu in ("gpu1", "gpu2"):
    x = find_xlsx(gpu)
    if x is None:
        print(f"[warn] {gpu} 无 evaluation_results xlsx")
        continue
    df = pd.read_excel(x)
    df["source_gpu"] = gpu
    frames.append(df)
    print(f"[{gpu}] {len(df)} 行  ← {x.name}")

if not frames:
    sys.exit("无可合并结果")

all_df = pd.concat(frames, ignore_index=True)
print(f"\n合并总数: {len(all_df)} 分子")

# 列名探测
cols = list(all_df.columns)
print(f"\n列: {cols}")

# 综合分列名候选
score_col = None
for c in cols:
    cl = c.lower()
    if "综合" in c or "composite" in cl or "score" in cl and "vina" not in cl:
        score_col = c; break
vina_col = next((c for c in cols if "vina" in c.lower() and "dock" in c.lower()), None) or \
           next((c for c in cols if "vina" in c.lower()), None)
qed_col = next((c for c in cols if c.lower() == "qed"), None)
sa_col = next((c for c in cols if c.lower() in ("sa", "sa_score")), None)

print(f"\n关键列: 综合={score_col}, vina={vina_col}, qed={qed_col}, sa={sa_col}")

# 分布统计
print("\n===== 分布统计 =====")
if vina_col:
    print(f"Vina dock: mean={all_df[vina_col].mean():.2f} median={all_df[vina_col].median():.2f} "
          f"min={all_df[vina_col].min():.2f} max={all_df[vina_col].max():.2f}")
if qed_col:
    print(f"QED: mean={all_df[qed_col].mean():.3f}")
if sa_col:
    print(f"SA: mean={all_df[sa_col].mean():.3f}")

# Top 20
sort_col = score_col if score_col else vina_col
if sort_col:
    asc = True if (vina_col and sort_col == vina_col) else False  # vina 越负越好；综合分越大越好
    top = all_df.sort_values(sort_col, ascending=asc).head(20)
    print(f"\n===== Top 20 (按 {sort_col}, {'升序' if asc else '降序'}) =====")
    show_cols = [c for c in [sort_col, vina_col, qed_col, sa_col, "source_gpu"] if c]
    # 加 smiles
    smi_col = next((c for c in cols if "smiles" in c.lower()), None)
    if smi_col: show_cols = [smi_col] + show_cols
    print(top[show_cols].to_string(index=False))

# 保存
out = MERGED / "round_200_merged_eval.xlsx"
all_df.to_excel(out, index=False)
print(f"\n已保存合并结果: {out}")
if sort_col:
    top.to_excel(MERGED / "round_200_top20.xlsx", index=False)
    print(f"已保存 Top20: {MERGED / 'round_200_top20.xlsx'}")
