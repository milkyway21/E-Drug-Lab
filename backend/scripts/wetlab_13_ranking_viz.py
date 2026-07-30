#!/usr/bin/env python3
"""
13 Wet-Lab → MolFactory 相似分子排名 + 论文级可视化
使用 E32 cycle_7 权重 (Combined=0.8531, PASS)，对 10K MolFactory 池做 GLARE 排名，
汇总 13 个对应 MolFactory 分子的 GLARE + CarsiScore 排名。
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem

# ── Paths ───────────────────────────────────────────────────
BASE = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project')
E32_RANKED = BASE / 'validation/molfactory_screen_20260706/ranked_10k_e32_grpo_sup.json'
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
OUT_DIR = BASE / 'validation/glare_e32_paper_al_20260630/wetlab_13_ranking'
E33_RANKED = BASE / 'validation/glare_e33_full_patent_20260709/ranked_10k_e33_grpo_sup.json'

# ── 13 Wet-Lab → MolFactory mapping (user-provided) ─────────
WETLAB_MAP = [
    ('0228271', '200',   0.632, False),
    ('0228279', '4984',  0.554, False),
    ('0228283', '8529',  0.581, False),
    ('0228303', '1677',  1.000, True),   # exact match
    ('0228366', '130',   1.000, True),   # exact match
    ('0228390', '4913',  0.764, False),
    ('0228405', '246',   0.650, False),
    ('0228414', '1170',  1.000, True),   # exact match
    ('0228416', '711',   0.614, False),
    ('0228417', '170',   0.621, False),
    ('LXC-102', '2648',  0.621, False),
    ('LXC-104', '4984',  0.554, False),
    ('LXC-106', '3311',  0.617, False),
]

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 90)
    print("  13 Wet-Lab → MolFactory Similar Molecules: E32 GLARE + CarsiScore Ranking")
    print("=" * 90)

    # ── Load E32 GLARE ranking ───────────────────────────────
    with open(E32_RANKED) as f:
        e32_data = json.load(f)
    e32_ranked = e32_data['ranked']
    n_pool = len(e32_ranked)
    print(f"\nE32 GLARE ranking: {n_pool} molecules (checkpoint: {e32_data['checkpoint']})")

    # Build rank map by canonical SMILES
    e32_rank_map = {}
    for i, r in enumerate(e32_ranked):
        c = norm(r['smiles'])
        e32_rank_map[c] = {
            'glare_rank': i + 1,
            'glare_score': r['glare_select_prob'],
            'glare_uncertainty': r.get('glare_uncertainty', 0),
        }

    # ── Load E33 GLARE ranking (bonus) ───────────────────────
    e33_rank_map = {}
    if E33_RANKED.exists():
        with open(E33_RANKED) as f:
            e33_data = json.load(f)
        e33_ranked = e33_data['ranked']
        for i, r in enumerate(e33_ranked):
            c = norm(r['smiles'])
            e33_rank_map[c] = {
                'glare_rank': i + 1,
                'glare_score': r.get('glare_select_prob', 0),
            }
        print(f"E33 GLARE ranking: {len(e33_ranked)} molecules (bonus)")

    # ── Load pool CSV ────────────────────────────────────────
    pool_df = pd.read_csv(POOL_CSV)
    print(f"Pool CSV: {len(pool_df)} rows")

    # Build ID lookup for MolFactory molecules
    pool_by_id = {}
    for i, row in pool_df.iterrows():
        mf_id = str(row['ID'])
        pool_by_id[mf_id] = {
            'idx': i,
            'smiles': row['smiles'],
            'canon': norm(row['smiles']),
            'CarsiScore': float(row['CarsiScore']),
            'RTMScore': float(row['RTMScore']),
            'similarity': float(row['similarity']),
            'MW': float(row['MW']),
            'TPSA': float(row['TPSA']),
            'LogP': float(row['LogP']),
        }

    # ── Match 13 molecules ───────────────────────────────────
    results = []
    for wetlab_id, mf_id, tanimoto, is_exact in WETLAB_MAP:
        mf = pool_by_id.get(mf_id)
        if not mf:
            print(f"  ⚠️ MolFactory_{mf_id} not found in pool!")
            continue

        e32 = e32_rank_map.get(mf['canon'], {})
        e33 = e33_rank_map.get(mf['canon'], {})

        # CarsiScore rank: lower (more negative) = better
        carsi_rank = mf['idx'] + 1  # CSV is sorted by CarsiScore

        entry = {
            'wetlab_id': wetlab_id,
            'molfactory_id': f'MolFactory_{mf_id}',
            'tanimoto': tanimoto,
            'is_exact_match': is_exact,
            'canonical_smiles': mf['canon'],
            'CarsiScore': mf['CarsiScore'],
            'carsi_rank': carsi_rank,
            'carsi_pct': round(100 * carsi_rank / n_pool, 2),
            'RTMScore': mf['RTMScore'],
            'MW': mf['MW'],
            'TPSA': mf['TPSA'],
            'LogP': mf['LogP'],
            'glare_e32_rank': e32.get('glare_rank'),
            'glare_e32_score': round(e32.get('glare_score', 0), 6) if e32 else None,
            'glare_e32_pct': round(100 * e32.get('glare_rank', n_pool) / n_pool, 2) if e32 else None,
            'glare_e33_rank': e33.get('glare_rank'),
            'glare_e33_score': round(e33.get('glare_score', 0), 6) if e33 else None,
            'glare_e33_pct': round(100 * e33.get('glare_rank', n_pool) / n_pool, 2) if e33 else None,
        }
        results.append(entry)

    n_found = len(results)
    print(f"\nMatched: {n_found}/13")

    # ── Stats ────────────────────────────────────────────────
    e32_ranks = [r['glare_e32_rank'] for r in results if r['glare_e32_rank']]
    e33_ranks = [r['glare_e33_rank'] for r in results if r['glare_e33_rank']]
    carsi_ranks = [r['carsi_rank'] for r in results]

    print(f"\n{'='*90}")
    print(f"  13 Similar Molecules — Ranking Summary (n_pool={n_pool})")
    print(f"{'='*90}")

    print(f"\n  {'Method':>20s} {'Mean Rank':>12s} {'Median':>8s} {'Best':>8s} {'Worst':>8s} {'Top 10%':>8s} {'Top 25%':>8s} {'Top 50%':>8s}")
    print(f"  {'─'*80}")

    for label, ranks in [('CarsiScore', carsi_ranks), ('GLARE E32', e32_ranks), ('GLARE E33', e33_ranks)]:
        if not ranks:
            continue
        arr = np.array(ranks)
        print(f"  {label:>20s} {np.mean(arr):>10.1f}  {np.median(arr):>8.1f}  "
              f"{int(np.min(arr)):>8d}  {int(np.max(arr)):>8d}  "
              f"{sum(arr <= n_pool*0.10):>8d}  {sum(arr <= n_pool*0.25):>8d}  {sum(arr <= n_pool*0.50):>8d}")

    # ── Per-molecule table ───────────────────────────────────
    print(f"\n{'─'*90}")
    print(f"  Per-Molecule Detail")
    print(f"{'─'*90}")
    print(f"  {'WetLab':>10s} {'MF_ID':>16s} {'Tanimoto':>8s} {'Exact':>5s} "
          f"{'Carsi':>7s} {'C_%':>6s} {'E32':>7s} {'E32%':>6s} {'E33':>7s} {'E33%':>6s} "
          f"{'CarsiScore':>10s} {'RTM':>6s} {'MW':>6s}")
    print(f"  {'─'*90}")

    for r in results:
        exact = '✓' if r['is_exact_match'] else ''
        print(f"  {r['wetlab_id']:>10s} {r['molfactory_id']:>16s} {r['tanimoto']:>8.3f} {exact:>5s} "
              f"{r['carsi_rank']:>7d} {r['carsi_pct']:>5.1f}% "
              f"{str(r['glare_e32_rank']):>7s} {str(r['glare_e32_pct']):>5s}% "
              f"{str(r['glare_e33_rank']):>7s} {str(r['glare_e33_pct']):>5s}% "
              f"{r['CarsiScore']:>10.2f} {r['RTMScore']:>6.1f} {r['MW']:>6.0f}")

    # ── 3 exact match subset ─────────────────────────────────
    exact_matches = [r for r in results if r['is_exact_match']]
    if exact_matches:
        em_e32 = [r['glare_e32_rank'] for r in exact_matches if r['glare_e32_rank']]
        em_carsi = [r['carsi_rank'] for r in exact_matches]
        print(f"\n  ── 3 Exact Matches (Tanimoto=1.0) ──")
        print(f"  GLARE E32 mean rank: {np.mean(em_e32):.1f} (top {100*np.mean(em_e32)/n_pool:.2f}%)")
        print(f"  CarsiScore mean rank: {np.mean(em_carsi):.1f} (top {100*np.mean(em_carsi)/n_pool:.2f}%)")

    # ── Save JSON ────────────────────────────────────────────
    report = {
        'pool_size': n_pool,
        'e32_checkpoint': e32_data['checkpoint'],
        'n_matched': n_found,
        'results': results,
        'stats': {
            'e32_glare_mean_rank': float(np.mean(e32_ranks)) if e32_ranks else None,
            'e32_glare_median_rank': float(np.median(e32_ranks)) if e32_ranks else None,
            'e32_glare_best_rank': int(np.min(e32_ranks)) if e32_ranks else None,
            'e32_glare_worst_rank': int(np.max(e32_ranks)) if e32_ranks else None,
            'e32_glare_top10pct': int(sum(np.array(e32_ranks) <= n_pool*0.10)) if e32_ranks else 0,
            'e32_glare_top25pct': int(sum(np.array(e32_ranks) <= n_pool*0.25)) if e32_ranks else 0,
            'e32_glare_top50pct': int(sum(np.array(e32_ranks) <= n_pool*0.50)) if e32_ranks else 0,
            'carsi_mean_rank': float(np.mean(carsi_ranks)),
            'carsi_median_rank': float(np.median(carsi_ranks)),
            'carsi_top10pct': int(sum(np.array(carsi_ranks) <= n_pool*0.10)),
            'carsi_top25pct': int(sum(np.array(carsi_ranks) <= n_pool*0.25)),
            'carsi_top50pct': int(sum(np.array(carsi_ranks) <= n_pool*0.50)),
        },
    }
    out_json = OUT_DIR / 'wetlab_13_similar_ranking.json'
    with open(out_json, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ JSON saved: {out_json}")

    # ── Save CSV ─────────────────────────────────────────────
    csv_rows = []
    for r in results:
        csv_rows.append({
            'wetlab_id': r['wetlab_id'],
            'molfactory_id': r['molfactory_id'],
            'tanimoto': r['tanimoto'],
            'is_exact_match': r['is_exact_match'],
            'canonical_smiles': r['canonical_smiles'],
            'CarsiScore': r['CarsiScore'],
            'carsi_rank': r['carsi_rank'],
            'carsi_pct': r['carsi_pct'],
            'RTMScore': r['RTMScore'],
            'MW': r['MW'],
            'TPSA': r['TPSA'],
            'LogP': r['LogP'],
            'glare_e32_rank': r['glare_e32_rank'],
            'glare_e32_score': r['glare_e32_score'],
            'glare_e32_pct': r['glare_e32_pct'],
            'glare_e33_rank': r['glare_e33_rank'],
            'glare_e33_score': r['glare_e33_score'],
            'glare_e33_pct': r['glare_e33_pct'],
        })
    out_csv = OUT_DIR / 'wetlab_13_similar_ranking.csv'
    pd.DataFrame(csv_rows).to_csv(out_csv, index=False)
    print(f"✅ CSV saved: {out_csv}")

    # ── Visualization ────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  Generating Publication-Quality Figures")
    print(f"{'='*90}")

    plot_rankings(results, n_pool, OUT_DIR)
    plot_enrichment(results, n_pool, OUT_DIR)
    plot_scatter(results, n_pool, OUT_DIR)

    print(f"\n✅ All outputs in: {OUT_DIR}")
    return results


def plot_rankings(results, n_pool, out_dir):
    """Bar chart: rank for each molecule, GLARE vs CarsiScore."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    # Paper style
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.size': 9,
        'axes.titlesize': 11,
        'axes.labelsize': 10,
        'xtick.labelsize': 8,
        'ytick.labelsize': 8,
        'legend.fontsize': 8,
        'figure.dpi': 150,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'axes.spines.top': False,
        'axes.spines.right': False,
    })

    labels = [f"{r['wetlab_id']}\n→{r['molfactory_id']}" for r in results]
    e32_ranks = [r['glare_e32_rank'] for r in results]
    e33_ranks = [r['glare_e33_rank'] for r in results]
    carsi_ranks = [r['carsi_rank'] for r in results]
    exact_flags = [r['is_exact_match'] for r in results]

    x = np.arange(len(results))
    width = 0.25

    fig, ax = plt.subplots(figsize=(14, 6))

    # Color palette (Nature-friendly)
    c_e32 = '#2166AC'   # blue
    c_e33 = '#92C5DE'   # light blue
    c_carsi = '#B2182B'  # red

    bars1 = ax.bar(x - width, carsi_ranks, width, color=c_carsi, alpha=0.85, label='CarsiScore', zorder=3)
    bars2 = ax.bar(x, e32_ranks, width, color=c_e32, alpha=0.85, label='GLARE E32', zorder=3)
    bars3 = ax.bar(x + width, e33_ranks, width, color=c_e33, alpha=0.85, label='GLARE E33', zorder=3)

    # Mark exact matches
    for i, is_exact in enumerate(exact_flags):
        if is_exact:
            ax.annotate('★', (x[i], max(e32_ranks[i], carsi_ranks[i], e33_ranks[i] or 0)),
                       ha='center', va='bottom', fontsize=14, color='#D4A017', fontweight='bold')

    # Mean lines
    mean_carsi = np.mean(carsi_ranks)
    mean_e32 = np.mean(e32_ranks)
    mean_e33 = np.mean([r for r in e33_ranks if r]) if any(e33_ranks) else 0
    ax.axhline(mean_carsi, color=c_carsi, linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(mean_e32, color=c_e32, linestyle='--', alpha=0.5, linewidth=1)
    ax.axhline(mean_e33, color=c_e33, linestyle='--', alpha=0.5, linewidth=1)

    # Top 10% line
    ax.axhline(n_pool * 0.10, color='gray', linestyle=':', alpha=0.4, linewidth=0.8)
    ax.text(len(results) - 0.5, n_pool * 0.10 + 150, 'Top 10%', fontsize=7, color='gray', ha='right')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel('Rank (lower = better)')
    ax.set_title(f'13 Wet-Lab → MolFactory Similar Molecules: Ranking Comparison\n'
                 f'Pool N={n_pool} | E32 cycle_7 | ★ = exact match')
    ax.legend(frameon=False)
    ax.set_ylim(0, n_pool * 1.05)
    ax.invert_yaxis()  # lower rank = better → top

    # Add mean annotations
    ax.text(0.02, 0.98, f'Mean Carsi: {mean_carsi:.0f}\nMean E32: {mean_e32:.0f}\nMean E33: {mean_e33:.0f}',
            transform=ax.transAxes, fontsize=7, va='top',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_rankings.png', dpi=300)
    fig.savefig(out_dir / 'fig_rankings.svg')
    plt.close()
    print("  ✅ fig_rankings.png / .svg")


def plot_enrichment(results, n_pool, out_dir):
    """Cumulative enrichment plot (like ROC but for rank percentile)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.size': 9,
        'axes.titlesize': 11,
        'axes.labelsize': 10,
        'figure.dpi': 150,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'axes.spines.top': False,
        'axes.spines.right': False,
    })

    fig, ax = plt.subplots(figsize=(7, 6))

    colors = {
        'CarsiScore': '#B2182B',
        'GLARE E32': '#2166AC',
        'GLARE E33': '#92C5DE',
    }

    for label, col_key in [('CarsiScore', 'carsi_rank'), ('GLARE E32', 'glare_e32_rank'), ('GLARE E33', 'glare_e33_rank')]:
        ranks = sorted([r[col_key] for r in results if r[col_key] is not None])
        if not ranks:
            continue
        x_vals = np.linspace(0, 100, 500)
        y_vals = []
        for xp in x_vals:
            cutoff = n_pool * xp / 100
            y_vals.append(sum(1 for r in ranks if r <= cutoff) / len(ranks) * 100)
        ax.plot(x_vals, y_vals, color=colors[label], linewidth=2, label=label)

    # Random baseline
    ax.plot([0, 100], [0, 100], 'k--', alpha=0.3, linewidth=1, label='Random')

    ax.set_xlabel('Top % of Ranked Pool')
    ax.set_ylabel('Cumulative % of 13 Molecules Found')
    ax.set_title('Enrichment Curve: 13 Wet-Lab → MolFactory Similar Molecules')
    ax.legend(frameon=False, loc='lower right')
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_enrichment.png', dpi=300)
    fig.savefig(out_dir / 'fig_enrichment.svg')
    plt.close()
    print("  ✅ fig_enrichment.png / .svg")


def plot_scatter(results, n_pool, out_dir):
    """Scatter: GLARE E32 rank vs CarsiScore rank, color by Tanimoto."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.size': 9,
        'axes.titlesize': 11,
        'axes.labelsize': 10,
        'figure.dpi': 150,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'axes.spines.top': False,
        'axes.spines.right': False,
    })

    fig, ax = plt.subplots(figsize=(7, 7))

    carsi = [r['carsi_rank'] for r in results]
    e32 = [r['glare_e32_rank'] for r in results]
    tanimoto = [r['tanimoto'] for r in results]
    exact = [r['is_exact_match'] for r in results]
    labels = [r['wetlab_id'] for r in results]

    # Color by tanimoto
    scatter = ax.scatter(carsi, e32, c=tanimoto, cmap='YlOrRd', s=80,
                         edgecolors='black', linewidth=0.5, zorder=5, vmin=0.5, vmax=1.0)

    # Mark exact matches with star
    for i, is_ex in enumerate(exact):
        if is_ex:
            ax.scatter([carsi[i]], [e32[i]], marker='*', s=250, c='#D4A017',
                      edgecolors='black', linewidth=0.5, zorder=6)

    # Labels
    for i, label in enumerate(labels):
        offset_y = 300 if i % 2 == 0 else -400
        ax.annotate(label, (carsi[i], e32[i]), fontsize=6, alpha=0.8,
                   xytext=(5, offset_y), textcoords='offset points',
                   arrowprops=dict(arrowstyle='->', color='gray', alpha=0.3, lw=0.5))

    # Diagonal
    max_val = max(max(carsi), max(e32))
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.2, linewidth=1)

    # Top 10% quadrant
    top10 = n_pool * 0.10
    ax.axhline(top10, color='green', linestyle=':', alpha=0.3, linewidth=0.8)
    ax.axvline(top10, color='green', linestyle=':', alpha=0.3, linewidth=0.8)
    ax.fill_between([0, top10], 0, top10, alpha=0.05, color='green')
    ax.text(top10/2, top10/2, 'Both Top 10%', fontsize=7, ha='center', va='center', alpha=0.5)

    ax.set_xlabel('CarsiScore Rank (lower = better)')
    ax.set_ylabel('GLARE E32 Rank (lower = better)')
    ax.set_title(f'GLARE E32 vs CarsiScore: 13 Wet-Lab Similar Molecules\n'
                 f'Pool N={n_pool} | Colored by Tanimoto Similarity')
    cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
    cbar.set_label('Tanimoto Similarity', fontsize=8)

    # Legend for exact matches
    legend_elements = [Line2D([0], [0], marker='*', color='w', markerfacecolor='#D4A017',
                              markersize=15, label='Exact Match (T=1.0)')]
    ax.legend(handles=legend_elements, frameon=False, loc='lower right')

    ax.set_xlim(0, max_val * 1.05)
    ax.set_ylim(0, max_val * 1.05)
    ax.invert_xaxis()
    ax.invert_yaxis()

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_scatter.png', dpi=300)
    fig.savefig(out_dir / 'fig_scatter.svg')
    plt.close()
    print("  ✅ fig_scatter.png / .svg")


if __name__ == '__main__':
    main()