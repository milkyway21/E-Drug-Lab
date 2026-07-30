#!/usr/bin/env python3
"""Compute target molecule rankings from GLARE screening results."""
import json
import numpy as np
from pathlib import Path
from rdkit import Chem

OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706')

# Load data
with open(OUTPUT_DIR / 'matched_targets.json') as f:
    matched = json.load(f)
with open(OUTPUT_DIR / 'ranked_e32_grpo_sup.json') as f:
    ranked_data = json.load(f)

ranked = ranked_data['ranked']
n_pool = len(ranked)

# Build SMILES -> rank map (normalize SMILES for robust matching)
def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

rank_map = {}
for r in ranked:
    smi_norm = norm(r['smiles'])
    rank_map[smi_norm] = {
        'rank': r['glare_rank'],
        'score': r['glare_select_prob'],
        'uncertainty': r.get('glare_uncertainty', None),
    }

# Compute target ranks
results = []
for t in matched:
    smi_canon = norm(t['smiles_canonical'])
    info = rank_map.get(smi_canon)
    if info is None:
        info = rank_map.get(t['smiles_canonical'])
    if info is None:
        print(f'  NOT FOUND: {t["image"]}')
        t['rank'] = None
        t['score'] = None
        t['percentile'] = None
    else:
        t['rank'] = info['rank']
        t['score'] = info['score']
        t['uncertainty'] = info['uncertainty']
        t['percentile'] = round(100 * info['rank'] / n_pool, 2)
    results.append(t)

found = [t for t in results if t.get('rank') is not None]
missing = [t for t in results if t.get('rank') is None]

print(f'\n{"="*80}')
print(f'MolFactory Target Molecule GLARE Ranking Report')
print(f'{"="*80}')
print(f'Checkpoint: E32 e32_grpo_sup cycle_7 (Combined=0.8531)')
print(f'Pool: {n_pool} molecules')
print(f'Targets: {len(results)} (from images), {len(found)} ranked')

if missing:
    print(f'WARNING: {len(missing)} not found in ranking')

if found:
    ranks = [t['rank'] for t in found]
    scores = [t['score'] for t in found]
    percentiles = [t['percentile'] for t in found]

    print(f'\n--- Ranking Statistics ---')
    print(f'Mean rank: {np.mean(ranks):.1f} / {n_pool}')
    print(f'Median rank: {np.median(ranks):.1f}')
    print(f'Best rank: #{min(ranks)} (top {min(percentiles):.2f}%)')
    print(f'Worst rank: #{max(ranks)} (top {max(percentiles):.2f}%)')
    print(f'Mean percentile: top {np.mean(percentiles):.2f}%')
    print(f'Median percentile: top {np.median(percentiles):.2f}%')
    print(f'Mean GLARE score: {np.mean(scores):.4f}')
    print(f'Median GLARE score: {np.median(scores):.4f}')

    # Distribution
    top5 = sum(1 for r in ranks if r <= n_pool * 0.05)
    top10 = sum(1 for r in ranks if r <= n_pool * 0.10)
    top25 = sum(1 for r in ranks if r <= n_pool * 0.25)
    top50 = sum(1 for r in ranks if r <= n_pool * 0.50)
    print(f'\n--- Quantile Distribution ---')
    print(f'Top 5%:   {top5}/{len(found)} ({100*top5/len(found):.1f}%)')
    print(f'Top 10%:  {top10}/{len(found)} ({100*top10/len(found):.1f}%)')
    print(f'Top 25%:  {top25}/{len(found)} ({100*top25/len(found):.1f}%)')
    print(f'Top 50%:  {top50}/{len(found)} ({100*top50/len(found):.1f}%)')

    # Detailed table
    print(f'\n--- Per-Molecule Details (sorted by GLARE rank) ---')
    print(f'{"Rank":>5s} {"%ile":>7s} {"Score":>7s} {"pDC50":>7s} {"Sim":>7s}  Image')
    print('-' * 70)
    sorted_found = sorted(found, key=lambda t: t['rank'])
    for t in sorted_found:
        pdc50_str = f'{t["pDC50"]:.2f}' if t['pDC50'] is not None else 'N/A'
        print(f'{t["rank"]:>5d} {t["percentile"]:>6.2f}% {t["score"]:>7.4f} {pdc50_str:>7s} {t["img_similarity"]:>7.3f}  {t["image"]}')

# Save report
report_path = OUTPUT_DIR / 'target_rank_report_e32_grpo_sup.json'
with open(report_path, 'w') as f:
    json.dump({
        'checkpoint': 'e32_grpo_sup_cycle7',
        'pool_size': n_pool,
        'n_targets': len(results),
        'n_found': len(found),
        'stats': {
            'mean_rank': float(np.mean(ranks)),
            'median_rank': float(np.median(ranks)),
            'best_rank': int(min(ranks)),
            'worst_rank': int(max(ranks)),
            'mean_percentile': float(np.mean(percentiles)),
            'median_percentile': float(np.median(percentiles)),
            'mean_score': float(np.mean(scores)),
            'median_score': float(np.median(scores)),
        } if found else {},
        'results': sorted_found if found else [],
    }, f, indent=2, ensure_ascii=False)

print(f'\nReport saved: {report_path}')
