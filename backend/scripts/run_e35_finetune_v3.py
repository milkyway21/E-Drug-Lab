#!/usr/bin/env python3
"""E35 v3 — 提高活性分子权重 + 专利集100分子 + 正确标签 Fine-Tune E34。

v2 问题：12 wet-lab (3pos/9neg) + 200 decoys → 灾难性遗忘，3正样本从 #1005 掉到 #6932
v3 策略：
  1. 正样本权重 2.0 → 5.0（强化活性信号）
  2. 从 403 专利集随机抽 100 分子（保留原权重）→ 防止遗忘 E34 学到的知识
  3. 200 decoys 不变
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
LR = 3e-4
ENSEMBLE = 3
N_DECOYS = 200
N_PATENT = 100
POS_WEIGHT = 5.0        # v2=2.0 → v3=5.0
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
    v3_dir = OUTPUT_DIR / 'v3'
    v3_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E35 v3 — 高权重正样本 + 100专利分子 Fine-Tune E34 cycle_7")
    print(f"  Positive: {POSITIVE_IDS} (蓝框=是)")
    print(f"  Negative: 其余 10 个")
    print(f"  Config: pos_weight={POS_WEIGHT}, +{N_PATENT} patent, +{N_DECOYS} decoys")
    print(f"  epochs={EPOCHS}, lr={LR}, ensemble={ENSEMBLE}")
    print("=" * 80)

    # ── Step 1: Extract SMILES from SDF files ─────────────────
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
    print(f"\n[2/5] Adding {N_PATENT} patent molecules from 403 pool...")
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
        # Use patent's own label and weight
        label_active = int(row['label_active'])
        label = 1 if label_active == 1 else 0  # weak (-1) → 0
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
    print(f"  Total training: {len(train_smiles)} molecules (pos={total_pos}, neg={total_neg})")
    print(f"  Composition: {len(train_smiles)-n_pat_added-n_decoy_added} wet-lab + {n_pat_added} patent + {n_decoy_added} decoys")

    # ── Step 4: Fine-tune ─────────────────────────────────────
    ckpt_path = str(v3_dir / 'e35_finetune_v3.pt')
    print(f"\n[4/5] Fine-tuning from E34 cycle_7...")
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

    print(f"\nE35 v3 (post fine-tune): mean=#{e35_mean:.0f} ({100*e35_mean/n_pool:.2f}%), "
          f"median=#{e35_median:.0f}")
    if pos_ranks:
        print(f"  3 Positives: mean=#{np.mean(pos_ranks):.0f} ({100*np.mean(pos_ranks)/n_pool:.2f}%)")
    if neg_ranks:
        print(f"  10 Negatives: mean=#{np.mean(neg_ranks):.0f} ({100*np.mean(neg_ranks)/n_pool:.2f}%)")

    # ── Load E34 pre-fine-tune + E35 v2 ──────────────────────
    with open(E34_RANKING) as f:
        e34_data = json.load(f)
    e34_results = {r['wetlab_id']: r for r in e34_data['results']}
    e34_mean = e34_data['mean_rank']

    v2_json = OUTPUT_DIR / 'wetlab_13_ranking_pre_vs_post_v2.json'
    e35_v2_mean = None
    if v2_json.exists():
        with open(v2_json) as f:
            v2_data = json.load(f)
        e35_v2_mean = v2_data['e35_post']['mean_rank']

    # ── Comparison: E34 vs E35 v2 vs E35 v3 ──────────────────
    print(f"\n{'='*90}")
    print(f"  E34 vs E35 v2 vs E35 v3 Comparison")
    print(f"{'='*90}")
    header = f"  {'WetLab':>10s} {'MF_ID':>16s} {'Pos':>4s} {'E34':>8s} {'E35v2':>8s} {'E35v3':>8s} {'Δv3':>8s}"
    print(header)
    print(f"  {'─'*75}")

    # Load v2 results for per-molecule comparison
    v2_results = {}
    if v2_json.exists():
        for r in v2_data['e35_post']['results']:
            v2_results[r['wetlab_id']] = r

    deltas_v3 = []
    for r in e35_results:
        wid = r['wetlab_id']
        pre_rank = e34_results[wid]['glare_rank'] if wid in e34_results else None
        v2_rank = v2_results[wid]['glare_rank'] if wid in v2_results else None
        post_rank = r['glare_rank']
        pos_mark = '🟢' if r['is_positive'] else '🔴'

        e34_str = f"#{pre_rank:>6d}" if pre_rank else f"{'N/A':>7s}"
        v2_str = f"#{v2_rank:>6d}" if v2_rank else f"{'N/A':>7s}"

        if pre_rank:
            delta_v3 = pre_rank - post_rank
            deltas_v3.append(delta_v3)
            better = '🟢 +' if delta_v3 > 0 else ('🔴 ' if delta_v3 < 0 else '  =')
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} {pos_mark:>4s} {e34_str} {v2_str} #{post_rank:>6d}  {delta_v3:>+7d}  {better}")
        else:
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} {pos_mark:>4s} {e34_str} {v2_str} #{post_rank:>6d}")

    n_improved = sum(1 for d in deltas_v3 if d > 0)
    n_worse = sum(1 for d in deltas_v3 if d < 0)
    pos_deltas = [d for i, d in enumerate(deltas_v3) if e35_results[i]['is_positive']]
    neg_deltas = [d for i, d in enumerate(deltas_v3) if not e35_results[i]['is_positive']]

    print(f"\n  Summary:")
    print(f"  E34  mean rank: #{e34_mean:.0f} ({100*e34_mean/n_pool:.2f}%)")
    if e35_v2_mean:
        print(f"  E35v2 mean rank: #{e35_v2_mean:.0f} ({100*e35_v2_mean/n_pool:.2f}%)")
    print(f"  E35v3 mean rank: #{e35_mean:.0f} ({100*e35_mean/n_pool:.2f}%)")
    print(f"  vs E34:  Improved={n_improved}/13, Worse={n_worse}/13, Mean Δ={np.mean(deltas_v3):+.0f}")
    if pos_deltas:
        print(f"  3 Positives vs E34: Mean Δ={np.mean(pos_deltas):+.0f}")
    if neg_deltas:
        print(f"  10 Negatives vs E34: Mean Δ={np.mean(neg_deltas):+.0f}")

    # ── Save report ──────────────────────────────────────────
    report = {
        'version': 'v3',
        'description': 'Higher positive weights (5.0) + 100 patent molecules + 200 decoys',
        'pool_size': int(n_pool),
        'base_checkpoint': E34_CKPT,
        'fine_tuned_checkpoint': ckpt_path,
        'training': {
            'n_wetlab': len(train_smiles) - n_pat_added - n_decoy_added,
            'n_patent': n_pat_added,
            'n_decoys': n_decoy_added,
            'n_total': len(train_smiles),
            'n_pos': int(total_pos),
            'n_neg': int(total_neg),
            'positive_ids': list(POSITIVE_IDS),
            'pos_weight': POS_WEIGHT,
            'epochs': EPOCHS,
            'lr': LR,
            'loss': loss,
        },
        'e34_pre': {
            'mean_rank': e34_mean,
            'median_rank': e34_data['median_rank'],
            'top_10pct': e34_data['top_10pct'],
            'top_25pct': e34_data['top_25pct'],
            'top_50pct': e34_data['top_50pct'],
        },
        'e35_v2': {
            'mean_rank': e35_v2_mean,
        } if e35_v2_mean else None,
        'e35_v3': {
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

    report_path = v3_dir / 'wetlab_13_ranking_e35_v3.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report saved: {report_path}")

    print(f"\n✅ E35 v3 Done.")


if __name__ == '__main__':
    main()