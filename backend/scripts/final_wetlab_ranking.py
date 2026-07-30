#!/usr/bin/env python3
"""Final ranking analysis: wet-lab 13 + MolFactory 28 target molecules in extended pool."""
import json
import numpy as np
from pathlib import Path
from rdkit import Chem

OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706')

# Load wetlab metadata
df13_data = {
    '0228271': {'pDC50': 1.37, 'is_strong': False},
    '0228279': {'pDC50': 6.37, 'is_strong': False},
    '0228283': {'pDC50': 6.25, 'is_strong': False},
    '0228303': {'pDC50': 5.22, 'is_strong': False},
    '0228366': {'pDC50': 5.83, 'is_strong': False},
    '0228390': {'pDC50': 6.37, 'is_strong': True},
    '0228405': {'pDC50': 5.66, 'is_strong': False},
    '0228414': {'pDC50': 6.72, 'is_strong': True},
    '0228416': {'pDC50': 5.28, 'is_strong': False},
    '0228417': {'pDC50': 5.57, 'is_strong': False},
    'LXC-102': {'pDC50': 6.85, 'is_strong': False},
    'LXC-104': {'pDC50': 6.37, 'is_strong': False},  # same canonical as 0228279
    'LXC-106': {'pDC50': 6.96, 'is_strong': True},
}

# Canonical SMILES for wetlab molecules (from previous run)
wetlab_canon = {
    '0228271': 'O=C1CCN(c2cccc(-c3ccc4c(c3)CCCN4)c2Cl)C(=O)N1',
    '0228279': 'Cc1c(-c2ccc(-c3cccn(CC(F)(F)F)c3=O)cc2)cccc1N1CCC(=O)NC1=O',
    '0228283': 'Cc1c(-c2ccc(C(=O)N3CCCCC3)cc2)cccc1N1CCC(=O)NC1=O',
    '0228303': 'CC1(C)CC(=O)Nc2ccc(-c3cccc(N4CCC(=O)NC4=O)c3Cl)cc21',
    '0228366': 'Nc1ccc(-c2cccc(N3CCC(=O)NC3=O)c2Cl)cc1F',
    '0228390': 'O=C1CCN(c2cccc(-c3ccc(OCc4ncccn4)cc3)c2Cl)C(=O)N1',
    '0228405': 'N#CC1=Cc2cc(-c3cccc(N4CCC(=O)NC4=O)c3Cl)ccc2OC1',
    '0228414': 'O=C1CCN(c2cccc(-c3ccc4c(c3)CCC(=O)N4)c2Cl)C(=O)N1',
    '0228416': 'O=C1CCN(c2cccc(-c3ccc4c(c3)CCC4=O)c2Cl)C(=O)N1',
    '0228417': 'O=C1CCN(c2cccc(-c3ccc4occc4c3)c2Cl)C(=O)N1',
    'LXC-102': 'Cc1c(-c2ccc(-n3ccccc3=O)cc2)cccc1N1CCC(=O)NC1=O',
    'LXC-104': 'Cc1c(-c2ccc(-c3cccn(CC(F)(F)F)c3=O)cc2)cccc1N1CCC(=O)NC1=O',
    'LXC-106': 'O=C1CCN(c2cccc(-c3ccc(C(=O)N4CCCCC4)cc3)c2Cl)C(=O)N1',
}

# Load extended ranking
with open(OUTPUT_DIR / 'ranked_extended_e32_grpo_sup.json') as f:
    ranked_data = json.load(f)
ranked = ranked_data['ranked']
n_pool = len(ranked)

# Also load matched targets for the 28
with open(OUTPUT_DIR / 'matched_targets.json') as f:
    matched_28 = json.load(f)

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

rank_map = {}
for r in ranked:
    rank_map[norm(r['smiles'])] = {'rank': r['glare_rank'], 'score': r['glare_select_prob']}

# Find wetlab ranks
print(f'{"="*90}')
print(f'  Wet-Lab 13 Molecules + MolFactory Targets in Extended Pool (n={n_pool})')
print(f'  Checkpoint: E32 e32_grpo_sup cycle_7 (Combined=0.8531)')
print(f'{"="*90}')

wetlab_results = []
for sid in df13_data:
    canon = wetlab_canon.get(sid)
    if not canon:
        continue
    entry = rank_map.get(norm(canon)) or rank_map.get(canon)
    if entry:
        pct = round(100 * entry['rank'] / n_pool, 2)
        wetlab_results.append({**df13_data[sid], 'sdf_id': sid, 'rank': entry['rank'],
                              'score': entry['score'], 'percentile': pct})

# Sort by rank
wetlab_results.sort(key=lambda x: x['rank'])

print(f'\n{"──":>3s} {"Wet-Lab 13":>35s} {"──":>3s} {"──":>3s} {"MolFactory 28 Targets":>35s} {"──"}')
print(f'{"Rank":>5s} {"%ile":>6s} {"ID":>10s} {"pDC50":>6s} {"★":>3s} | {"Rank":>5s} {"%ile":>6s} {"Image":>35s}')
print('-' * 90)

# Interleave: show all 13 wetlab + top/bottom 28
for i in range(max(len(wetlab_results), len(matched_28))):
    w_str = ''
    m_str = ''
    if i < len(wetlab_results):
        w = wetlab_results[i]
        star = '⭐' if w['is_strong'] else '  '
        w_str = f'{w["rank"]:>5d} {w["percentile"]:>5.2f}% {w["sdf_id"]:>10s} {w["pDC50"]:>6.2f} {star}'
    if i < len(matched_28):
        m = matched_28[i]
        m_rank = rank_map.get(norm(m['smiles_canonical']))
        if m_rank:
            m_pct = round(100 * m_rank['rank'] / n_pool, 2)
            m_str = f'{m_rank["rank"]:>5d} {m_pct:>5.2f}% {m["image"][:35]}'
        else:
            m_str = f'{"?":>5s} {"?":>5s} {m["image"][:35]}'
    print(f'{w_str:35s} | {m_str}')

# Stats
print(f'\n{"="*90}')
print(f'  Summary Statistics')
print(f'{"="*90}')

# Wetlab stats
w_ranks = [w['rank'] for w in wetlab_results]
w_scores = [w['score'] for w in wetlab_results]
w_pcts = [w['percentile'] for w in wetlab_results]
w_strong = [w for w in wetlab_results if w['is_strong']]
w_weak = [w for w in wetlab_results if not w['is_strong']]

print(f'\n--- Wet-Lab 13 (n={len(wetlab_results)}) ---')
print(f'  Mean rank: {np.mean(w_ranks):.1f} / {n_pool} (top {np.mean(w_pcts):.2f}%)')
print(f'  Median rank: {np.median(w_ranks):.1f}')
print(f'  Best: #{min(w_ranks)} (top {min(w_pcts):.2f}%)')
print(f'  Worst: #{max(w_ranks)} (top {max(w_pcts):.2f}%)')
print(f'  Mean score: {np.mean(w_scores):.4f}')

if w_strong:
    sr = [w['rank'] for w in w_strong]
    sp = [w['percentile'] for w in w_strong]
    print(f'\n  --- 3 Strong Actives ---')
    print(f'  Mean rank: {np.mean(sr):.1f} (top {np.mean(sp):.2f}%)')
    for w in w_strong:
        print(f'    #{w["rank"]:>5d} (top {w["percentile"]:.2f}%)  {w["sdf_id"]} pDC50={w["pDC50"]:.2f}')

if w_weak:
    wr = [w['rank'] for w in w_weak]
    wp = [w['percentile'] for w in w_weak]
    print(f'\n  --- 9 Weak/Inactive ---')
    print(f'  Mean rank: {np.mean(wr):.1f} (top {np.mean(wp):.2f}%)')

# Distribution
print(f'\n--- Wet-Lab 13 Quantile Distribution ---')
for cutoff, label in [(0.05, 'Top 5%'), (0.10, 'Top 10%'), (0.25, 'Top 25%'), (0.50, 'Top 50%')]:
    n = sum(1 for r in w_ranks if r <= n_pool * cutoff)
    print(f'  {label:>10s}: {n}/{len(w_ranks)} ({100*n/len(w_ranks):.1f}%)')

# MolFactory 28 stats
m_ranks_list = []
for m in matched_28:
    entry = rank_map.get(norm(m['smiles_canonical']))
    if entry:
        m_ranks_list.append(entry['rank'])

if m_ranks_list:
    m_pcts_list = [100*r/n_pool for r in m_ranks_list]
    print(f'\n--- MolFactory 28 Targets (n={len(m_ranks_list)}) ---')
    print(f'  Mean rank: {np.mean(m_ranks_list):.1f} (top {np.mean(m_pcts_list):.2f}%)')
    print(f'  Median rank: {np.median(m_ranks_list):.1f}')

print(f'\n✅ Done')
