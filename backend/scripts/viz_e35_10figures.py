#!/usr/bin/env python3
"""E34 vs E35 v2: 10 张论文级虚拟筛选可视化。

参考: Nature Drug Discovery, J. Med. Chem., JCIM, J. Chem. Inf. Model. 等期刊的
虚拟筛选/分子排序评估图标准。10 张图覆盖: 排名对比、富集、分布、变化、汇总。

Figures:
  1.  Ranked bar chart — E34/E35 逐分子排名对比
  2.  Waterfall plot — 排名变化 Δ
  3.  Enrichment curve — 累积富集曲线
  4.  Scatter: E34 vs E35 — 排名散点图
  5.  Box plot — 正/负样本排名分布
  6.  ECDF — 排名百分位累积分布
  7.  Top-N enrichment bar — 各阈值命中数
  8.  Rank percentile heatmap — 分子×方法 排名矩阵
  9.  Volcano/difference — 变化幅度 vs 显著性
  10. Summary dashboard — 四合一总览
"""
import json, sys
import numpy as np
from pathlib import Path

E34_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403')
E35_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e35_finetune_13wetlab')
OUT_DIR = E35_DIR / 'figures'

WETLAB_MAP = [
    ('0228271', '200',   0.632), ('0228279', '4984',  0.554), ('0228283', '8529',  0.581),
    ('0228303', '1677',  1.000), ('0228366', '130',   1.000), ('0228390', '4913',  0.764),
    ('0228405', '246',   0.650), ('0228414', '1170',  1.000), ('0228416', '711',   0.614),
    ('0228417', '170',   0.621), ('LXC-102', '2648',  0.621), ('LXC-104', '4984',  0.554),
    ('LXC-106', '3311',  0.617),
]
POSITIVE_IDS = {'0228390', '0228414', 'LXC-106'}
N_POOL = 10242

def load_data():
    with open(E34_DIR / 'wetlab_13_similar_ranking.json') as f:
        e34 = json.load(f)
    with open(E35_DIR / 'wetlab_13_ranking_pre_vs_post_v2.json') as f:
        e35 = json.load(f)

    e34_map = {r['wetlab_id']: r for r in e34['results']}
    e35_map = {r['wetlab_id']: r for r in e35['e35_post']['results']}

    molecules = []
    for wetlab_id, mf_id, tanimoto in WETLAB_MAP:
        e34_r = e34_map.get(wetlab_id, {})
        e35_r = e35_map.get(wetlab_id, {})
        molecules.append({
            'wetlab_id': wetlab_id,
            'molfactory_id': f'MolFactory_{mf_id}',
            'tanimoto': tanimoto,
            'is_positive': wetlab_id in POSITIVE_IDS,
            'e34_rank': e34_r.get('glare_rank'),
            'e34_pct': e34_r.get('glare_pct'),
            'e35_rank': e35_r.get('glare_rank'),
            'e35_pct': e35_r.get('glare_pct'),
            'carsi_rank': e35_r.get('carsi_rank'),
        })
    return molecules, e34, e35

def setup_style():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 10,
        'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 8,
        'figure.dpi': 150, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'axes.spines.top': False, 'axes.spines.right': False,
    })
    return plt

# ── Color palette (Nature-friendly, colorblind-aware) ────────
C_POS = '#D4A017'     # gold — positive
C_NEG = '#2166AC'     # blue — negative
C_E34 = '#92C5DE'     # light blue — E34 pre
C_E35 = '#B2182B'     # red — E35 post
C_CARSI = '#4DAF4A'   # green — CarsiScore
C_IMPROVED = '#27AE60'
C_WORSE = '#E74C3C'
C_NEUTRAL = '#95A5A6'

def fig1_bar_chart(mols, plt):
    """Ranked bar chart: E34 vs E35 per molecule, sorted by E34 rank."""
    mols_sorted = sorted(mols, key=lambda m: m['e34_rank'])
    labels = [f"{m['wetlab_id']}" for m in mols_sorted]
    e34_r = [m['e34_rank'] for m in mols_sorted]
    e35_r = [m['e35_rank'] for m in mols_sorted]
    colors = [C_POS if m['is_positive'] else C_NEG for m in mols_sorted]

    x = np.arange(len(mols_sorted))
    width = 0.35
    fig, ax = plt.subplots(figsize=(15, 6))

    bars1 = ax.bar(x - width/2, e34_r, width, color=C_E34, alpha=0.85, label='E34 (Pre FT)', zorder=3)
    bars2 = ax.bar(x + width/2, e35_r, width, color=C_E35, alpha=0.85, label='E35 v2 (Post FT)', zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('GLARE Rank (lower = better)')
    ax.set_title('Figure 1: Per-Molecule Ranking — E34 vs E35 v2 Fine-Tune')
    ax.set_ylim(0, max(max(e34_r), max(e35_r)) * 1.1)
    ax.invert_yaxis()

    ax.axhline(np.mean(e34_r), color=C_E34, linestyle='--', alpha=0.4, lw=1)
    ax.axhline(np.mean(e35_r), color=C_E35, linestyle='--', alpha=0.5, lw=1.5)
    ax.axhline(N_POOL * 0.10, color='gray', linestyle=':', alpha=0.3, lw=0.8)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_E34, alpha=0.85, label=f'E34 (mean #{np.mean(e34_r):.0f}, {100*np.mean(e34_r)/N_POOL:.1f}%)'),
        Patch(facecolor=C_E35, alpha=0.85, label=f'E35 v2 (mean #{np.mean(e35_r):.0f}, {100*np.mean(e35_r)/N_POOL:.1f}%)'),
        Patch(facecolor=C_POS, alpha=0.7, label='Positive (3)'),
        Patch(facecolor=C_NEG, alpha=0.7, label='Negative (10)'),
    ]
    ax.legend(handles=legend_elements, frameon=False, loc='upper left', fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('GLARE Rank (lower = better)')
    ax.set_title('Figure 1: Per-Molecule Ranking — E34 vs E35 v2 Fine-Tune')
    ax.set_ylim(0, max(max(e34_r), max(e35_r)) * 1.1)
    ax.invert_yaxis()

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig1_ranking_bar.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig1_ranking_bar.svg')
    plt.close()
    print("  ✅ fig1_ranking_bar")


def fig2_waterfall(mols, plt):
    """Waterfall plot: rank change Δ per molecule."""
    mols_sorted = sorted(mols, key=lambda m: m['e34_rank'] - (m['e35_rank'] or 0), reverse=True)
    labels = [f"{m['wetlab_id']}" for m in mols_sorted]
    deltas = [m['e34_rank'] - m['e35_rank'] for m in mols_sorted]
    colors = [C_IMPROVED if d > 0 else C_WORSE for d in deltas]

    fig, ax = plt.subplots(figsize=(14, 6))
    x = np.arange(len(mols_sorted))
    bars = ax.bar(x, deltas, color=colors, alpha=0.85, zorder=3, edgecolor='white', lw=0.5)

    # Add value labels
    for i, (d, c) in enumerate(zip(deltas, colors)):
        va = 'bottom' if d >= 0 else 'top'
        ax.text(i, d + (200 if d >= 0 else -200), f'{d:+d}', ha='center', va=va, fontsize=7, color=c, fontweight='bold')

    ax.axhline(0, color='black', lw=0.8, zorder=2)
    ax.axhline(np.mean(deltas), color='gray', linestyle='--', alpha=0.5, lw=1)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_IMPROVED, alpha=0.85, label=f'Improved ({sum(1 for d in deltas if d>0)}/13)'),
        Patch(facecolor=C_WORSE, alpha=0.85, label=f'Worse ({sum(1 for d in deltas if d<0)}/13)'),
    ]
    ax.legend(handles=legend_elements, frameon=False, loc='upper right')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Δ Rank (E34 − E35, positive = improved)')
    ax.set_title(f'Figure 2: Rank Change Waterfall — Mean Δ = {np.mean(deltas):+.0f} ranks')
    ax.axhline(0, color='black', lw=0.5)

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig2_waterfall.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig2_waterfall.svg')
    plt.close()
    print("  ✅ fig2_waterfall")


def fig3_enrichment(mols, plt):
    """Enrichment curve: cumulative % found vs top % of ranked pool."""
    fig, ax = plt.subplots(figsize=(7, 6))

    for label, rank_key, color, ls in [
        ('E34', 'e34_rank', C_E34, '-'),
        ('E35 v2', 'e35_rank', C_E35, '-'),
        ('CarsiScore', 'carsi_rank', C_CARSI, '--'),
    ]:
        ranks = sorted([m[rank_key] for m in mols if m[rank_key] is not None])
        if not ranks:
            continue
        x_vals = np.linspace(0, 100, 500)
        y_vals = []
        for xp in x_vals:
            cutoff = N_POOL * xp / 100
            y_vals.append(sum(1 for r in ranks if r <= cutoff) / len(ranks) * 100)
        ax.plot(x_vals, y_vals, color=color, linestyle=ls, linewidth=2, label=label, alpha=0.9)

    ax.plot([0, 100], [0, 100], 'k--', alpha=0.2, lw=1, label='Random')
    ax.set_xlabel('Top % of Ranked Pool')
    ax.set_ylabel('Cumulative % of 13 Molecules Retrieved')
    ax.set_title('Figure 3: Enrichment Curve')
    ax.legend(frameon=False, loc='lower right')
    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig3_enrichment.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig3_enrichment.svg')
    plt.close()
    print("  ✅ fig3_enrichment")


def fig4_scatter(mols, plt):
    """Scatter: E34 rank vs E35 rank."""
    fig, ax = plt.subplots(figsize=(7, 7))

    for m in mols:
        color = C_POS if m['is_positive'] else C_NEG
        marker = 's' if m['is_positive'] else 'o'
        size = 120 if m['is_positive'] else 80
        ax.scatter(m['e34_rank'], m['e35_rank'], c=color, marker=marker, s=size,
                  edgecolors='black', lw=0.5, zorder=5, alpha=0.85)
        ax.annotate(m['wetlab_id'], (m['e34_rank'], m['e35_rank']),
                   fontsize=6, alpha=0.7, xytext=(4, 4), textcoords='offset points')

    max_val = max(max(m['e34_rank'] for m in mols), max(m['e35_rank'] for m in mols))
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.2, lw=1, label='Identity')

    # Quadrant lines at top 10%
    top10 = N_POOL * 0.10
    ax.axhline(top10, color='green', linestyle=':', alpha=0.3, lw=0.8)
    ax.axvline(top10, color='green', linestyle=':', alpha=0.3, lw=0.8)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_POS, alpha=0.7, label='Positive (3)'),
        Patch(facecolor=C_NEG, alpha=0.7, label='Negative (10)'),
    ]
    ax.legend(handles=legend_elements, frameon=False, loc='lower right')

    # Correlation
    e34_r = [m['e34_rank'] for m in mols]
    e35_r = [m['e35_rank'] for m in mols]
    corr = np.corrcoef(e34_r, e35_r)[0, 1]
    ax.text(0.05, 0.95, f'Pearson r = {corr:.3f}\nSpearman ρ = {np.corrcoef(np.argsort(e34_r), np.argsort(e35_r))[0,1]:.3f}',
            transform=ax.transAxes, fontsize=8, va='top',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.set_xlabel('E34 GLARE Rank')
    ax.set_ylabel('E35 v2 GLARE Rank')
    ax.set_title('Figure 4: E34 vs E35 — Rank Correlation')
    ax.invert_xaxis(); ax.invert_yaxis()

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig4_scatter.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig4_scatter.svg')
    plt.close()
    print("  ✅ fig4_scatter")


def fig5_boxplot(mols, plt):
    """Box plot: rank distribution by method and label."""
    fig, ax = plt.subplots(figsize=(8, 6))

    pos_e34 = [m['e34_rank'] for m in mols if m['is_positive']]
    neg_e34 = [m['e34_rank'] for m in mols if not m['is_positive']]
    pos_e35 = [m['e35_rank'] for m in mols if m['is_positive']]
    neg_e35 = [m['e35_rank'] for m in mols if not m['is_positive']]

    positions = [1, 2, 4, 5]
    data = [pos_e34, pos_e35, neg_e34, neg_e35]
    colors = [C_POS, C_POS, C_NEG, C_NEG]
    alphas = [0.6, 0.9, 0.6, 0.9]

    bp = ax.boxplot(data, positions=positions, widths=0.6, patch_artist=True,
                     medianprops={'color': 'black', 'lw': 1.5},
                     flierprops={'marker': 'o', 'markersize': 4, 'alpha': 0.5})

    for patch, color, alpha in zip(bp['boxes'], colors, alphas):
        patch.set_facecolor(color)
        patch.set_alpha(alpha)

    # Add individual points
    for i, (pos, d, c) in enumerate(zip(positions, data, colors)):
        jitter = np.random.default_rng(42).normal(0, 0.05, len(d))
        ax.scatter([pos] * len(d) + jitter, d, c=c, s=30, alpha=0.7, zorder=5, edgecolors='white', lw=0.5)

    ax.set_xticks([1.5, 4.5])
    ax.set_xticklabels(['Positive (n=3)', 'Negative (n=10)'])
    ax.set_ylabel('GLARE Rank')
    ax.set_title('Figure 5: Rank Distribution — Positive vs Negative')
    ax.invert_yaxis()

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_E34, alpha=0.6, label='E34'),
        Patch(facecolor=C_E35, alpha=0.9, label='E35 v2'),
    ]
    ax.legend(handles=legend_elements, frameon=False, loc='upper right')

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig5_boxplot.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig5_boxplot.svg')
    plt.close()
    print("  ✅ fig5_boxplot")


def fig6_ecdf(mols, plt):
    """ECDF of rank percentiles."""
    fig, ax = plt.subplots(figsize=(7, 6))

    for label, rank_key, color, ls in [
        ('E34', 'e34_rank', C_E34, '-'),
        ('E35 v2', 'e35_rank', C_E35, '-'),
        ('CarsiScore', 'carsi_rank', C_CARSI, '--'),
    ]:
        ranks = sorted([m[rank_key] for m in mols if m[rank_key] is not None])
        if not ranks:
            continue
        pcts = [r / N_POOL * 100 for r in ranks]
        y = np.arange(1, len(pcts) + 1) / len(pcts)
        ax.step(pcts, y, where='post', color=color, linestyle=ls, linewidth=2, label=label, alpha=0.9)

    ax.plot([0, 100], [0, 1], 'k--', alpha=0.2, lw=1, label='Random')
    ax.set_xlabel('Rank Percentile')
    ax.set_ylabel('Cumulative Fraction of Molecules')
    ax.set_title('Figure 6: Empirical Cumulative Distribution of Rank Percentiles')
    ax.legend(frameon=False, loc='lower right')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 1.05)

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig6_ecdf.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig6_ecdf.svg')
    plt.close()
    print("  ✅ fig6_ecdf")


def fig7_topn_bars(mols, plt):
    """Top-N enrichment: how many molecules in top 1%/5%/10%/25%/50%."""
    thresholds = [0.01, 0.05, 0.10, 0.25, 0.50]
    labels = ['Top 1%', 'Top 5%', 'Top 10%', 'Top 25%', 'Top 50%']

    e34_counts = [sum(1 for m in mols if m['e34_rank'] <= N_POOL * t) for t in thresholds]
    e35_counts = [sum(1 for m in mols if m['e35_rank'] <= N_POOL * t) for t in thresholds]
    carsi_counts = [sum(1 for m in mols if m['carsi_rank'] <= N_POOL * t) for t in thresholds]
    expected = [13 * t for t in thresholds]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(labels))
    width = 0.2

    ax.bar(x - width, e34_counts, width, color=C_E34, alpha=0.85, label='E34', zorder=3)
    ax.bar(x, e35_counts, width, color=C_E35, alpha=0.85, label='E35 v2', zorder=3)
    ax.bar(x + width, carsi_counts, width, color=C_CARSI, alpha=0.85, label='CarsiScore', zorder=3)

    # Expected line
    ax.plot(x, expected, 'k--', alpha=0.3, lw=1, marker='o', markersize=3, label='Random expectation')

    for i in range(len(labels)):
        if e34_counts[i] > 0: ax.text(i - width, e34_counts[i] + 0.2, str(e34_counts[i]), ha='center', fontsize=8, fontweight='bold')
        if e35_counts[i] > 0: ax.text(i, e35_counts[i] + 0.2, str(e35_counts[i]), ha='center', fontsize=8, fontweight='bold')
        if carsi_counts[i] > 0: ax.text(i + width, carsi_counts[i] + 0.2, str(carsi_counts[i]), ha='center', fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel('Molecules Retrieved (out of 13)')
    ax.set_title('Figure 7: Top-N Enrichment — Molecules Retrieved at Each Threshold')
    ax.legend(frameon=False, loc='upper left')
    ax.set_ylim(0, 14)

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig7_topn_bars.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig7_topn_bars.svg')
    plt.close()
    print("  ✅ fig7_topn_bars")


def fig8_heatmap(mols, plt):
    """Rank percentile heatmap: molecules × methods."""
    # Sort by E34 rank
    mols_sorted = sorted(mols, key=lambda m: m['e34_rank'])
    row_labels = [f"{m['wetlab_id']}" for m in mols_sorted]
    data = np.array([
        [m['e34_rank'] / N_POOL * 100 for m in mols_sorted],
        [m['e35_rank'] / N_POOL * 100 for m in mols_sorted],
        [m['carsi_rank'] / N_POOL * 100 for m in mols_sorted],
    ])

    fig, ax = plt.subplots(figsize=(12, 4))
    im = ax.imshow(data, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=100)

    # Annotate
    for i in range(3):
        for j in range(len(mols_sorted)):
            val = data[i, j]
            color = 'white' if val > 50 else 'black'
            ax.text(j, i, f'{val:.1f}%', ha='center', va='center', fontsize=7, color=color, fontweight='bold')

    ax.set_xticks(range(len(row_labels)))
    ax.set_xticklabels(row_labels, rotation=45, ha='right', fontsize=8)
    ax.set_yticks(range(3))
    ax.set_yticklabels(['E34', 'E35 v2', 'CarsiScore'])

    # Color-code positive labels
    for j, m in enumerate(mols_sorted):
        if m['is_positive']:
            ax.get_xticklabels()[j].set_color(C_POS)
            ax.get_xticklabels()[j].set_fontweight('bold')

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Rank Percentile (%)', fontsize=8)

    ax.set_title('Figure 8: Rank Percentile Heatmap — Molecules × Methods')
    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig8_heatmap.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig8_heatmap.svg')
    plt.close()
    print("  ✅ fig8_heatmap")


def fig9_volcano(mols, plt):
    """Volcano-style: |Δ rank| vs mean rank, bubble size = Tanimoto."""
    fig, ax = plt.subplots(figsize=(9, 7))

    for m in mols:
        delta = m['e34_rank'] - m['e35_rank']
        mean_rank = (m['e34_rank'] + m['e35_rank']) / 2
        abs_delta = abs(delta)
        color = C_IMPROVED if delta > 0 else C_WORSE
        size = 80 + m['tanimoto'] * 200

        ax.scatter(mean_rank, abs_delta, s=size, c=color, alpha=0.8, zorder=5,
                  edgecolors='black', lw=0.5)
        ax.annotate(m['wetlab_id'], (mean_rank, abs_delta),
                   fontsize=7, alpha=0.8, xytext=(5, 5), textcoords='offset points')

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=C_IMPROVED, alpha=0.8, label=f'Improved ({sum(1 for m in mols if m["e34_rank"] > m["e35_rank"])})'),
        Patch(facecolor=C_WORSE, alpha=0.8, label=f'Worse ({sum(1 for m in mols if m["e34_rank"] < m["e35_rank"])})'),
    ]
    ax.legend(handles=legend_elements, frameon=False, loc='upper right')

    # Annotate bubble size
    ax.text(0.95, 0.95, 'Bubble size ∝ Tanimoto similarity', transform=ax.transAxes,
            fontsize=7, ha='right', va='top', alpha=0.5)

    ax.set_xlabel('Mean Rank (E34 + E35) / 2')
    ax.set_ylabel('|Δ Rank| = |E34 − E35|')
    ax.set_title('Figure 9: Rank Change Volcano — Magnitude vs Baseline')

    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig9_volcano.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig9_volcano.svg')
    plt.close()
    print("  ✅ fig9_volcano")


def fig10_dashboard(mols, e34_data, e35_data, plt):
    """4-panel summary dashboard."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # Panel A: Rank bar chart (compact)
    ax = axes[0, 0]
    mols_sorted = sorted(mols, key=lambda m: m['e34_rank'])
    labels = [m['wetlab_id'] for m in mols_sorted]
    x = np.arange(len(mols_sorted))
    width = 0.35
    ax.bar(x - width/2, [m['e34_rank'] for m in mols_sorted], width, color=C_E34, alpha=0.85, label='E34')
    ax.bar(x + width/2, [m['e35_rank'] for m in mols_sorted], width, color=C_E35, alpha=0.85, label='E35 v2')
    ax.axhline(np.mean([m['e34_rank'] for m in mols_sorted]), color=C_E34, linestyle='--', alpha=0.3, lw=1)
    ax.axhline(np.mean([m['e35_rank'] for m in mols_sorted]), color=C_E35, linestyle='--', alpha=0.4, lw=1)
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Rank'); ax.set_title('A. Per-Molecule Ranking'); ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=7)

    # Panel B: Enrichment (compact)
    ax = axes[0, 1]
    for label, rk, c, ls in [('E34', 'e34_rank', C_E34, '-'), ('E35', 'e35_rank', C_E35, '-'), ('Carsi', 'carsi_rank', C_CARSI, '--')]:
        ranks = sorted([m[rk] for m in mols if m[rk] is not None])
        xv = np.linspace(0, 100, 300)
        yv = [sum(1 for r in ranks if r <= N_POOL * xp / 100) / len(ranks) * 100 for xp in xv]
        ax.plot(xv, yv, color=c, ls=ls, lw=2, label=label)
    ax.plot([0, 100], [0, 100], 'k--', alpha=0.2, lw=1)
    ax.set_xlabel('Top % of Pool'); ax.set_ylabel('Cumulative % Found')
    ax.set_title('B. Enrichment Curve'); ax.legend(frameon=False, fontsize=7)
    ax.set_xlim(0, 50); ax.set_ylim(0, 105)

    # Panel C: Summary stats table
    ax = axes[1, 0]
    ax.axis('off')
    stats = [
        ['Metric', 'E34', 'E35 v2', 'Δ'],
        ['Mean Rank', f'#{e34_data["mean_rank"]:.0f}', f'#{e35_data["e35_post"]["mean_rank"]:.0f}',
         f'{e34_data["mean_rank"] - e35_data["e35_post"]["mean_rank"]:+.0f}'],
        ['Mean %ile', f'{e34_data["mean_pct"]:.1f}%', f'{100*e35_data["e35_post"]["mean_rank"]/N_POOL:.1f}%',
         f'{e34_data["mean_pct"] - 100*e35_data["e35_post"]["mean_rank"]/N_POOL:+.1f}%'],
        ['Top 10%', str(e34_data['top_10pct']), str(e35_data['e35_post']['top_10pct']),
         f'{e35_data["e35_post"]["top_10pct"] - e34_data["top_10pct"]:+d}'],
        ['Top 25%', str(e34_data['top_25pct']), str(e35_data['e35_post']['top_25pct']),
         f'{e35_data["e35_post"]["top_25pct"] - e34_data["top_25pct"]:+d}'],
        ['Top 50%', str(e34_data['top_50pct']), str(e35_data['e35_post']['top_50pct']),
         f'{e35_data["e35_post"]["top_50pct"] - e34_data["top_50pct"]:+d}'],
        ['Pos Mean', f'#{np.mean([m["e34_rank"] for m in mols if m["is_positive"]]):.0f}',
         f'#{np.mean([m["e35_rank"] for m in mols if m["is_positive"]]):.0f}',
         f'{np.mean([m["e34_rank"] - m["e35_rank"] for m in mols if m["is_positive"]]):+.0f}'],
        ['Neg Mean', f'#{np.mean([m["e34_rank"] for m in mols if not m["is_positive"]]):.0f}',
         f'#{np.mean([m["e35_rank"] for m in mols if not m["is_positive"]]):.0f}',
         f'{np.mean([m["e34_rank"] - m["e35_rank"] for m in mols if not m["is_positive"]]):+.0f}'],
        ['Improved', '', '', f'{sum(1 for m in mols if m["e34_rank"] > m["e35_rank"])}/13'],
        ['Worse', '', '', f'{sum(1 for m in mols if m["e34_rank"] < m["e35_rank"])}/13'],
    ]
    table = ax.table(cellText=stats, cellLoc='center', loc='center',
                     colWidths=[0.2, 0.15, 0.15, 0.12])
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    for key, cell in table.get_celld().items():
        cell.set_linewidth(0.3)
        if key[0] == 0:
            cell.set_facecolor('#f0f0f0')
            cell.get_text().set_fontweight('bold')
    ax.set_title('C. Summary Statistics')

    # Panel D: Scatter (compact)
    ax = axes[1, 1]
    for m in mols:
        c = C_POS if m['is_positive'] else C_NEG
        ax.scatter(m['e34_rank'], m['e35_rank'], c=c, s=80, alpha=0.8, zorder=5, edgecolors='black', lw=0.3)
        ax.annotate(m['wetlab_id'], (m['e34_rank'], m['e35_rank']), fontsize=5, alpha=0.6, xytext=(3, 3), textcoords='offset points')
    mv = max(max(m['e34_rank'] for m in mols), max(m['e35_rank'] for m in mols))
    ax.plot([0, mv], [0, mv], 'k--', alpha=0.2, lw=1)
    ax.set_xlabel('E34 Rank'); ax.set_ylabel('E35 v2 Rank')
    ax.set_title('D. Rank Correlation'); ax.invert_xaxis(); ax.invert_yaxis()

    fig.suptitle('Figure 10: E34 vs E35 v2 — Fine-Tune Impact Summary Dashboard',
                 fontsize=13, fontweight='bold', y=0.98)
    plt.tight_layout()
    fig.savefig(OUT_DIR / 'fig10_dashboard.png', dpi=300)
    fig.savefig(OUT_DIR / 'fig10_dashboard.svg')
    plt.close()
    print("  ✅ fig10_dashboard")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mols, e34, e35 = load_data()
    plt = setup_style()

    print("=" * 60)
    print("  Generating 10 Publication-Quality Figures")
    print("=" * 60)

    fig1_bar_chart(mols, plt)
    fig2_waterfall(mols, plt)
    fig3_enrichment(mols, plt)
    fig4_scatter(mols, plt)
    fig5_boxplot(mols, plt)
    fig6_ecdf(mols, plt)
    fig7_topn_bars(mols, plt)
    fig8_heatmap(mols, plt)
    fig9_volcano(mols, plt)
    fig10_dashboard(mols, e34, e35, plt)

    print(f"\n✅ All 10 figures saved to: {OUT_DIR}")
    print(f"   Formats: PNG (300dpi) + SVG (vector)")


if __name__ == '__main__':
    main()