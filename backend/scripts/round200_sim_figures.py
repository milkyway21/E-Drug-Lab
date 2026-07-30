#!/usr/bin/env python3
"""round_200 相似性分析 Nature 风格图（Python/matplotlib）。

5 面板：
a. max_tani 分布直方图 + q90 阈值 + 0.5 参考线
b. max_tani vs Vina_Dock 散点（Top10% 高亮，Pearson r）
c. max_tani vs SA / vs QED 双子图
d. Top10% 高相似组：最近邻 pDC50 分布 + Vina vs pDC50
e. 与 9nfrligand 相似度 vs 与 MGD max_tani 对比
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from scipy.stats import pearsonr

# ---- mandatory font/SVG rules ----
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["font.size"] = 7
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["axes.spines.right"] = False
plt.rcParams["axes.spines.top"] = False
plt.rcParams["legend.frameon"] = False

PALETTE = {
    "blue_main": "#0F4D92", "blue_secondary": "#3775BA",
    "green_3": "#8BCF8B", "red_strong": "#B64342",
    "teal": "#42949E", "violet": "#9A4D8E",
    "neutral_light": "#CFCECE", "neutral_mid": "#767676",
    "neutral_dark": "#4D4D4D", "gold": "#FFD700",
}
C_OTHER = PALETTE["neutral_light"]
C_TOP = PALETTE["red_strong"]
C_BLUE = PALETTE["blue_main"]
C_TEAL = PALETTE["teal"]

ROUND = Path("/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200")
OUT = ROUND / "similarity" / "figures"
OUT.mkdir(exist_ok=True)
res = pd.read_csv(ROUND / "similarity" / "gen_vs_ref_similarity.csv")
q90 = float(res["max_tani"].quantile(0.90))
res["is_top"] = res["max_tani"] >= q90
print(f"n={len(res)} q90={q90:.3f} top={res['is_top'].sum()}")

fig = plt.figure(figsize=(7.2, 6.4))
# 布局：a 左上, b 右上, c 中行, d 左下, e 右下
ax_a = fig.add_axes([0.07, 0.66, 0.27, 0.30])
ax_b = fig.add_axes([0.40, 0.66, 0.27, 0.30])
ax_c1 = fig.add_axes([0.75, 0.66, 0.22, 0.30])
ax_d = fig.add_axes([0.07, 0.34, 0.40, 0.27])
ax_e = fig.add_axes([0.55, 0.34, 0.40, 0.27])
ax_c2 = fig.add_axes([0.75, 0.34, 0.22, 0.27])

def panel_label(ax, lab, x=-0.18, y=1.08):
    ax.text(x, y, lab, transform=ax.transAxes, fontsize=9, fontweight="bold", va="top", ha="left")

# ---- a: 相似度分布 ----
panel_label(ax_a, "a")
ax_a.hist(res["max_tani"], bins=30, color=C_BLUE, alpha=0.75, edgecolor="white", linewidth=0.4)
ax_a.axvline(q90, color=C_TOP, lw=1.2, ls="--", label=f"Top10% = {q90:.2f}")
ax_a.axvline(0.5, color=PALETTE["neutral_mid"], lw=1.0, ls=":", label="0.50 (none reached)")
ax_a.set_xlabel("Max Tanimoto to known MGDs")
ax_a.set_ylabel("Generated molecules (n=922)")
ax_a.legend(loc="upper right", fontsize=5.5, handlelength=1.2)
ax_a.set_title("Structural similarity is overall low", fontsize=6.5, fontweight="bold", loc="left")

# ---- b: tani vs Vina ----
panel_label(ax_b, "b")
oth = res[~res["is_top"]]
top = res[res["is_top"]]
ax_b.scatter(oth["max_tani"], oth["Vina_Dock"], s=6, c=C_OTHER, alpha=0.5, linewidths=0, label="Other")
ax_b.scatter(top["max_tani"], top["Vina_Dock"], s=10, c=C_TOP, alpha=0.8, linewidths=0.2, edgecolors="white", label="Top10%")
# 拟合线
z = np.polyfit(res["max_tani"], res["Vina_Dock"], 1)
xs = np.linspace(res["max_tani"].min(), res["max_tani"].max(), 50)
ax_b.plot(xs, np.polyval(z, xs), color=C_BLUE, lw=1.0)
r, p = pearsonr(res["max_tani"], res["Vina_Dock"])
ax_b.text(0.05, 0.05, f"r={r:.2f}\np={p:.1e}", transform=ax_b.transAxes, fontsize=5.8, va="bottom")
ax_b.set_xlabel("Max Tanimoto")
ax_b.set_ylabel("Vina dock (kcal/mol)")
ax_b.legend(loc="upper right", fontsize=5.5, markerscale=0.8)
ax_b.set_title("Affinity vs similarity: weak", fontsize=6.5, fontweight="bold", loc="left")

# ---- c1: tani vs SA ----
panel_label(ax_c1, "c")
ax_c1.scatter(res["max_tani"], res["SA"], s=5, c=C_TEAL, alpha=0.5, linewidths=0)
z2 = np.polyfit(res["max_tani"], res["SA"], 1)
ax_c1.plot(xs, np.polyval(z2, xs), color=PALETTE["neutral_dark"], lw=0.9)
r2, _ = pearsonr(res["max_tani"], res["SA"])
ax_c1.text(0.05, 0.05, f"SA\nr={r2:.2f}", transform=ax_c1.transAxes, fontsize=5.8, va="bottom")
ax_c1.set_xlabel("Max Tanimoto")
ax_c1.set_ylabel("SA score")
ax_c1.set_title("Synthesizability rises with similarity", fontsize=6.5, fontweight="bold", loc="left")

# ---- d: Top10% pDC50 分布 + Vina vs pDC50 ----
panel_label(ax_d, "d")
top_nn = top.dropna(subset=["nn_pDC50"])
ax_d.hist(top_nn["nn_pDC50"], bins=15, color=C_TOP, alpha=0.7, edgecolor="white", linewidth=0.4)
ax_d.set_xlabel("Nearest-neighbor pDC50 (wet-lab, Top10%)")
ax_d.set_ylabel("Count")
ax_d.set_title(f"High-similarity mols map to active MGDs (pDC50≥5)", fontsize=6.5, fontweight="bold", loc="left")
# 内嵌 Vina vs pDC50
inset = fig.add_axes([0.30, 0.55, 0.15, 0.10])
inset.scatter(top_nn["nn_pDC50"], top_nn["Vina_Dock"], s=6, c=C_TOP, alpha=0.7, linewidths=0)
rv, _ = pearsonr(top_nn["nn_pDC50"], top_nn["Vina_Dock"])
inset.text(0.05, 0.05, f"r={rv:.2f}", transform=inset.transAxes, fontsize=5)
inset.set_xlabel("nn pDC50", fontsize=5)
inset.set_ylabel("Vina", fontsize=5)
inset.tick_params(labelsize=4.5)
for s in ["top", "right"]:
    inset.spines[s].set_visible(False)

# ---- e: 9nfrligand 相似度 vs MGD max_tani ----
panel_label(ax_e, "e")
ax_e.scatter(res["max_tani"], res["tani_9nfr"], s=6, c=C_BLUE, alpha=0.5, linewidths=0)
ax_e.axhline(0.5, color=PALETTE["neutral_mid"], lw=0.8, ls=":")
ax_e.set_xlabel("Max Tanimoto to MGDs")
ax_e.set_ylabel("Tanimoto to 9nfr ligand (target)")
r9_max = res["tani_9nfr"].max()
ax_e.text(0.05, 0.92, f"max to 9nfr ligand = {r9_max:.2f}\n(6 mols have 9nfr as NN)",
          transform=ax_e.transAxes, fontsize=5.8, va="top")
ax_e.set_title("Gen mols diverge from the co-crystal ligand", fontsize=6.5, fontweight="bold", loc="left")

# ---- c2: tani vs QED ----
panel_label(ax_c2, "")
ax_c2.scatter(res["max_tani"], res["QED"], s=5, c=PALETTE["green_3"], alpha=0.5, linewidths=0)
z3 = np.polyfit(res["max_tani"], res["QED"], 1)
ax_c2.plot(xs, np.polyval(z3, xs), color=PALETTE["neutral_dark"], lw=0.9)
r3, _ = pearsonr(res["max_tani"], res["QED"])
ax_c2.text(0.05, 0.05, f"QED\nr={r3:.2f}", transform=ax_c2.transAxes, fontsize=5.8, va="bottom")
ax_c2.set_xlabel("Max Tanimoto")
ax_c2.set_ylabel("QED")
ax_c2.set_title("Drug-likeness vs similarity", fontsize=6.5, fontweight="bold", loc="left")

fig.suptitle("DiffGUI-generated VAV1 glue candidates vs known molecular glue degraders (MGDs)",
             fontsize=8.5, fontweight="bold", y=0.98)

for ext in ("svg", "pdf", "png"):
    fig.savefig(OUT / f"similarity_analysis.{ext}", dpi=600, bbox_inches="tight")
print(f"[saved] {OUT}/similarity_analysis.{{svg,pdf,png}}")
