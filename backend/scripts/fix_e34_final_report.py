#!/usr/bin/env python3
"""Fix: Generate final JSON files from existing E34 summary.json + checkpoints."""
import sys, os, json
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import query

OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403')
CKPT_DIR = OUTPUT_DIR / 'e34_grpo_sup' / 'checkpoints'
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
ENSEMBLE = 3

WETLAB_MAP = [
    ('0228271', '200',   0.632),
    ('0228279', '4984',  0.554),
    ('0228283', '8529',  0.581),
    ('0228303', '1677',  1.000),
    ('0228366', '130',   1.000),
    ('0228390', '4913',  0.764),
    ('0228405', '246',   0.650),
    ('0228414', '1170',  1.000),
    ('0228416', '711',   0.614),
    ('0228417', '170',   0.621),
    ('LXC-102', '2648',  0.621),
    ('LXC-104', '4984',  0.554),
    ('LXC-106', '3311',  0.617),
]

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def main():
    # Load existing summary
    with open(OUTPUT_DIR / 'e34_grpo_sup' / 'summary.json') as f:
        summary = json.load(f)

    # Load MolFactory pool
    mf_pool_df = pd.read_csv(POOL_CSV)
    mf_id_to_canon = {}
    for i, row in mf_pool_df.iterrows():
        mf_id = str(row['ID'])
        mf_id_to_canon[mf_id] = norm(row['smiles'])

    pool_smiles = [norm(s) for s in mf_pool_df['smiles'].tolist()]
    pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))

    # Find best cycle from summary
    best_cycle = None
    best_mean_rank = float('inf')
    cycle_13mol_log = []

    for c in summary['cycles']:
        cycle = c['cycle']
        ckpt_path = str(CKPT_DIR / f'cycle_{cycle}.pt')

        if not Path(ckpt_path).exists():
            print(f"  ⚠️ cycle_{cycle}.pt not found, skipping")
            continue

        print(f"Querying cycle_{cycle} on MolFactory pool...")
        qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
        if not qr.get('ok', False) and 'ranked' not in qr:
            print(f"  ❌ Query failed for cycle_{cycle}")
            continue

        ranked = qr.get('ranked', [])
        n_pool = len(ranked)

        rank_map = {}
        for r in ranked:
            rank_map[norm(r['smiles'])] = {
                'rank': int(r['glare_rank']),
                'score': float(r['glare_select_prob']),
            }

        results = []
        for wetlab_id, mf_id, tanimoto in WETLAB_MAP:
            canon = mf_id_to_canon.get(mf_id)
            if not canon:
                continue
            entry = rank_map.get(canon)
            if entry:
                carsi_idx = mf_pool_df[mf_pool_df['ID'].astype(str) == mf_id].index
                carsi_rank = int(carsi_idx[0] + 1) if len(carsi_idx) > 0 else None
                results.append({
                    'wetlab_id': wetlab_id,
                    'molfactory_id': f'MolFactory_{mf_id}',
                    'tanimoto': tanimoto,
                    'glare_rank': entry['rank'],
                    'glare_score': round(entry['score'], 6),
                    'glare_pct': round(100 * entry['rank'] / n_pool, 2),
                    'carsi_rank': carsi_rank,
                })

        if not results:
            print(f"  ⚠️ No matches for cycle_{cycle}")
            continue

        ranks = [r['glare_rank'] for r in results]
        entry = {
            'cycle': int(cycle),
            'n_pool': int(n_pool),
            'n_matched': int(len(results)),
            'mean_rank': float(np.mean(ranks)),
            'median_rank': float(np.median(ranks)),
            'best_rank': int(np.min(ranks)),
            'worst_rank': int(np.max(ranks)),
            'mean_pct': round(100 * np.mean(ranks) / n_pool, 2),
            'top_10pct': int(sum(1 for r in ranks if r <= n_pool * 0.10)),
            'top_25pct': int(sum(1 for r in ranks if r <= n_pool * 0.25)),
            'top_50pct': int(sum(1 for r in ranks if r <= n_pool * 0.50)),
            'results': results,
        }
        cycle_13mol_log.append(entry)
        print(f"  cycle_{cycle}: mean_rank={entry['mean_rank']:.1f} (top {entry['mean_pct']:.2f}%), "
              f"top10%={entry['top_10pct']}, top25%={entry['top_25pct']}, top50%={entry['top_50pct']}")

        if entry['mean_rank'] < best_mean_rank:
            best_mean_rank = entry['mean_rank']
            best_cycle = entry

    # Save cycle_13mol_ranking.json
    with open(OUTPUT_DIR / 'e34_grpo_sup' / 'cycle_13mol_ranking.json', 'w') as f:
        json.dump(cycle_13mol_log, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved cycle_13mol_ranking.json ({len(cycle_13mol_log)} cycles)")

    # Save best ranking report
    if best_cycle:
        best_report = {
            'pool_size': best_cycle['n_pool'],
            'best_cycle': best_cycle['cycle'],
            'checkpoint': str(CKPT_DIR / f'cycle_{best_cycle["cycle"]}.pt'),
            'mean_rank': best_cycle['mean_rank'],
            'median_rank': best_cycle['median_rank'],
            'best_rank': best_cycle['best_rank'],
            'worst_rank': best_cycle['worst_rank'],
            'mean_pct': best_cycle['mean_pct'],
            'top_10pct': best_cycle['top_10pct'],
            'top_25pct': best_cycle['top_25pct'],
            'top_50pct': best_cycle['top_50pct'],
            'results': best_cycle['results'],
        }
        with open(OUTPUT_DIR / 'wetlab_13_similar_ranking.json', 'w') as f:
            json.dump(best_report, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved wetlab_13_similar_ranking.json (best: cycle_{best_cycle['cycle']})")

        # Print final table
        print(f"\n{'='*80}")
        print(f"  E34 Best 13-mol Ranking: cycle_{best_cycle['cycle']}")
        print(f"  Mean: #{best_cycle['mean_rank']:.0f} (top {best_cycle['mean_pct']:.2f}%)")
        print(f"{'='*80}")
        for r in sorted(best_cycle['results'], key=lambda x: x['glare_rank']):
            print(f"  {r['wetlab_id']:>10s} → {r['molfactory_id']:>16s}  "
                  f"GLARE=#{r['glare_rank']:>5d} ({r['glare_pct']:.1f}%)  "
                  f"Carsi=#{r['carsi_rank']:>5d}")

    print(f"\n✅ Done.")


if __name__ == '__main__':
    main()