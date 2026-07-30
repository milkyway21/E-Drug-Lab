#!/usr/bin/env python3
"""Compute target molecule rankings from multiple GLARE checkpoints + comparison."""
import json
import numpy as np
from pathlib import Path
from rdkit import Chem

OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706')

with open(OUTPUT_DIR / 'matched_targets.json') as f:
    matched = json.load(f)

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def compute_ranks(ranked_file, ckpt_label):
    """Compute target ranks from a ranked JSON file."""
    with open(ranked_file) as f:
        data = json.load(f)
    ranked = data['ranked']
    n_pool = len(ranked)

    rank_map = {}
    for r in ranked:
        smi_norm = norm(r['smiles'])
        rank_map[smi_norm] = {
            'rank': r['glare_rank'],
            'score': r['glare_select_prob'],
        }

    results = []
    for t in matched:
        smi_canon = norm(t['smiles_canonical'])
        info = rank_map.get(smi_canon, rank_map.get(t['smiles_canonical']))
        key = f'rank_{ckpt_label}'
        if info:
            t[key] = info['rank']
            t[f'score_{ckpt_label}'] = info['score']
            t[f'pct_{ckpt_label}'] = round(100 * info['rank'] / n_pool, 2)
        else:
            t[key] = None
            t[f'score_{ckpt_label}'] = None
            t[f'pct_{ckpt_label}'] = None

    found = [t for t in matched if t.get(key) is not None]
    ranks = [t[key] for t in found]
    scores = [t[f'score_{ckpt_label}'] for t in found]
    pcts = [t[f'pct_{ckpt_label}'] for t in found]

    return {
        'label': ckpt_label,
        'n_pool': n_pool,
        'n_found': len(found),
        'mean_rank': float(np.mean(ranks)),
        'median_rank': float(np.median(ranks)),
        'best_rank': int(min(ranks)),
        'worst_rank': int(max(ranks)),
        'mean_pct': float(np.mean(pcts)),
        'median_pct': float(np.median(pcts)),
        'mean_score': float(np.mean(scores)),
        'median_score': float(np.median(scores)),
    }, matched

# Compute for both checkpoints
ckpts = [
    (OUTPUT_DIR / 'ranked_e32_grpo_sup.json', 'e32_grpo_sup'),
    (OUTPUT_DIR / 'ranked_e30_sup_5e4.json', 'e30_sup_5e4'),
]

all_stats = {}
for ckpt_file, label in ckpts:
    if ckpt_file.exists():
        stats, matched = compute_ranks(ckpt_file, label)
        all_stats[label] = stats
        print(f'\n{"="*80}')
        print(f'Checkpoint: {label}')
        print(f'{"="*80}')
        print(f'Pool: {stats["n_pool"]}, Found: {stats["n_found"]}')
        print(f'Mean rank: {stats["mean_rank"]:.1f} / {stats["n_pool"]}')
        print(f'Median rank: {stats["median_rank"]:.1f}')
        print(f'Best: #{stats["best_rank"]} (top {100*stats["best_rank"]/stats["n_pool"]:.2f}%)')
        print(f'Worst: #{stats["worst_rank"]} (top {100*stats["worst_rank"]/stats["n_pool"]:.2f}%)')
        print(f'Mean score: {stats["mean_score"]:.4f}')

# Comparison table
if len(all_stats) >= 2:
    print(f'\n{"="*80}')
    print(f'Comparison: Per-Molecule Ranks Across Checkpoints')
    print(f'{"="*80}')
    labels = list(all_stats.keys())
    print(f'{"Image":50s} {"pDC50":>7s} {"Sim":>7s}', end='')
    for lb in labels:
        print(f' {lb+"_rank":>14s} {lb+"_pct":>8s}', end='')
    print()
    print('-' * (70 + 24 * len(labels)))

    # Sort by e32 rank
    sorted_matched = sorted(
        [t for t in matched if t.get(f'rank_{labels[0]}') is not None],
        key=lambda t: t[f'rank_{labels[0]}']
    )
    for t in sorted_matched:
        pdc50_str = f'{t["pDC50"]:.2f}' if t['pDC50'] is not None else 'N/A'
        print(f'{t["image"]:50s} {pdc50_str:>7s} {t["img_similarity"]:>7.3f}', end='')
        for lb in labels:
            r = t.get(f'rank_{lb}', 'N/A')
            p = t.get(f'pct_{lb}', 'N/A')
            p_str = f'{p:.2f}%' if isinstance(p, (int, float)) else str(p)
            print(f' {str(r):>14s} {p_str:>8s}', end='')
        print()

# Save combined report
report = {
    'stats': all_stats,
    'results': matched,
}
with open(OUTPUT_DIR / 'target_rank_report_combined.json', 'w') as f:
    # Clean numpy types
    clean_results = []
    for t in matched:
        ct = {}
        for k, v in t.items():
            if isinstance(v, (np.floating,)): ct[k] = float(v)
            elif isinstance(v, (np.integer,)): ct[k] = int(v)
            else: ct[k] = v
        clean_results.append(ct)
    report['results'] = clean_results
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f'\nCombined report saved: {OUTPUT_DIR / "target_rank_report_combined.json"}')
