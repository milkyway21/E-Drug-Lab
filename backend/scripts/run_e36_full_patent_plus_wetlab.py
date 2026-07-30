#!/usr/bin/env python3
"""E36 — 403专利 + 13湿实验分子 全量从头训练（E11风格）。

不 fine-tune，直接将湿实验分子混入训练集从头训练，
让湿实验信号融入初始权重，避免灾难性遗忘。

对比 E34（仅403专利）看湿实验数据是否带来提升。
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
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e36_full_patent_plus_wetlab')
SDF_DIR = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第一轮分子生成15个实体分子'
WETLAB_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv'
PATENT_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv'
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
E34_RANKING = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403/wetlab_13_similar_ranking.json'

EPOCHS = 50
LR = 3e-4
ENSEMBLE = 3
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

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E36 — 403专利 + 13湿实验 全量从头训练（E11风格）")
    print(f"  Strategy: supervised, epochs={EPOCHS}, lr={LR}")
    print(f"  Positive wet-lab: {POSITIVE_IDS}")
    print("=" * 80)

    # ── Step 1: Load 13 wet-lab molecules ────────────────────
    print(f"\n[1/4] Loading 13 wet-lab molecules...")
    train_smiles = []
    train_labels = []
    train_weights = []

    # Load wet-lab CSV for SMILES references
    wetlab_df = pd.read_csv(WETLAB_CSV)
    wetlab_smi_map = {}
    for _, row in wetlab_df.iterrows():
        wetlab_smi_map[str(row['SDF_ID'])] = str(row['SMILES'])

    for fname in sorted(os.listdir(SDF_DIR)):
        if not fname.endswith('.sdf'):
            continue
        sid = fname.replace('.sdf', '')
        fpath = os.path.join(SDF_DIR, fname)

        # Try SDF first, fall back to CSV
        canon = extract_smiles_from_sdf(fpath)
        if canon is None:
            # Fallback to CSV SMILES
            csv_smi = wetlab_smi_map.get(sid)
            if csv_smi:
                canon = norm(csv_smi)
                print(f"  ⚠️ {sid}: SDF parse failed, using CSV SMILES → {canon[:60]}...")
            else:
                print(f"  ❌ {sid}: No SMILES available (SDF failed + CSV missing)")
                continue

        is_positive = sid in POSITIVE_IDS
        label = 1 if is_positive else 0
        weight = POS_WEIGHT if is_positive else 1.0

        train_smiles.append(canon)
        train_labels.append(label)
        train_weights.append(weight)
        print(f"  {'🟢' if is_positive else '🔴'} {sid}: label={label}, weight={weight}, {canon[:60]}...")

    n_wet_pos = sum(train_labels)
    n_wet_neg = len(train_labels) - n_wet_pos
    print(f"  Wet-lab: {len(train_smiles)} molecules (pos={n_wet_pos}, neg={n_wet_neg})")

    # ── Step 2: Load ALL 403 patent molecules ────────────────
    print(f"\n[2/4] Loading 403 patent molecules...")
    patent_df = pd.read_csv(PATENT_CSV)
    existing_canons = set(train_smiles)
    n_pat_added = 0
    n_pat_pos = 0

    for _, row in patent_df.iterrows():
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

    total_pos = sum(train_labels)
    total_neg = len(train_labels) - total_pos
    print(f"  Patent: {n_pat_added} added (pos={n_pat_pos}, neg={n_pat_added-n_pat_pos})")
    print(f"  Total: {len(train_smiles)} molecules (pos={total_pos}, neg={total_neg})")

    # ── Step 3: Train from scratch ───────────────────────────
    ckpt_path = str(OUTPUT_DIR / 'e36_full.pt')
    print(f"\n[3/4] Training from scratch (no prev_checkpoint)...")
    print(f"  epochs={EPOCHS}, lr={LR}, ensemble={ENSEMBLE}, strategy=supervised")
    t0 = time.time()

    result = train(
        checkpoint_path=ckpt_path,
        train_smiles=train_smiles,
        train_labels=train_labels,
        sample_weights=train_weights,
        prev_checkpoint=None,  # train from scratch!
        epochs=EPOCHS,
        ensemble_size=ENSEMBLE,
        lr=LR,
        strategy="supervised",
    )

    if not result.get('ok', False):
        print(f"❌ Train failed: {result.get('error', str(result)[:300])}")
        return

    loss = result.get('final_loss', None)
    print(f"✅ Trained in {time.time()-t0:.0f}s, loss={loss}")

    # ── Step 4: Rank 13 similar molecules ────────────────────
    print(f"\n[4/4] Ranking 13 similar molecules on MolFactory pool...")
    mf_pool_df = pd.read_csv(POOL_CSV)
    pool_smiles = [norm(s) for s in mf_pool_df['smiles'].tolist()]
    pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))
    print(f"  Pool: {len(pool_smiles)} unique SMILES")

    mf_id_to_canon = {}
    for i, row in mf_pool_df.iterrows():
        mf_id_to_canon[str(row['ID'])] = norm(row['smiles'])

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
    e36_results = []
    for wetlab_id, mf_id, tanimoto in WETLAB_MAP:
        canon = mf_id_to_canon.get(mf_id)
        if not canon:
            continue
        entry = rank_map.get(canon)
        if entry:
            carsi_idx = mf_pool_df[mf_pool_df['ID'].astype(str) == mf_id].index
            carsi_rank = int(carsi_idx[0] + 1) if len(carsi_idx) > 0 else None
            e36_results.append({
                'wetlab_id': wetlab_id,
                'molfactory_id': f'MolFactory_{mf_id}',
                'tanimoto': tanimoto,
                'glare_rank': entry['rank'],
                'glare_score': round(entry['score'], 6),
                'glare_pct': round(100 * entry['rank'] / n_pool, 2),
                'carsi_rank': carsi_rank,
                'is_positive': wetlab_id in POSITIVE_IDS,
            })

    e36_ranks = [r['glare_rank'] for r in e36_results]
    e36_mean = float(np.mean(e36_ranks))
    e36_median = float(np.median(e36_ranks))

    pos_ranks = [r['glare_rank'] for r in e36_results if r['is_positive']]
    neg_ranks = [r['glare_rank'] for r in e36_results if not r['is_positive']]

    print(f"\nE36: mean=#{e36_mean:.0f} ({100*e36_mean/n_pool:.2f}%), median=#{e36_median:.0f}")
    if pos_ranks:
        print(f"  3 Positives: mean=#{np.mean(pos_ranks):.0f} ({100*np.mean(pos_ranks)/n_pool:.2f}%)")
    if neg_ranks:
        print(f"  10 Negatives: mean=#{np.mean(neg_ranks):.0f} ({100*np.mean(neg_ranks)/n_pool:.2f}%)")

    # ── Load E34 ─────────────────────────────────────────────
    with open(E34_RANKING) as f:
        e34_data = json.load(f)
    e34_results = {r['wetlab_id']: r for r in e34_data['results']}
    e34_mean = e34_data['mean_rank']

    # ── Comparison ───────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  E34 (403 patent) vs E36 (403 patent + 13 wet-lab)")
    print(f"{'='*80}")
    print(f"  {'WetLab':>10s} {'MF_ID':>16s} {'Pos':>4s} {'E34':>8s} {'E36':>8s} {'Δ':>8s}")
    print(f"  {'─'*60}")

    deltas = []
    for r in e36_results:
        wid = r['wetlab_id']
        pre_rank = e34_results[wid]['glare_rank'] if wid in e34_results else None
        post_rank = r['glare_rank']
        pos_mark = '🟢' if r['is_positive'] else '🔴'
        if pre_rank:
            delta = pre_rank - post_rank
            deltas.append(delta)
            better = '🟢 +' if delta > 0 else ('🔴 ' if delta < 0 else '  =')
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} {pos_mark:>4s} #{pre_rank:>6d}  #{post_rank:>6d}  {delta:>+7d}  {better}")

    n_improved = sum(1 for d in deltas if d > 0)
    n_worse = sum(1 for d in deltas if d < 0)
    pos_deltas = [d for i, d in enumerate(deltas) if e36_results[i]['is_positive']]
    neg_deltas = [d for i, d in enumerate(deltas) if not e36_results[i]['is_positive']]

    print(f"\n  E34 mean: #{e34_mean:.0f} ({100*e34_mean/n_pool:.2f}%)")
    print(f"  E36 mean: #{e36_mean:.0f} ({100*e36_mean/n_pool:.2f}%), Δ={e34_mean-e36_mean:+.0f}")
    if pos_deltas:
        print(f"  3 Positives: Mean Δ={np.mean(pos_deltas):+.0f}")
    if neg_deltas:
        print(f"  10 Negatives: Mean Δ={np.mean(neg_deltas):+.0f}")
    print(f"  Improved: {n_improved}/13, Worse: {n_worse}/13")

    success = e36_mean < e34_mean
    print(f"\n  {'✅ E36 BETTER THAN E34!' if success else '❌ E36 still worse than E34'}")

    # ── Save report ──────────────────────────────────────────
    report = {
        'version': 'e36',
        'description': '403 patent + 13 wet-lab molecules, trained from scratch (E11 style)',
        'pool_size': int(n_pool),
        'checkpoint': ckpt_path,
        'hyperparams': {
            'epochs': EPOCHS, 'lr': LR, 'ensemble_size': ENSEMBLE,
            'strategy': 'supervised', 'pos_weight': POS_WEIGHT,
            'note': 'No prev_checkpoint — trained from scratch',
        },
        'training': {
            'n_wetlab': int(n_wet_pos + n_wet_neg),
            'n_patent': n_pat_added,
            'n_total': len(train_smiles),
            'n_pos': int(total_pos),
            'n_neg': int(total_neg),
            'positive_ids': list(POSITIVE_IDS),
            'loss': loss,
        },
        'e34': {
            'mean_rank': e34_mean,
            'median_rank': e34_data['median_rank'],
        },
        'e36': {
            'mean_rank': e36_mean,
            'median_rank': e36_median,
            'pos_mean_rank': float(np.mean(pos_ranks)) if pos_ranks else None,
            'neg_mean_rank': float(np.mean(neg_ranks)) if neg_ranks else None,
            'top_10pct': int(sum(1 for r in e36_ranks if r <= n_pool * 0.10)),
            'top_25pct': int(sum(1 for r in e36_ranks if r <= n_pool * 0.25)),
            'top_50pct': int(sum(1 for r in e36_ranks if r <= n_pool * 0.50)),
            'results': e36_results,
        },
        'delta_vs_e34': {
            'mean_rank': round(e34_mean - e36_mean, 1),
            'n_improved': n_improved,
            'n_worse': n_worse,
            'e36_better': success,
        },
    }

    report_path = OUTPUT_DIR / 'e36_ranking.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report saved: {report_path}")
    print(f"✅ E36 Done.")


if __name__ == '__main__':
    main()