#!/usr/bin/env python3
"""E46 可视化: Patent active retrieval with negatives — R0→R1→R2 渐进改善.

Figures:
  1. Score Separation — 正负评分分离度逐轮提升
  2. Strong Active Mean Rank — 强活性分子排名改善
  3. Patent Pos/Neg Score 对比 — 三轮模型评分分布
  4. Recall @Top-K — 已知活性分子召回率
  5. 四合一 Dashboard
"""
import json
import numpy as np
from pathlib import Path

E46_JSON = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e46_planb/E46_planb_results.json"
)
OUT_DIR = E46_JSON.parent / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 配色 (soft green/red semantic) ──
C_R0 = "#B8C5D4"       # 灰蓝 — 基线
C_R1 = "#A8D5A2"       # soft green — 改善
C_R2 = "#72C073"       # 更深绿 — 进一步改善
C_IMPROVED = "#A8D5A2"
C_IMPROVED_DK = "#5FAF6B"
C_WORSE = "#E8A6A1"
C_WORSE_DK = "#D4736B"
C_NEUTRAL = "#B0B8C0"
C_EDGE = "#5A6570"
C_SCORE_BG = "#F5F9F3"
C_GREEN_BG = "#F0F7EF"
C_RED_BG = "#FBF0EF"

ROUNDS = ["R0", "R1", "R2"]
ROUND_LABELS = ["R0\n(Patent 403)", "R1\n(+13 R1 wet-lab)", "R2\n(+19 R2 wet-lab)"]
C_ROUNDS = [C_R0, C_R1, C_R2]


def load():
    with open(E46_JSON) as f:
        return json.load(f)


def setup_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans", "sans-serif"],
        "svg.fonttype": "none", "pdf.fonttype": 42,
        "font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
        "xtick.labelsize": 10, "ytick.labelsize": 9, "legend.fontsize": 9,
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.8, "legend.frameon": False,
    })
    return plt


def save(fig, plt, stem):
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=300)
    fig.savefig(OUT_DIR / f"{stem}.svg")
    plt.close(fig)
    print(f"  ✅ {stem}")


# ──────────────────────────────────────────────────────────────────
# Fig 1: Score Separation 逐轮提升（核心指标）
# ──────────────────────────────────────────────────────────────────
def fig1_score_separation(doc, plt):
    data = doc["results"]
    scores = [data[r]["score_separation"] for r in ROUNDS]
    pct = [(s - scores[0]) / scores[0] * 100 for s in scores]

    fig, ax = plt.subplots(figsize=(8, 5.5))
    x = np.arange(3)
    bars = ax.bar(x, scores, color=C_ROUNDS, width=0.55, alpha=0.92,
                  edgecolor=C_EDGE, lw=0.6, zorder=3)

    # 标注值 + 提升百分比
    for i, (v, p) in enumerate(zip(scores, pct)):
        ax.text(i, v + 0.008, f"{v:.4f}", ha="center", fontsize=13, fontweight="bold",
                color=C_EDGE)
        if i > 0 and p > 0:
            ax.text(i, v - 0.025, f"+{p:.1f}%", ha="center", fontsize=10,
                    color=C_IMPROVED_DK, fontweight="bold")

    # Δ 箭头
    for i in range(1, 3):
        delta = scores[i] - scores[i - 1]
        mid = (scores[i] + scores[i - 1]) / 2
        ax.annotate(f"Δ +{delta:.4f}", xy=(i - 0.5 + 0.15, mid + 0.015),
                    fontsize=9, color=C_IMPROVED_DK, ha="center", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS, fontsize=11)
    ax.set_ylabel("Score Separation\n(pos score − neg score, higher = better)", fontsize=11)
    ax.set_title("Figure 1: Score Separation — Progressive Improvement Across Rounds\n"
                 f"R0: {scores[0]:.4f} → R1: {scores[1]:.4f} → R2: {scores[2]:.4f}  "
                 f"(+{pct[2]:.1f}% total)",
                 fontsize=12)
    ax.set_ylim(0.38, max(scores) * 1.15)
    ax.set_facecolor(C_SCORE_BG)

    # 摘要 box
    summary = (
        f"Score Separation = pos mean score − neg mean score\n"
        f"Pos scores: R0={data['R0']['patent_pos']['mean_score']:.4f}  "
        f"R1={data['R1']['patent_pos']['mean_score']:.4f}  "
        f"R2={data['R2']['patent_pos']['mean_score']:.4f}\n"
        f"Neg scores: R0={data['R0']['patent_neg']['mean_score']:.4f}  "
        f"R1={data['R1']['patent_neg']['mean_score']:.4f}  "
        f"R2={data['R2']['patent_neg']['mean_score']:.4f}\n"
        f"R2 将 neg score 从 {data['R0']['patent_neg']['mean_score']:.4f} "
        f"降至 {data['R2']['patent_neg']['mean_score']:.4f} (−{100*(1-data['R2']['patent_neg']['mean_score']/data['R0']['patent_neg']['mean_score']):.1f}%)"
    )
    ax.text(0.02, 0.97, summary, transform=ax.transAxes, fontsize=7.5, va="top",
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor=C_IMPROVED_DK, alpha=0.92))

    fig.tight_layout()
    save(fig, plt, "fig1_score_separation")


# ──────────────────────────────────────────────────────────────────
# Fig 2: Strong Active Mean Rank + Patent Pos Mean Rank
# ──────────────────────────────────────────────────────────────────
def fig2_strong_active_rank(doc, plt):
    data = doc["results"]
    strong_ranks = [data[r]["strong_active"]["mean_rank"] for r in ROUNDS]
    pos_ranks = [data[r]["patent_pos"]["mean_rank"] for r in ROUNDS]
    n_pool = doc["config"]["pool_size"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # A: Strong Active mean rank
    ax = ax1
    x = np.arange(3)
    bars = ax.bar(x, strong_ranks, color=C_ROUNDS, width=0.55, alpha=0.92,
                  edgecolor=C_EDGE, lw=0.6, zorder=3)
    for i, v in enumerate(strong_ranks):
        ax.text(i, v + 3, f"#{v:.0f}", ha="center", fontsize=13, fontweight="bold", color=C_EDGE)
        pct = v / n_pool * 100
        ax.text(i, v - 20, f"Top {pct:.2f}%", ha="center", fontsize=9, color=C_IMPROVED_DK,
                fontweight="bold")
    for i in range(1, 3):
        delta = strong_ranks[i] - strong_ranks[i - 1]
        if delta < 0:
            ax.annotate(f"↑{-delta:.0f}", xy=(i, strong_ranks[i] - 35),
                        ha="center", fontsize=10, color=C_IMPROVED_DK, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS, fontsize=10)
    ax.set_ylabel("Mean Rank (lower = better)")
    ax.set_title(f"A. Strong Active (pDC50>8, n={data['R0']['strong_active']['n']})", fontsize=12)
    ax.invert_yaxis()
    ax.set_facecolor(C_SCORE_BG)

    # B: Patent Pos Mean Rank (nearly flat, but context)
    ax = ax2
    ax.bar(x, pos_ranks, color=C_ROUNDS, width=0.55, alpha=0.92, edgecolor=C_EDGE, lw=0.6, zorder=3)
    for i, v in enumerate(pos_ranks):
        ax.text(i, v + 2, f"#{v:.0f}", ha="center", fontsize=12, fontweight="bold", color=C_EDGE)
    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS, fontsize=10)
    ax.set_ylabel("Mean Rank (lower = better)")
    ax.set_title(f"B. All Patent Pos (pDC50>7, n={data['R0']['patent_pos']['n']})", fontsize=12)
    ax.invert_yaxis()
    ax.set_facecolor(C_SCORE_BG)

    fig.suptitle("Figure 2: Active Molecule Mean Rank Across Rounds", fontsize=13,
                 fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, plt, "fig2_strong_active_rank")


# ──────────────────────────────────────────────────────────────────
# Fig 3: Neg Score Distribution (Pos flat, Neg drops — key story)
# ──────────────────────────────────────────────────────────────────
def fig3_pos_neg_scores(doc, plt):
    data = doc["results"]
    pos_scores = [data[r]["patent_pos"]["mean_score"] for r in ROUNDS]
    neg_scores = [data[r]["patent_neg"]["mean_score"] for r in ROUNDS]
    strong_scores = [data[r]["strong_active"]["mean_score"] for r in ROUNDS]

    fig, ax = plt.subplots(figsize=(9, 5.8))
    x = np.arange(3)
    w = 0.25

    # Pos scores
    bars_p = ax.bar(x - w, pos_scores, w, color="#E8D5A3", alpha=0.92,
                    edgecolor=C_EDGE, lw=0.5, zorder=3, label="Patent Pos (pDC50>7)")
    # Strong scores
    bars_s = ax.bar(x, strong_scores, w, color="#D4B872", alpha=0.92,
                    edgecolor=C_EDGE, lw=0.5, zorder=3, label="Strong Active (pDC50>8)")
    # Neg scores (key: drops significantly)
    bars_n = ax.bar(x + w, neg_scores, w, color=[C_WORSE, "#E0908A", "#D4736B"],
                    alpha=0.92, edgecolor=C_EDGE, lw=0.6, zorder=3, label="Patent Neg (label≤0)")

    # Value labels
    for bars in [bars_p, bars_s, bars_n]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.005,
                    f"{h:.4f}", ha="center", fontsize=8, color=C_EDGE, fontweight="bold")

    # Neg score drop annotation
    for i in range(3):
        if i == 0:
            continue
        drop = (neg_scores[0] - neg_scores[i]) / neg_scores[0] * 100
        ax.annotate(f"Neg↓{drop:.1f}%", xy=(i + w, neg_scores[i] - 0.04),
                    ha="center", fontsize=9, color=C_WORSE_DK, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS, fontsize=11)
    ax.set_ylabel("Mean GLARE Score")
    ax.set_title("Figure 3: Model Scores — Pos Stable, Neg Progressively Lowered\n"
                 "Model learns to down-score non-actives while keeping true actives high",
                 fontsize=12)
    ax.legend(fontsize=9, loc="lower left")
    ax.set_ylim(0.40, 1.03)

    # 右侧注释
    ax.text(0.98, 0.97,
            f"Pos scores flat: {pos_scores[0]:.4f}→{pos_scores[2]:.4f}\n"
            f"Neg scores drop: {neg_scores[0]:.4f}→{neg_scores[2]:.4f}\n"
            f"→ Score separation +13.5%",
            transform=ax.transAxes, fontsize=9, va="top", ha="right",
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=C_GREEN_BG, edgecolor=C_IMPROVED_DK, alpha=0.9))

    fig.tight_layout()
    save(fig, plt, "fig3_pos_neg_scores")


# ──────────────────────────────────────────────────────────────────
# Fig 4: Recall @Top-K (已知活性分子召回)
# ──────────────────────────────────────────────────────────────────
def fig4_recall(doc, plt):
    data = doc["results"]
    ks = [10, 50, 100, 200, 500, 1000, 5000]
    n_total = 315  # total known actives

    fig, ax = plt.subplots(figsize=(8, 5.5))
    x = np.arange(len(ks))
    w = 0.22

    for ri, r in enumerate(ROUNDS):
        recalls = [data[r]["recall"][f"recall_top{k}"] for k in ks]
        ax.bar(x + (ri - 1) * w, recalls, w, color=C_ROUNDS[ri], alpha=0.92,
               edgecolor=C_EDGE, lw=0.5, zorder=3, label=f"{r}")

    # Expected random line
    random_expected = [n_total * k / doc["config"]["pool_size"] for k in ks]
    ax.plot(x, random_expected, "k--", alpha=0.3, lw=1, marker="o", markersize=4,
            label="Random", zorder=2)

    ax.set_xticks(x)
    ax.set_xticklabels([f"Top-{k}" for k in ks], fontsize=9)
    ax.set_ylabel("Actives Recalled")
    ax.set_title(f"Figure 4: Recall of Known Actives at Top-K (out of {n_total})\n"
                 f"All models ~perfect recall — actives firmly at top of pool",
                 fontsize=12)
    ax.legend(fontsize=9, loc="lower right")
    ax.set_ylim(0, n_total + 20)

    # 最佳 line
    ax.axhline(n_total, color=C_IMPROVED_DK, ls=":", lw=0.8, alpha=0.6)
    ax.text(len(ks) - 0.3, n_total + 5, f"All {n_total} actives", fontsize=8,
            color=C_IMPROVED_DK, ha="right")

    fig.tight_layout()
    save(fig, plt, "fig4_recall")


# ──────────────────────────────────────────────────────────────────
# Fig 5: Dashboard (4-panel)
# ──────────────────────────────────────────────────────────────────
def fig5_dashboard(doc, plt):
    data = doc["results"]
    n_pool = doc["config"]["pool_size"]
    n_total = 315  # total known active molecules

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # A: Score Separation bars
    ax = axes[0, 0]
    scores = [data[r]["score_separation"] for r in ROUNDS]
    x = np.arange(3)
    pct_improve = [(s - scores[0]) / scores[0] * 100 for s in scores]
    ax.bar(x, scores, color=C_ROUNDS, width=0.55, alpha=0.92, edgecolor=C_EDGE, lw=0.5)
    for i, v in enumerate(scores):
        ax.text(i, v + 0.005, f"{v:.4f}", ha="center", fontsize=11, fontweight="bold")
        if i > 0:
            ax.text(i, v - 0.02, f"+{pct_improve[i]:.1f}%", ha="center", fontsize=8,
                    color=C_IMPROVED_DK, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS)
    ax.set_ylabel("Score Separation")
    ax.set_title("A. Score Separation (pos−neg)", fontweight="bold")
    ax.set_facecolor(C_SCORE_BG)

    # B: Pos/Neg Score trends
    ax = axes[0, 1]
    pos_s = [data[r]["patent_pos"]["mean_score"] for r in ROUNDS]
    neg_s = [data[r]["patent_neg"]["mean_score"] for r in ROUNDS]
    ax.plot(x, pos_s, "o-", color=C_IMPROVED_DK, lw=2.5, markersize=10, label="Pos score",
            zorder=5)
    ax.plot(x, neg_s, "s-", color=C_WORSE_DK, lw=2.5, markersize=10, label="Neg score",
            zorder=5)
    for i in range(3):
        ax.annotate(f"{pos_s[i]:.4f}", (i, pos_s[i]), fontsize=8, color=C_IMPROVED_DK,
                    xytext=(0, 8), textcoords="offset points", ha="center", fontweight="bold")
        ax.annotate(f"{neg_s[i]:.4f}", (i, neg_s[i]), fontsize=8, color=C_WORSE_DK,
                    xytext=(0, -12), textcoords="offset points", ha="center", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS)
    ax.set_ylabel("Mean Score")
    ax.set_title("B. Pos/Neg Score Trends", fontweight="bold")
    ax.legend(fontsize=8)

    # C: Stats table
    ax = axes[1, 0]
    ax.axis("off")
    pos_ranks = [data[r]["patent_pos"]["mean_rank"] for r in ROUNDS]
    neg_ranks = [data[r]["patent_neg"]["mean_rank"] for r in ROUNDS]
    strong_ranks = [data[r]["strong_active"]["mean_rank"] for r in ROUNDS]

    rows = [
        ["Metric", "R0 (Patent)", "R1 (+13R1)", "R2 (+19R2)", "R0→R2 Δ"],
        ["Score Separation", f"{scores[0]:.4f}", f"{scores[1]:.4f}", f"{scores[2]:.4f}",
         f"+{(scores[2]-scores[0]):.4f} ({pct_improve[2]:+.1f}%)"],
        ["Pos Score", f"{pos_s[0]:.4f}", f"{pos_s[1]:.4f}", f"{pos_s[2]:.4f}",
         f"{(pos_s[2]-pos_s[0]):+.4f}"],
        ["Neg Score", f"{neg_s[0]:.4f}", f"{neg_s[1]:.4f}", f"{neg_s[2]:.4f}",
         f"{(neg_s[2]-neg_s[0]):+.4f} (↓{100*(1-neg_s[2]/neg_s[0]):.1f}%)"],
        ["Strong Pos Mean Rank", f"#{strong_ranks[0]:.0f}", f"#{strong_ranks[1]:.0f}",
         f"#{strong_ranks[2]:.0f}", f"{(strong_ranks[2]-strong_ranks[0]):+.0f}"],
        ["Pos Mean Rank", f"#{pos_ranks[0]:.0f}", f"#{pos_ranks[1]:.0f}",
         f"#{pos_ranks[2]:.0f}", f"{(pos_ranks[2]-pos_ranks[0]):+.0f}"],
        ["Neg Mean Rank", f"#{neg_ranks[0]:.0f}", f"#{neg_ranks[1]:.0f}",
         f"#{neg_ranks[2]:.0f}", f"{(neg_ranks[2]-neg_ranks[0]):+.0f}"],
        ["Neg Median Rank", f"#{data['R0']['patent_neg']['median_rank']:.0f}",
         f"#{data['R1']['patent_neg']['median_rank']:.0f}",
         f"#{data['R2']['patent_neg']['median_rank']:.0f}", "—"],
        [f"Recall Top-500 ({n_total=})", f"{data['R0']['recall']['recall_top500']}/{n_total}",
         f"{data['R1']['recall']['recall_top500']}/{n_total}",
         f"{data['R2']['recall']['recall_top500']}/{n_total}", "—"],
    ]
    table = ax.table(cellText=rows, cellLoc="center", loc="center",
                     colWidths=[0.28, 0.16, 0.16, 0.16, 0.16])
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    for key, cell in table.get_celld().items():
        cell.set_linewidth(0.3)
        r, c = key
        if r == 0:
            cell.set_facecolor("#E8ECF0")
            cell.get_text().set_fontweight("bold")
        if r in (1, 2, 4, 5):
            cell.set_facecolor(C_GREEN_BG)
        if r == 3:
            cell.set_facecolor(C_RED_BG)
    ax.set_title("C. Key Metrics Summary", fontweight="bold", pad=8)

    # D: Strong Active Rank improvement
    ax = axes[1, 1]
    ax.bar(x, strong_ranks, color=C_ROUNDS, width=0.55, alpha=0.92, edgecolor=C_EDGE, lw=0.5)
    for i, v in enumerate(strong_ranks):
        ax.text(i, v + 2, f"#{v:.0f}", ha="center", fontsize=12, fontweight="bold")
        ax.text(i, v - 10, f"Top {v/n_pool*100:.2f}%", ha="center", fontsize=8,
                color=C_IMPROVED_DK, fontweight="bold")
    for i in range(1, 3):
        d = strong_ranks[i] - strong_ranks[i - 1]
        if d < 0:
            ax.annotate(f"↑{-d:.0f}", xy=(i, strong_ranks[i] - 25),
                        ha="center", fontsize=10, color=C_IMPROVED_DK, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ROUND_LABELS)
    ax.set_ylabel("Mean Rank (lower better)")
    ax.set_title(f"D. Strong Active (pDC50>8) Rank Improvement", fontweight="bold")
    ax.invert_yaxis()
    ax.set_facecolor(C_SCORE_BG)

    total_pct = (scores[2] - scores[0]) / scores[0] * 100
    fig.suptitle(
        f"E46 Plan B Dashboard — Progressive RL: Score Separation +{total_pct:.1f}%  |  "
        f"Strong Active Rank #{strong_ranks[0]:.0f}→#{strong_ranks[2]:.0f}  |  "
        f"Pool: {n_pool:,} mols (100k swxds + patent + R1 + R2)",
        fontsize=13, fontweight="bold", y=0.99
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, plt, "fig5_dashboard")


# ──────────────────────────────────────────────────────────────────
def main():
    doc = load()
    plt = setup_style()

    print("=" * 60)
    print("  E46 Plan B Visualization")
    print("=" * 60)

    print(doc["description"])
    config = doc["config"]
    print(f"  Pool: {config['pool_size']} | Patent: {config['n_patent']} "
          f"({config['n_patent_pos']} pos, {config['n_patent_neg']} neg) "
          f"| Strong: {config['n_strong']} | R1: {config['n_r1']} | R2: {config['n_r2']}")

    for r in ROUNDS:
        d = doc["results"][r]
        print(f"  {r}: pos #{d['patent_pos']['mean_rank']:.0f}  "
              f"neg #{d['patent_neg']['mean_rank']:.0f}  "
              f"strong #{d['strong_active']['mean_rank']:.0f}  "
              f"score_sep={d['score_separation']:.4f}  "
              f"recall500={d['recall']['recall_top500']}/{315}")

    fig1_score_separation(doc, plt)
    fig2_strong_active_rank(doc, plt)
    fig3_pos_neg_scores(doc, plt)
    fig4_recall(doc, plt)
    fig5_dashboard(doc, plt)

    print(f"\n  ✅ All figures → {OUT_DIR}")


if __name__ == "__main__":
    main()
