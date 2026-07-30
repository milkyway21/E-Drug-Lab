#!/usr/bin/env python3
"""E35 v4 sweep — 测试不同 l2_lambda 值。

v4 l2_lambda=0.1 太强：loss=11.03（anchor loss 主导），排名几乎不变。
现在 sweep [3e-3, 1e-2, 3e-2] 找 L2-SP 最佳强度。
"""
import sys, os, json, time
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import train, query

# ── Config ──────────────────────────────────────────────────
E34_CKPT = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403/e34_grpo_sup/checkpoints/cycle_7.pt'
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e35_finetune_13wetlab')
SDF_DIR = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第一轮分子生成15个实体分子'
DECOY_JSON = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709/data/decoys_10k.json'
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
PATENT_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv'
E34_RANKING = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403/wetlab_13_similar_ranking.json'

EPOCHS = 5
LR = 3e-4               # 恢复原始 lr，L2-SP 负责正则化
ENSEMBLE = 3
WEIGHT_DECAY = 1e-5
N_DECOYS = 200
N_PATENT = 100
POS_WEIGHT = 5.0
RANDOM_SEED = 42

POSITIVE_IDS = {'0228390', '0228414', 'LXC-106'}

WETLAB_MAP = [
    ('0228271', '200',   0.632), ('0228279', '4984',  0.554),
    ('0228283', '8529',  0.581), ('0228303', '1677',  1.000),
    ('0228366', '130',   1.000), ('0228390', '4913',  0.764),
    ('0228405', '246',   0.650), ('0228414', '1170',  1.000),
    ('0228416', '711',   0.614), ('0228417', '170',   0.621),
    ('LXC-102', '2648',  0.621), ('LXC-104', '4984',  0.554),
    ('LXC-106', '3311',  0.617),
]

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def extract_smiles_from_sdf(sdf_path):
    suppl = Chem.SDMolSupplier(sdf_path)
    if not suppl or len(suppl) == 0:
        return None
    mol = suppl[0]
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)

def prepare_data():
    """Prepare training data once (same for all sweep runs)."""
    train_smiles, train_labels, train_weights = [], [], []

    # Wet-lab
    for fname in sorted(os.listdir(SDF_DIR)):
        if not fname.endswith('.sdf'):
            continue
        sid = fname.replace('.sdf', '')
        canon = extract_smiles_from_sdf(os.path.join(SDF_DIR, fname))
        if canon is None:
            continue
        is_positive = sid in POSITIVE_IDS
        train_smiles.append(canon)
        train_labels.append(1 if is_positive else 0)
        train_weights.append(POS_WEIGHT if is_positive else 1.0)

    # Patent
    patent_df = pd.read_csv(PATENT_CSV)
    rng = np.random.default_rng(RANDOM_SEED)
    patent_indices = rng.choice(len(patent_df), size=N_PATENT, replace=False)
    existing = set(train_smiles)
    for idx in patent_indices:
        row = patent_df.iloc[idx]
        canon = norm(row['canonical_smiles'])
        if not canon or canon in existing:
            continue
        label_active = int(row['label_active'])
        train_smiles.append(canon)
        train_labels.append(1 if label_active == 1 else 0)
        train_weights.append(float(row['sample_weight']))
        existing.add(canon)

    # Decoys
    with open(DECOY_JSON) as f:
        decoys = json.load(f)
    decoy_indices = rng.choice(len(decoys), size=N_DECOYS, replace=False)
    for idx in decoy_indices:
        canon = norm(decoys[idx])
        if canon and canon not in existing:
            train_smiles.append(canon)
            train_labels.append(0)
            train_weights.append(1.0)
            existing.add(canon)

    return train_smiles, train_labels, train_weights

def rank_and_eval(ckpt_path, pool_csv, e34_ranking_path):
    """Query MolFactory pool and compute 13-molecule ranking."""
    mf_pool_df = pd.read_csv(pool_csv)
    pool_smiles = [norm(s) for s in mf_pool_df['smiles'].tolist()]
    pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))

    mf_id_to_canon = {}
    for i, row in mf_pool_df.iterrows():
        mf_id_to_canon[str(row['ID'])] = norm(row['smiles'])

    qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
    ranked = qr.get('ranked', [])
    n_pool = len(ranked)

    rank_map = {}
    for r in ranked:
        rank_map[norm(r['smiles'])] = int(r['glare_rank'])

    results = []
    for wetlab_id, mf_id, tanimoto in WETLAB_MAP:
        canon = mf_id_to_canon.get(mf_id)
        if not canon:
            continue
        rank = rank_map.get(canon)
        if rank is not None:
            results.append({
                'wetlab_id': wetlab_id, 'molfactory_id': f'MolFactory_{mf_id}',
                'tanimoto': tanimoto, 'glare_rank': rank,
                'glare_pct': round(100 * rank / n_pool, 2),
                'is_positive': wetlab_id in POSITIVE_IDS,
            })

    ranks = [r['glare_rank'] for r in results]
    pos_ranks = [r['glare_rank'] for r in results if r['is_positive']]

    with open(e34_ranking_path) as f:
        e34_data = json.load(f)
    e34_mean = e34_data['mean_rank']

    return {
        'mean_rank': float(np.mean(ranks)),
        'median_rank': float(np.median(ranks)),
        'pos_mean_rank': float(np.mean(pos_ranks)) if pos_ranks else None,
        'n_pool': n_pool,
        'e34_mean': e34_mean,
        'results': results,
    }

def main():
    sweep_dir = OUTPUT_DIR / 'v4_l2sp_sweep'
    sweep_dir.mkdir(parents=True, exist_ok=True)

    L2_LAMBDAS = [3e-3, 1e-2, 3e-2]

    print("=" * 80)
    print("  E35 v4 L2-SP Sweep")
    print(f"  l2_lambda values: {L2_LAMBDAS}")
    print(f"  lr={LR}, weight_decay={WEIGHT_DECAY}, epochs={EPOCHS}")
    print("=" * 80)

    # Prepare data once
    train_smiles, train_labels, train_weights = prepare_data()
    total_pos = sum(train_labels)
    print(f"\nTraining data: {len(train_smiles)} molecules (pos={total_pos}, neg={len(train_labels)-total_pos})")

    summary = []
    for l2_lambda in L2_LAMBDAS:
        print(f"\n{'─'*60}")
        print(f"  l2_lambda = {l2_lambda} ({l2_lambda/3e-4:.0f}x default)")
        print(f"{'─'*60}")

        ckpt_path = str(sweep_dir / f'e35_v4_l2sp_{l2_lambda:.0e}.pt')
        t0 = time.time()

        result = train(
            checkpoint_path=ckpt_path,
            train_smiles=train_smiles,
            train_labels=train_labels,
            sample_weights=train_weights,
            prev_checkpoint=E34_CKPT,
            epochs=EPOCHS,
            ensemble_size=ENSEMBLE,
            lr=LR,
            l2_lambda=l2_lambda,
            weight_decay=WEIGHT_DECAY,
            strategy="supervised",
        )

        if not result.get('ok', False):
            print(f"  ❌ Failed: {result.get('error', str(result)[:200])}")
            continue

        loss = result.get('final_loss', None)
        train_time = time.time() - t0
        print(f"  ✅ Trained in {train_time:.0f}s, loss={loss}")

        # Rank
        tq = time.time()
        eval_result = rank_and_eval(ckpt_path, POOL_CSV, E34_RANKING)
        query_time = time.time() - tq

        e34_mean = eval_result['e34_mean']
        e35_mean = eval_result['mean_rank']
        delta = e34_mean - e35_mean
        n_pool = eval_result['n_pool']

        print(f"  Mean rank: #{e35_mean:.0f} ({100*e35_mean/n_pool:.2f}%), "
              f"Δ vs E34: {delta:+.0f}, "
              f"Pos mean: #{eval_result['pos_mean_rank']:.0f}")

        # Per-molecule
        for r in eval_result['results']:
            wid = r['wetlab_id']
            pos_mark = '🟢' if r['is_positive'] else '🔴'
            print(f"    {pos_mark} {wid}: #{r['glare_rank']} ({r['glare_pct']}%)")

        summary.append({
            'l2_lambda': l2_lambda,
            'loss': loss,
            'train_time': train_time,
            'query_time': query_time,
            'mean_rank': e35_mean,
            'pos_mean_rank': eval_result['pos_mean_rank'],
            'median_rank': eval_result['median_rank'],
            'delta_vs_e34': delta,
            'n_pool': n_pool,
        })

    # ── Summary table ────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  Sweep Summary")
    print(f"{'='*80}")
    print(f"  {'l2_lambda':>12s} {'x default':>10s} {'Loss':>10s} {'Mean Rank':>12s} {'vs E34':>10s} {'Pos Mean':>10s}")
    print(f"  {'─'*70}")
    print(f"  {'E34 (base)':>12s} {'—':>10s} {'—':>10s} #{e34_mean:>11.0f} {'—':>10s} —")
    for s in summary:
        x_default = s['l2_lambda'] / 3e-4
        print(f"  {s['l2_lambda']:>12.0e} {x_default:>10.0f}x {s['loss']:>10.4f} "
              f"#{s['mean_rank']:>11.0f} {s['delta_vs_e34']:>+10.0f} "
              f"#{s['pos_mean_rank']:>9.0f}")

    best = min(summary, key=lambda s: s['mean_rank'])
    print(f"\n  Best: l2_lambda={best['l2_lambda']:.0e}, mean_rank=#{best['mean_rank']:.0f}")

    # Save
    with open(sweep_dir / 'sweep_summary.json', 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"✅ Sweep saved: {sweep_dir / 'sweep_summary.json'}")


if __name__ == '__main__':
    main()