#!/usr/bin/env python3
"""E34 13-mol ranking visualization + comparison with E32/E33/CarsiScore."""
import json, sys
import numpy as np
from pathlib import Path

E34_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403')
E32_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e32_paper_al_20260630/wetlab_13_ranking')
OUT_DIR = E34_DIR / 'figures'

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load E34 results
    with open(E34_DIR / 'wetlab_13_similar_ranking.json') as f:
        e34_data = json.load(f)

    # Load E32 results (from earlier run)
    e32_data = None
    e32_json = E32_DIR / 'wetlab_13_similar_ranking.json'
    if e32_json.exists():
        with open(e32_json) as f:
            e32_data = json.load(f)

    # E34 per-molecule data
    e34_results = {r['wetlab_id']: r for r in e34_data['results']}

    # E32 per-molecule data
    e32_results = {}
    if e32_data:
        for r in e32_data['results']:
            e32_results[r['wetlab_id']] = r

    # CarsiScore baseline (same for all - from pool CSV row position)
    carsi_ranks = {
        '0228271': 200, '0228279': 4984, '0228283': 8529,
        '0228303': 1677, '0228366': 130, '0228390': 4913,
        '0228405': 246, '0228414': 1170, '0228416': 711,
        '0228417': 170, 'LXC-102': 2648, 'LXC-104': 4984, 'LXC-106': 3311,
    }

    n_pool = 10242
    labels = list(carsi_ranks.keys())

    e34_ranks = [e34_results[l]['glare_rank'] for l in labels]
    e32_ranks = [e32_results[l]['glare_e32_rank'] for l in labels] if e32_results else None
    carsi_r = [carsi_ranks[l] for l in labels]

    print("=" * 80)
    print("  E34 vs E32 vs E33 vs CarsiScore: 13 Similar Molecules Ranking")
    print("=" * 80)

    # === Summary stats ===
    print(f"\n  {'Method':>20s} {'Mean Rank':>12s} {'Median':>8s} {'Best':>8s} {'Worst':>8s} "
          f"{'Top 10%':>8s} {'Top 25%':>8s} {'Top 50%':>8s}")
    print(f"  {'─'*80}")

    for label, ranks in [
        ('CarsiScore', carsi_r),
        ('GLARE E32', e32_ranks),
        ('GLARE E33', [2464, 1733, 8908, 5162, 5803, 2090, 4195, 1212, 4743, 1907, 587, 1733, 5481]),  # from E33 summary
        ('GLARE E34', e34_ranks),
    ]:
        if not ranks:
            continue
        arr = np.array(ranks)
        print(f"  {label:>20s} {np.mean(arr):>10.1f}  {np.median(arr):>8.1f}  "
              f"{int(np.min(arr)):>8d}  {int(np.max(arr)):>8d}  "
              f"{sum(arr <= n_pool*0.10):>8d}  {sum(arr <= n_pool*0.25):>8d}  {sum(arr <= n_pool*0.50):>8d}")

    # === Per-molecule comparison table ===
    print(f"\n  {'WetLab':>10s} {'MolFactory':>16s} {'Carsi':>7s} {'E32':>7s} {'E33':>7s} {'E34':>7s} {'Best':>7s}")
    print(f"  {'─'*70}")

    for label in labels:
        e34r = e34_results[label]['glare_rank']
        e32r = e32_results[label]['glare_e32_rank'] if label in e32_results else '?'
        e33r_map = {
            '0228271': 2464, '0228279': 1733, '0228283': 8908, '0228303': 5162, '0228366': 5803,
            '0228390': 2090, '0228405': 4195, '0228414': 1212, '0228416': 4743, '0228417': 1907,
            'LXC-102': 587, 'LXC-104': 1733, 'LXC-106': 5481,
        }
        e33r = e33r_map.get(label, '?')
        cr = carsi_ranks[label]
        best = min([cr, e32r if isinstance(e32r, (int, float)) else 99999, e33r if isinstance(e33r, (int, float)) else 99999, e34r])
        best_marker = ''
        if best == e34r: best_marker = '🟢'
        elif best == e32r and isinstance(e32r, (int, float)): best_marker = '🔵'
        elif best == e33r and isinstance(e33r, int): best_marker = '🟡'
        elif best == cr: best_marker = '🔴'

        mf_id = e34_results[label]['molfactory_id']
        print(f"  {label:>10s} {mf_id:>16s} {cr:>7d} {str(e32r):>7s} {str(e33r):>7s} {e34r:>7d} {best_marker:>7s}")

    print(f"\n  🟢 = E34 best, 🔵 = E32 best, 🟡 = E33 best, 🔴 = CarsiScore best")

    # === Generate figures ===
    plot_comparison_bar(labels, e34_ranks, e32_ranks, e33r_map, carsi_r, n_pool, OUT_DIR)
    plot_enrichment_compare(labels, e34_ranks, e32_ranks, carsi_r, n_pool, OUT_DIR)
    plot_scatter_compare(labels, e34_ranks, e32_ranks, carsi_r, OUT_DIR)

    print(f"\n✅ All figures saved to: {OUT_DIR}")


def plot_comparison_bar(labels, e34_ranks, e32_ranks, e33r_map, carsi_r, n_pool, out_dir):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 10,
        'figure.dpi': 150, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'axes.spines.top': False, 'axes.spines.right': False,
    })

    x = np.arange(len(labels))
    width = 0.2
    fig, ax = plt.subplots(figsize=(16, 6))

    ax.bar(x - 1.5*width, carsi_r, width, color='#B2182B', alpha=0.85, label='CarsiScore', zorder=3)
    if e32_ranks:
        ax.bar(x - 0.5*width, e32_ranks, width, color='#2166AC', alpha=0.85, label='GLARE E32', zorder=3)
    e33_r = [e33r_map.get(l) for l in labels]
    ax.bar(x + 0.5*width, e33_r, width, color='#92C5DE', alpha=0.85, label='GLARE E33', zorder=3)
    ax.bar(x + 1.5*width, e34_ranks, width, color='#D4A017', alpha=0.9, label='GLARE E34 ★', zorder=3)

    # Mean lines
    ax.axhline(np.mean(carsi_r), color='#B2182B', linestyle='--', alpha=0.4, linewidth=1)
    if e32_ranks:
        ax.axhline(np.mean(e32_ranks), color='#2166AC', linestyle='--', alpha=0.4, linewidth=1)
    ax.axhline(np.mean(e33_r), color='#92C5DE', linestyle='--', alpha=0.4, linewidth=1)
    ax.axhline(np.mean(e34_ranks), color='#D4A017', linestyle='--', alpha=0.6, linewidth=1.5)

    ax.axhline(n_pool * 0.10, color='gray', linestyle=':', alpha=0.3, linewidth=0.8)
    ax.text(len(labels) - 0.5, n_pool * 0.10 + 200, 'Top 10%', fontsize=7, color='gray', ha='right')

    ax.set_xticks(x)
    short_labels = [f"{l}\n→{e33r_map.get(l, '?')}"[:14] for l in labels]
    ax.set_xticklabels(['→'.join(l.split('→')[:2]) for l in [f"{l}" for l in labels]], rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Rank (lower = better)')
    ax.set_title(f'E34: Full 403 Training vs Baselines — 13 Wet-Lab Similar Molecules\n'
                 f'Pool N={n_pool} | E34 cycle_7 mean=#{np.mean(e34_ranks):.0f} (top {100*np.mean(e34_ranks)/n_pool:.1f}%)')
    ax.legend(frameon=False, loc='upper right')
    ax.set_ylim(0, n_pool * 1.05)
    ax.invert_yaxis()

    stats_text = f'Mean: Carsi=#{np.mean(carsi_r):.0f}'
    if e32_ranks:
        stats_text += f' | E32=#{np.mean(e32_ranks):.0f}'
    stats_text += f' | E33=#{np.mean(e33_r):.0f} | E34=#{np.mean(e34_ranks):.0f}'
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=7, va='top',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_e34_comparison_bar.png', dpi=300)
    fig.savefig(out_dir / 'fig_e34_comparison_bar.svg')
    plt.close()
    print("  ✅ fig_e34_comparison_bar.png/.svg")


def plot_enrichment_compare(labels, e34_ranks, e32_ranks, carsi_r, n_pool, out_dir):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 10,
        'figure.dpi': 150, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'axes.spines.top': False, 'axes.spines.right': False,
    })

    fig, ax = plt.subplots(figsize=(7, 6))
    colors = {'CarsiScore': '#B2182B', 'GLARE E32': '#2166AC', 'GLARE E34': '#D4A017'}

    for label, ranks, color in [
        ('CarsiScore', carsi_r, colors['CarsiScore']),
        ('GLARE E32', e32_ranks, colors['GLARE E32']),
        ('GLARE E34', e34_ranks, colors['GLARE E34']),
    ]:
        if not ranks:
            continue
        sorted_ranks = sorted(ranks)
        x_vals = np.linspace(0, 100, 500)
        y_vals = []
        for xp in x_vals:
            cutoff = n_pool * xp / 100
            y_vals.append(sum(1 for r in sorted_ranks if r <= cutoff) / len(sorted_ranks) * 100)
        ax.plot(x_vals, y_vals, color=color, linewidth=2, label=label)

    ax.plot([0, 100], [0, 100], 'k--', alpha=0.3, linewidth=1, label='Random')
    ax.set_xlabel('Top % of Ranked Pool')
    ax.set_ylabel('Cumulative % of 13 Molecules Found')
    ax.set_title('Enrichment Curve: E34 vs Baselines')
    ax.legend(frameon=False, loc='lower right')
    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_e34_enrichment.png', dpi=300)
    fig.savefig(out_dir / 'fig_e34_enrichment.svg')
    plt.close()
    print("  ✅ fig_e34_enrichment.png/.svg")


def plot_scatter_compare(labels, e34_ranks, e32_ranks, carsi_r, out_dir):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 10,
        'figure.dpi': 150, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'axes.spines.top': False, 'axes.spines.right': False,
    })

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    for ax, ranks, title, label in [
        (ax1, e32_ranks, 'E32 vs CarsiScore', 'E32'),
        (ax2, e34_ranks, 'E34 vs CarsiScore', 'E34'),
    ]:
        if not ranks:
            continue
        ax.scatter(carsi_r, ranks, s=60, alpha=0.8, zorder=5, edgecolors='black', linewidth=0.5)
        for i, l in enumerate(labels):
            ax.annotate(l, (carsi_r[i], ranks[i]), fontsize=6, alpha=0.7,
                       xytext=(3, 3), textcoords='offset points')
        max_val = max(max(carsi_r), max(ranks))
        ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.2, linewidth=1)
        ax.set_xlabel('CarsiScore Rank')
        ax.set_ylabel(f'GLARE {label} Rank')
        ax.set_title(title)
        ax.invert_xaxis(); ax.invert_yaxis()

        # Pearson correlation
        corr = np.corrcoef(carsi_r, ranks)[0, 1]
        ax.text(0.05, 0.95, f'Pearson r={corr:.3f}', transform=ax.transAxes,
                fontsize=8, va='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_e34_scatter_compare.png', dpi=300)
    fig.savefig(out_dir / 'fig_e34_scatter_compare.svg')
    plt.close()
    print("  ✅ fig_e34_scatter_compare.png/.svg")


if __name__ == '__main__':
    main()