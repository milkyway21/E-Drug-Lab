#!/usr/bin/env python3
"""E33 result: rank 36 selected molecules with best E33 checkpoint on 10K MolFactory pool."""
import sys, os, json, time
import numpy as np
from pathlib import Path
from rdkit import Chem
import pandas as pd

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import query

# ── Config ──────────────────────────────────────────────────
E33_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709')
E32_RESULTS = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706')
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
SELECTED_CSV = '/data/ye/e-drug-lab/molfactory/selected_similar_molecules_name_smiles.csv'
CKPT_PATH = str(E33_DIR / 'e33_grpo_sup' / 'checkpoints' / 'cycle_6.pt')  # Best: ROC=0.8996, Combined=0.9413
POOL_SMILES = str(E32_RESULTS / 'pool_10k_smiles.json')

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def main():
    print("=" * 80)
    print("  E33 → 36 Selected Molecules GLARE Ranking on 10K MolFactory Pool")
    print("=" * 80)

    # Check for E33 checkpoint
    if not Path(CKPT_PATH).exists():
        # Try other cycles
        for c in range(7, -1, -1):
            alt = str(E33_DIR / 'e33_grpo_sup' / 'checkpoints' / f'cycle_{c}.pt')
            if Path(alt).exists():
                ckpt = alt
                print(f"Using checkpoint: cycle_{c}.pt")
                break
        else:
            print("❌ No E33 checkpoint found! Has training completed?")
            return
    else:
        ckpt = CKPT_PATH
        print(f"Using checkpoint: cycle_7.pt")

    # Load 10K pool
    print(f"\nLoading 10K pool...")
    if Path(POOL_SMILES).exists():
        with open(POOL_SMILES) as f:
            pool_smiles = json.load(f)
    else:
        df = pd.read_csv(POOL_CSV)
        pool_smiles = [norm(s) for s in df['smiles'].tolist()]
        pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))
    print(f"Pool: {len(pool_smiles)} molecules")

    # GLARE ranking
    print(f"\nRunning GLARE query (GPU 5, ensemble=3)...")
    t0 = time.time()
    result = query(ckpt, pool_smiles, ensemble_size=3)
    elapsed = time.time() - t0

    if not result.get('ok', False) and 'ranked' not in result:
        print(f"❌ Query failed: {result.get('error', str(result)[:300])}")
        return

    ranked = result.get('ranked', [])
    print(f"✅ Ranked {len(ranked)} molecules in {elapsed:.0f}s")

    # Build rank map
    rank_map = {}
    for r in ranked:
        smi_norm = norm(r['smiles'])
        rank_map[smi_norm] = {
            'rank': r['glare_rank'],
            'score': r['glare_select_prob'],
            'uncertainty': r.get('glare_uncertainty', 0),
        }

    # Load 36 selected molecules
    selected_df = pd.read_csv(SELECTED_CSV)
    print(f"\nSelected molecules: {len(selected_df)}")

    # Load pool CSV for CarsiScore data
    pool_df = pd.read_csv(POOL_CSV)
    carsi_map = {}
    for i, row in pool_df.iterrows():
        smi_norm = norm(row['smiles'])
        if smi_norm:
            carsi_map[smi_norm] = {
                'carsi_score': float(row['CarsiScore']),
                'carsi_rank': i + 1,  # CSV is sorted by CarsiScore
                'rtm_score': float(row.get('RTMScore', 0)),
            }

    # Match 36 molecules
    results = []
    n_pool = len(ranked)

    for _, row in selected_df.iterrows():
        name = row['??']
        smi = row['smiles']
        canon = norm(smi)

        glare_info = rank_map.get(canon)
        carsi_info = carsi_map.get(canon)

        entry = {
            'name': name,
            'canon': canon,
            'glare_rank': glare_info['rank'] if glare_info else None,
            'glare_score': round(glare_info['score'], 6) if glare_info else None,
            'glare_pct': round(100 * glare_info['rank'] / n_pool, 2) if glare_info else None,
            'carsi_rank': carsi_info['carsi_rank'] if carsi_info else None,
            'carsi_score': round(carsi_info['carsi_score'], 3) if carsi_info else None,
            'rtm_score': round(carsi_info['rtm_score'], 3) if carsi_info else None,
        }
        results.append(entry)

    # Stats
    glare_ranks = [r['glare_rank'] for r in results if r['glare_rank'] is not None]
    carsi_ranks = [r['carsi_rank'] for r in results if r['carsi_rank'] is not None]

    print(f"\n{'='*80}")
    print(f"  Results: E33 GLARE vs CarsiScore — 36 Selected Molecules")
    print(f"{'='*80}")

    glare_stats = {}
    if glare_ranks:
        glare_stats = {
            'mean_rank': float(np.mean(glare_ranks)),
            'median_rank': float(np.median(glare_ranks)),
            'best_rank': int(min(glare_ranks)),
            'worst_rank': int(max(glare_ranks)),
            'mean_pct': round(100 * np.mean(glare_ranks) / n_pool, 2),
            'top_10pct': sum(1 for r in glare_ranks if r <= n_pool * 0.10),
            'top_25pct': sum(1 for r in glare_ranks if r <= n_pool * 0.25),
            'top_50pct': sum(1 for r in glare_ranks if r <= n_pool * 0.50),
        }
        print(f"\n  GLARE (E33 e33_grpo_sup cycle_7):")
        print(f"    Mean: {glare_stats['mean_rank']:.1f} / {n_pool} (top {glare_stats['mean_pct']:.2f}%)")
        print(f"    Median: {glare_stats['median_rank']:.1f}")
        print(f"    Best: #{glare_stats['best_rank']}, Worst: #{glare_stats['worst_rank']}")
        print(f"    Top 10%: {glare_stats['top_10pct']}/36, Top 25%: {glare_stats['top_25pct']}/36, Top 50%: {glare_stats['top_50pct']}/36")

    carsi_stats = {}
    if carsi_ranks:
        carsi_stats = {
            'mean_rank': float(np.mean(carsi_ranks)),
            'median_rank': float(np.median(carsi_ranks)),
            'best_rank': int(min(carsi_ranks)),
            'worst_rank': int(max(carsi_ranks)),
            'mean_pct': round(100 * np.mean(carsi_ranks) / n_pool, 2),
            'top_10pct': sum(1 for r in carsi_ranks if r <= n_pool * 0.10),
            'top_25pct': sum(1 for r in carsi_ranks if r <= n_pool * 0.25),
            'top_50pct': sum(1 for r in carsi_ranks if r <= n_pool * 0.50),
        }
        print(f"\n  CarsiScore:")
        print(f"    Mean: {carsi_stats['mean_rank']:.1f} / {n_pool} (top {carsi_stats['mean_pct']:.2f}%)")
        print(f"    Median: {carsi_stats['median_rank']:.1f}")
        print(f"    Best: #{carsi_stats['best_rank']}, Worst: #{carsi_stats['worst_rank']}")
        print(f"    Top 10%: {carsi_stats['top_10pct']}/36, Top 25%: {carsi_stats['top_25pct']}/36, Top 50%: {carsi_stats['top_50pct']}/36")

    # Detailed table
    print(f"\n{'─'*80}")
    print(f"  Per-Molecule Detail (sorted by GLARE rank)")
    print(f"{'─'*80}")
    sorted_by_glare = sorted([r for r in results if r['glare_rank'] is not None], key=lambda x: x['glare_rank'])
    print(f"  {'Name':>22s} {'GLARE':>7s} {'G_%':>7s} {'Carsi':>7s} {'C_Score':>9s} {'RTM':>8s}")
    print(f"  {'─'*65}")
    for r in sorted_by_glare:
        print(f"  {r['name']:>22s} {r['glare_rank']:>7d} {r['glare_pct']:>6.2f}% "
              f"{str(r['carsi_rank']):>7s} {str(r['carsi_score']):>9s} {str(r['rtm_score']):>8s}")

    # Compare with E32 baseline
    e32_final = E32_RESULTS / 'selected_36_final_report.json'
    if e32_final.exists():
        with open(e32_final) as f:
            e32_data = json.load(f)
        e32_glare = e32_data.get('glare_stats', {})
        print(f"\n{'─'*80}")
        print(f"  Comparison with E32 Baseline (e32_grpo_sup cycle_7)")
        print(f"{'─'*80}")
        print(f"  {'Metric':>25s} {'E32':>10s} {'E33':>10s} {'Δ':>10s}")
        print(f"  {'─'*58}")
        for key, label in [('mean_rank', 'Mean GLARE Rank'), ('mean_pct', 'Mean %ile'),
                          ('top_10pct', 'Top 10%'), ('top_25pct', 'Top 25%'),
                          ('top_50pct', 'Top 50%')]:
            e32v = e32_glare.get(key, 'N/A')
            e33v = glare_stats.get(key, 'N/A')
            delta = ''
            if isinstance(e32v, (int, float)) and isinstance(e33v, (int, float)):
                delta = f'{e33v - e32v:+.1f}' if 'pct' in key else f'{e33v - e32v:+.1f}'
            print(f"  {label:>25s} {str(e32v):>10s} {str(e33v):>10s} {delta:>10s}")

    # Save
    report = {
        'pool_size': n_pool,
        'n_selected': len(results),
        'checkpoint': ckpt,
        'glare_stats': glare_stats,
        'carsi_stats': carsi_stats,
        'results': results,
    }
    out_file = E33_DIR / 'selected_36_ranking.json'
    with open(out_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report saved: {out_file}")


if __name__ == '__main__':
    main()
