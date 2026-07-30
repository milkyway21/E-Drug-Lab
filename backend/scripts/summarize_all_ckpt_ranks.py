#!/usr/bin/env python3
"""Compute average rank of 28 target molecules across all GLARE checkpoints."""
import json
import numpy as np
from pathlib import Path
from rdkit import Chem

OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706')

# Load matched targets
with open(OUTPUT_DIR / 'matched_targets.json') as f:
    matched = json.load(f)

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

target_canons = {norm(t['smiles_canonical']): t for t in matched}

# Load checkpoint info
with open(OUTPUT_DIR / 'top_checkpoints.json') as f:
    checkpoints = json.load(f)

# Process each checkpoint result
all_results = []  # per-checkpoint stats
molecule_ranks = {}  # per-molecule: {ckpt_label: rank}

for ck in checkpoints:
    label = f'{ck["exp"]}_{ck["config"]}'
    out_file = OUTPUT_DIR / f'ranked_{label}.json'
    if not out_file.exists():
        print(f'SKIP {label}: no result file')
        continue

    with open(out_file) as f:
        data = json.load(f)

    ranked = data.get('ranked', [])
    if not ranked:
        print(f'SKIP {label}: empty ranking')
        continue

    n_pool = len(ranked)

    # Build SMILES→rank map
    rank_map = {}
    for r in ranked:
        smi = norm(r.get('smiles', ''))
        if smi:
            rank_map[smi] = {'rank': r.get('glare_rank', 0), 'score': r.get('glare_select_prob', 0)}

    # Find ranks for our 28 targets
    found_ranks = []
    missing = []
    for canon, t in target_canons.items():
        entry = rank_map.get(canon)
        if entry:
            found_ranks.append(entry['rank'])
            # Track per-molecule
            img = t['image']
            if img not in molecule_ranks:
                molecule_ranks[img] = {}
            molecule_ranks[img][label] = {'rank': entry['rank'], 'score': entry['score']}
        else:
            missing.append(t['image'])

    if found_ranks:
        avg_rank = np.mean(found_ranks)
        med_rank = np.median(found_ranks)
        avg_pct = 100 * avg_rank / n_pool
        best_r = min(found_ranks)
        worst_r = max(found_ranks)
        top10 = sum(1 for r in found_ranks if r <= 0.10 * n_pool)
        top25 = sum(1 for r in found_ranks if r <= 0.25 * n_pool)
        top50 = sum(1 for r in found_ranks if r <= 0.50 * n_pool)

        all_results.append({
            'label': label,
            'exp': ck['exp'],
            'config': ck['config'],
            'r1_combined': ck['r1_combined'],
            'r1_roc': ck['r1_roc'],
            'ckpt_name': ck['ckpt_name'],
            'n_pool': n_pool,
            'n_found': len(found_ranks),
            'n_missing': len(missing),
            'avg_rank': round(float(avg_rank), 1),
            'med_rank': round(float(med_rank), 1),
            'avg_pct': round(float(avg_pct), 2),
            'best_rank': best_r,
            'worst_rank': worst_r,
            'top10': top10,
            'top25': top25,
            'top50': top50,
        })

# Sort by avg_rank (lower=better)
all_results.sort(key=lambda x: x['avg_rank'])

# Print results
print(f'\n{"="*100}')
print(f'  28 MolFactory Target Molecules — Average Rank Across All Checkpoints')
print(f'{"="*100}')
print(f'  {"Rank":>4s} {"Checkpoint":>32s} {"Comb":>7s} {"ROC":>7s} {"AvgRank":>9s} {"Avg%":>7s} {"MedRank":>8s} {"Best":>6s} {"Worst":>6s} {"Top10%":>8s} {"Top25%":>8s} {"Top50%":>8s} {"Miss":>5s}')
print(f'  {"-"*95}')

for i, r in enumerate(all_results):
    print(f'  {i+1:>4d} {r["label"]:>32s} {r["r1_combined"]:>7.4f} {r["r1_roc"]:>7.4f} '
          f'{r["avg_rank"]:>8.1f} {r["avg_pct"]:>6.2f}% {r["med_rank"]:>8.1f} '
          f'{r["best_rank"]:>6d} {r["worst_rank"]:>6d} '
          f'{r["top10"]:>4d}/28 {r["top25"]:>4d}/28 {r["top50"]:>4d}/28 '
          f'{r["n_missing"]:>5d}')

# Top 5 best
print(f'\n{"="*100}')
print(f'  🏆 TOP 5 Checkpoints for MolFactory Target Ranking')
print(f'{"="*100}')
for i, r in enumerate(all_results[:5]):
    print(f'\n  #{i+1}: {r["label"]} (R1_Combined={r["r1_combined"]:.4f}, R1_ROC={r["r1_roc"]:.4f})')
    print(f'      Avg rank: {r["avg_rank"]:.1f}/{r["n_pool"]} (top {r["avg_pct"]:.2f}%)')
    print(f'      Top 10%: {r["top10"]}/28, Top 25%: {r["top25"]}/28, Top 50%: {r["top50"]}/28')

# Per-molecule: show best checkpoint
print(f'\n{"="*100}')
print(f'  Best Checkpoint Per Molecule')
print(f'{"="*100}')
print(f'  {"Image":>45s} {"Best CKPT":>32s} {"Rank":>6s} {"%ile":>7s}')
print(f'  {"-"*95}')
for img in sorted(molecule_ranks.keys()):
    ckpt_data = molecule_ranks[img]
    # Find best (lowest rank)
    best_ckpt = min(ckpt_data.items(), key=lambda x: x[1]['rank'])
    best_label = best_ckpt[0]
    best_rank = best_ckpt[1]['rank']
    # Need pool size for percentile - use 2134 (standard)
    best_pct = round(100 * best_rank / 2134, 2)
    print(f'  {img:>45s} {best_label:>32s} {best_rank:>6d} {best_pct:>6.2f}%')

# Save results
summary = {
    'n_checkpoints': len(all_results),
    'n_targets': 28,
    'rankings': all_results,
    'per_molecule_best': {
        img: {'best_ckpt': min(cpts.items(), key=lambda x: x[1]['rank'])[0],
              'best_rank': min(cpts.items(), key=lambda x: x[1]['rank'])[1]['rank']}
        for img, cpts in molecule_ranks.items()
    },
    'molecule_all_ranks': {
        img: {ck: v['rank'] for ck, v in cpts.items()}
        for img, cpts in molecule_ranks.items()
    },
}

with open(OUTPUT_DIR / 'all_checkpoints_summary.json', 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(f'\n✅ Summary saved: {OUTPUT_DIR / "all_checkpoints_summary.json"}')
