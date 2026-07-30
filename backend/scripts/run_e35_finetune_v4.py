#!/usr/bin/env python3
"""E35 v4 — 论文方法 L2-SP 正则化 Fine-Tune E34。

GLARE 模型自带 anchored regularization（= L2-SP）：
  加载 prev_checkpoint 后设 anchor = 预训练权重，
  训练时加 penalty: l2_lambda * ||θ - θ_anchor||²

v2/v3 问题: l2_lambda=3e-4（为 403 分子设计），12 分子时 task loss 噪声
  压倒 anchor 约束 → 灾难性遗忘。

v4 策略（参考 L2-SP 论文 "Explicit Inductive Bias for Transfer Learning"）：
  1. l2_lambda: 3e-4 → 1e-1（333x，强约束权重不偏离 E34）
  2. lr: 3e-4 → 1e-4（3x 降低，小步更新）
  3. weight_decay: 0.0 → 1e-5（AdamW 风格 weight decay）
  4. 数据同 v3: 12 wet-lab + 100 patent + 200 decoys
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

# ── v4 Hyperparams ──────────────────────────────────────────
EPOCHS = 5
LR = 1e-4               # v3=3e-4 → 1e-4（3x 降低）
ENSEMBLE = 3
L2_LAMBDA = 1e-1        # v3=3e-4 → 1e-1（333x，强 L2-SP）
WEIGHT_DECAY = 1e-5     # v3=0.0 → 1e-5（AdamW 风格）
N_DECOYS = 200
N_PATENT = 100
POS_WEIGHT = 5.0
RANDOM_SEED = 42

POSITIVE_IDS = {'0228390', '0228414', 'LXC-106'}

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

def extract_smiles_from_sdf(sdf_path):
    suppl = Chem.SDMolSupplier(sdf_path)
    if not suppl or len(suppl) == 0:
        return None
    mol = suppl[0]
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)

def main():
    v4_dir = OUTPUT_DIR / 'v4_l2sp'
    v4_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E35 v4 — L2-SP 正则化 Fine-Tune（论文 Anchored Regularization）")
    print(f"  Positive: {POSITIVE_IDS} (蓝框=是)")
    print(f"  Config: l2_lambda={L2_LAMBDA} (333x default), lr={LR} (1/3x)")
    print(f"          weight_decay={WEIGHT_DECAY}, pos_weight={POS_WEIGHT}")
    print(f"          +{N_PATENT} patent, +{N_DECOYS} decoys")
    print("=" * 80)

    # ── Step 1: Extract SMILES from SDF ───────────────────────
    print(f"\n[1/5] Extracting SMILES from SDF files...")
    train_smiles = []
    train_labels = []
    train_weights = []

    for fname in sorted(os.listdir(SDF_DIR)):
        if not fname.endswith('.sdf'):
            continue
        sid = fname.replace('.sdf', '')
        fpath = os.path.join(SDF_DIR, fname)
        canon = extract_smiles_from_sdf(fpath)
        if canon is None:
            print(f"  ⚠️ {sid}: FAILED to parse SDF")
            continue

        is_positive = sid in POSITIVE_IDS
        label = 1 if is_positive else 0
        weight = POS_WEIGHT if is_positive else 1.0

        train_smiles.append(canon)
        train_labels.append(label)
        train_weights.append(weight)
        print(f"  {'🟢' if is_positive else '🔴'} {sid}: label={label}, weight={weight}, {canon[:60]}...")

    n_pos = sum(train_labels)
    n_neg = len(train_labels) - n_pos
    print(f"  Wet-lab: {len(train_smiles)} molecules (pos={n_pos}, neg={n_neg})")

    # ── Step 2: Add 100 patent molecules ──────────────────────
    print(f"\n[2/5] Adding {N_PATENT} patent molecules...")
    patent_df = pd.read_csv(PATENT_CSV)
    rng = np.random.default_rng(RANDOM_SEED)
    patent_indices = rng.choice(len(patent_df), size=N_PATENT, replace=False)

    existing_canons = set(train_smiles)
    n_pat_added = 0
    n_pat_pos = 0
    for idx in patent_indices:
        row = patent_df.iloc[idx]
        canon = norm(row['canonical_smiles'])
        if not canon or canon in existing_canons:
            continue
        label_active = int(row['label_active'])
        label = 1 if label_active == 1 else 0
        weight = float(row['sample_weight'])
        train_smiles.append(canon)
        train_labels.append(label)
        train_weights.append(weight)
        existing_canons.add(canon)
        n_pat_added += 1
        if label == 1:
            n_pat_pos += 1

    print(f"  Added {n_pat_added} patent molecules (pos={n_pat_pos}, neg={n_pat_added-n_pat_pos})")

    # ── Step 3: Add 200 decoys ────────────────────────────────
    print(f"\n[3/5] Adding {N_DECOYS} decoys...")
    with open(DECOY_JSON) as f:
        decoys = json.load(f)
    decoy_indices = rng.choice(len(decoys), size=N_DECOYS, replace=False)

    n_decoy_added = 0
    for idx in decoy_indices:
        canon = norm(decoys[idx])
        if canon and canon not in existing_canons:
            train_smiles.append(canon)
            train_labels.append(0)
            train_weights.append(1.0)
            existing_canons.add(canon)
            n_decoy_added += 1

    total_pos = sum(train_labels)
    total_neg = len(train_labels) - total_pos
    print(f"  Added {n_decoy_added} decoys")
    print(f"  Total: {len(train_smiles)} molecules (pos={total_pos}, neg={total_neg})")

    # ── Step 4: Fine-tune with L2-SP ──────────────────────────
    ckpt_path = str(v4_dir / 'e35_finetune_v4_l2sp.pt')
    print(f"\n[4/5] Fine-tuning with L2-SP (l2_lambda={L2_LAMBDA}, lr={LR})...")
    print(f"  Anchor = E34 cycle_7 weights, penalty = {L2_LAMBDA} * ||θ - θ_E34||²")
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
        l2_lambda=L2_LAMBDA,
        weight_decay=WEIGHT_DECAY,
        strategy="supervised",
    )

    if not result.get('ok', False):
        print(f"❌ Fine-tune failed: {result.get('error', str(result)[:300])}")
        return

    loss = result.get('final_loss', None)
    print(f"✅ Fine-tuned in {time.time()-t0:.0f}s, loss={loss}")

    # ── Step 5: Rank 13 similar molecules ─────────────────────
    print(f"\n[5/5] Ranking 13 similar molecules on MolFactory pool...")
    mf_pool_df = pd.read_csv(POOL_CSV)
    pool_smiles = [norm(s) for s in mf_pool_df['smiles'].tolist()]
    pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))

    mf_id_to_canon = {}
    for i, row in mf_pool_df.iterrows():
        mf_id_to_canon[str(row['ID'])] = norm(row['smiles'])

    print(f"  Querying on {len(pool_smiles)} molecules...")
    tq = time.time()
    qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
    if not qr.get('ok', False) and 'ranked' not in qr:
        print(f"❌ Query failed: {qr.get('error', str(qr)[:300])}")
        return

    ranked = qr.get('ranked', [])
    n_pool = len(ranked)
    print(f"✅ Ranked in {time.time()-tq:.0f}s")

    rank_map = {}
    for r in ranked:
        rank_map[norm(r['smiles'])] = {
            'rank': int(r['glare_rank']),
            'score': float(r['glare_select_prob']),
        }

    # ── Match 13 similar molecules ───────────────────────────
    e35_results = []
    for wetlab_id, mf_id, tanimoto in WETLAB_MAP:
        canon = mf_id_to_canon.get(mf_id)
        if not canon:
            continue
        entry = rank_map.get(canon)
        if entry:
            carsi_idx = mf_pool_df[mf_pool_df['ID'].astype(str) == mf_id].index
            carsi_rank = int(carsi_idx[0] + 1) if len(carsi_idx) > 0 else None
            e35_results.append({
                'wetlab_id': wetlab_id,
                'molfactory_id': f'MolFactory_{mf_id}',
                'tanimoto': tanimoto,
                'glare_rank': entry['rank'],
                'glare_score': round(entry['score'], 6),
                'glare_pct': round(100 * entry['rank'] / n_pool, 2),
                'carsi_rank': carsi_rank,
                'is_positive': wetlab_id in POSITIVE_IDS,
            })

    e35_ranks = [r['glare_rank'] for r in e35_results]
    e35_mean = float(np.mean(e35_ranks))
    e35_median = float(np.median(e35_ranks))

    pos_ranks = [r['glare_rank'] for r in e35_results if r['is_positive']]
    neg_ranks = [r['glare_rank'] for r in e35_results if not r['is_positive']]

    print(f"\nE35 v4 (L2-SP): mean=#{e35_mean:.0f} ({100*e35_mean/n_pool:.2f}%), "
          f"median=#{e35_median:.0f}")
    if pos_ranks:
        print(f"  3 Positives: mean=#{np.mean(pos_ranks):.0f} ({100*np.mean(pos_ranks)/n_pool:.2f}%)")
    if neg_ranks:
        print(f"  10 Negatives: mean=#{np.mean(neg_ranks):.0f} ({100*np.mean(neg_ranks)/n_pool:.2f}%)")

    # ── Load E34 + v2 + v3 ───────────────────────────────────
    with open(E34_RANKING) as f:
        e34_data = json.load(f)
    e34_results = {r['wetlab_id']: r for r in e34_data['results']}
    e34_mean = e34_data['mean_rank']

    v2_json = OUTPUT_DIR / 'wetlab_13_ranking_pre_vs_post_v2.json'
    v3_json = OUTPUT_DIR / 'v3' / 'wetlab_13_ranking_e35_v3.json'

    v2_results = {}
    if v2_json.exists():
        with open(v2_json) as f:
            v2_data = json.load(f)
        for r in v2_data['e35_post']['results']:
            v2_results[r['wetlab_id']] = r

    v3_results = {}
    if v3_json.exists():
        with open(v3_json) as f:
            v3_data = json.load(f)
        for r in v3_data['e35_v3']['results']:
            v3_results[r['wetlab_id']] = r

    # ── Comparison ───────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  E34 vs E35 v2 vs E35 v3 vs E35 v4 (L2-SP)")
    print(f"{'='*100}")
    print(f"  {'WetLab':>10s} {'MF_ID':>16s} {'Pos':>4s} {'E34':>8s} {'v2':>8s} {'v3':>8s} {'v4':>8s} {'Δv4':>8s}")
    print(f"  {'─'*85}")

    deltas_v4 = []
    for r in e35_results:
        wid = r['wetlab_id']
        pre_rank = e34_results[wid]['glare_rank'] if wid in e34_results else None
        v2_rank = v2_results[wid]['glare_rank'] if wid in v2_results else None
        v3_rank = v3_results[wid]['glare_rank'] if wid in v3_results else None
        post_rank = r['glare_rank']
        pos_mark = '🟢' if r['is_positive'] else '🔴'

        e34_str = f"#{pre_rank:>6d}" if pre_rank else "N/A"
        v2_str = f"#{v2_rank:>6d}" if v2_rank else "N/A"
        v3_str = f"#{v3_rank:>6d}" if v3_rank else "N/A"

        if pre_rank:
            delta_v4 = pre_rank - post_rank
            deltas_v4.append(delta_v4)
            better = '🟢 +' if delta_v4 > 0 else ('🔴 ' if delta_v4 < 0 else '  =')
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} {pos_mark:>4s} {e34_str} {v2_str} {v3_str} #{post_rank:>6d}  {delta_v4:>+7d}  {better}")
        else:
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} {pos_mark:>4s} {e34_str} {v2_str} {v3_str} #{post_rank:>6d}")

    n_improved = sum(1 for d in deltas_v4 if d > 0)
    n_worse = sum(1 for d in deltas_v4 if d < 0)
    pos_deltas = [d for i, d in enumerate(deltas_v4) if e35_results[i]['is_positive']]
    neg_deltas = [d for i, d in enumerate(deltas_v4) if not e35_results[i]['is_positive']]

    e35_v2_mean = v2_data['e35_post']['mean_rank'] if v2_json.exists() else None
    e35_v3_mean = v3_data['e35_v3']['mean_rank'] if v3_json.exists() else None

    print(f"\n  Summary:")
    print(f"  {'Method':<12s} {'Mean Rank':>12s} {'vs E34':>10s} {'Pos Mean':>10s} {'Improved':>10s}")
    print(f"  {'─'*55}")
    print(f"  {'E34':<12s} #{e34_mean:>11.0f} {'—':>10s} —          —")
    if e35_v2_mean:
        print(f"  {'E35 v2':<12s} #{e35_v2_mean:>11.0f} {e35_v2_mean-e34_mean:>+10.0f} —          —")
    if e35_v3_mean:
        print(f"  {'E35 v3':<12s} #{e35_v3_mean:>11.0f} {e35_v3_mean-e34_mean:>+10.0f} —          —")
    print(f"  {'E35 v4':<12s} #{e35_mean:>11.0f} {e35_mean-e34_mean:>+10.0f} "
          f"#{np.mean(pos_ranks):>9.0f} {n_improved:>7d}/13  {'✅' if n_improved > 6 else '⚠️'}")

    if pos_deltas:
        print(f"\n  3 Positives vs E34: Mean Δ={np.mean(pos_deltas):+.0f}")
    if neg_deltas:
        print(f"  10 Negatives vs E34: Mean Δ={np.mean(neg_deltas):+.0f}")

    # ── Save report ──────────────────────────────────────────
    report = {
        'version': 'v4_l2sp',
        'description': 'L2-SP regularization (anchored to E34) with l2_lambda=0.1, lr=1e-4, weight_decay=1e-5',
        'pool_size': int(n_pool),
        'base_checkpoint': E34_CKPT,
        'fine_tuned_checkpoint': ckpt_path,
        'hyperparams': {
            'l2_lambda': L2_LAMBDA,
            'lr': LR,
            'weight_decay': WEIGHT_DECAY,
            'epochs': EPOCHS,
            'ensemble_size': ENSEMBLE,
            'pos_weight': POS_WEIGHT,
            'strategy': 'supervised',
            'note': 'L2-SP via GLARE anchored regularization. Anchor = E34 cycle_7 weights. '
                     'l2_lambda 333x default (3e-4→1e-1) to prevent catastrophic forgetting on 12 molecules.',
        },
        'training': {
            'n_wetlab': len(train_smiles) - n_pat_added - n_decoy_added,
            'n_patent': n_pat_added,
            'n_decoys': n_decoy_added,
            'n_total': len(train_smiles),
            'n_pos': int(total_pos),
            'n_neg': int(total_neg),
            'positive_ids': list(POSITIVE_IDS),
            'loss': loss,
        },
        'e34_pre': {
            'mean_rank': e34_mean,
            'median_rank': e34_data['median_rank'],
        },
        'e35_v2': {'mean_rank': e35_v2_mean} if e35_v2_mean else None,
        'e35_v3': {'mean_rank': e35_v3_mean} if e35_v3_mean else None,
        'e35_v4': {
            'mean_rank': e35_mean,
            'median_rank': e35_median,
            'pos_mean_rank': float(np.mean(pos_ranks)) if pos_ranks else None,
            'neg_mean_rank': float(np.mean(neg_ranks)) if neg_ranks else None,
            'top_10pct': int(sum(1 for r in e35_ranks if r <= n_pool * 0.10)),
            'top_25pct': int(sum(1 for r in e35_ranks if r <= n_pool * 0.25)),
            'top_50pct': int(sum(1 for r in e35_ranks if r <= n_pool * 0.50)),
            'results': e35_results,
        },
        'delta_vs_e34': {
            'mean_rank': round(e34_mean - e35_mean, 1),
            'n_improved': n_improved,
            'n_worse': n_worse,
            'pos_mean_delta': round(float(np.mean(pos_deltas)), 1) if pos_deltas else None,
            'neg_mean_delta': round(float(np.mean(neg_deltas)), 1) if neg_deltas else None,
        },
    }

    report_path = v4_dir / 'wetlab_13_ranking_e35_v4_l2sp.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report saved: {report_path}")
    print(f"✅ E35 v4 Done.")


if __name__ == '__main__':
    main()