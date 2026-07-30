#!/usr/bin/env python3
"""E35 — 13 湿实验分子 Few-Shot Fine-Tune E34 权重 + 13 相似分子排名对比。

E11 风格小规模训练：全量数据一次性监督训练，少量 epochs。
从 E34 cycle_7 fine-tune，对比 fine-tune 前后 13 相似分子排名变化。
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
WETLAB_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv'
DECOY_JSON = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709/data/decoys_10k.json'
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
E34_RANKING = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403/wetlab_13_similar_ranking.json'

EPOCHS = 5
LR = 3e-4
ENSEMBLE = 3
N_DECOYS = 200
RANDOM_SEED = 42

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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E35 — 13 Wet-Lab Molecules Few-Shot Fine-Tune E34 cycle_7")
    print(f"  Method: Supervised training (E11 style), epochs={EPOCHS}, lr={LR}")
    print(f"  Base: E34 cycle_7")
    print("=" * 80)

    # ── Load 13 wet-lab molecules ────────────────────────────
    wetlab_df = pd.read_csv(WETLAB_CSV)
    print(f"\nLoaded 13 wet-lab molecules: "
          f"active={int((wetlab_df['label']==1).sum())}, "
          f"weak={int((wetlab_df['pDC50']>=6.0).sum() - (wetlab_df['label']==1).sum())}, "
          f"inactive={int((wetlab_df['pDC50']<6.0).sum())}")

    train_smiles = []
    train_labels = []
    train_weights = []

    for _, row in wetlab_df.iterrows():
        canon = norm(row['SMILES'])
        if not canon:
            continue
        pdc50 = float(row['pDC50'])
        is_strong = row['is_strong'] == 'True' or row['is_strong'] == True

        # Label: pDC50≥6.5 → 1, pDC50<6.0 → 0, [6.0,6.5) → excluded
        if pdc50 >= 6.5:
            label = 1
            weight = 2.0 if is_strong else 1.0
        elif pdc50 < 6.0:
            label = 0
            weight = 1.0
        else:  # [6.0, 6.5) weak
            label = 0  # treat as inactive for training
            weight = 0.5

        train_smiles.append(canon)
        train_labels.append(label)
        train_weights.append(weight)

    n_pos = sum(train_labels)
    n_neg = len(train_labels) - n_pos
    print(f"Training: {len(train_smiles)} wet-lab molecules (pos={n_pos}, neg={n_neg})")

    # ── Add decoys ───────────────────────────────────────────
    with open(DECOY_JSON) as f:
        decoys = json.load(f)
    rng = np.random.default_rng(RANDOM_SEED)
    decoy_indices = rng.choice(len(decoys), size=N_DECOYS, replace=False)

    for idx in decoy_indices:
        canon = norm(decoys[idx])
        if canon and canon not in train_smiles:
            train_smiles.append(canon)
            train_labels.append(0)
            train_weights.append(1.0)

    print(f"Added {N_DECOYS} decoys → total training set: {len(train_smiles)} molecules "
          f"(pos={sum(train_labels)}, neg={len(train_labels)-sum(train_labels)})")

    # ── Fine-tune ────────────────────────────────────────────
    ckpt_path = str(OUTPUT_DIR / 'e35_finetune.pt')
    print(f"\nFine-tuning from E34 cycle_7...")
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

    # ── Rank 13 similar molecules on MolFactory pool ──────────
    print(f"\nLoading MolFactory pool for 13-mol ranking...")
    mf_pool_df = pd.read_csv(POOL_CSV)
    pool_smiles = [norm(s) for s in mf_pool_df['smiles'].tolist()]
    pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))
    print(f"Pool: {len(pool_smiles)} unique SMILES")

    mf_id_to_canon = {}
    for i, row in mf_pool_df.iterrows():
        mf_id = str(row['ID'])
        mf_id_to_canon[mf_id] = norm(row['smiles'])

    print(f"Querying fine-tuned model on MolFactory pool...")
    tq = time.time()
    qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
    if not qr.get('ok', False) and 'ranked' not in qr:
        print(f"❌ Query failed: {qr.get('error', str(qr)[:300])}")
        return

    ranked = qr.get('ranked', [])
    n_pool = len(ranked)
    print(f"✅ Ranked {n_pool} molecules in {time.time()-tq:.0f}s")

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
            })

    e35_ranks = [r['glare_rank'] for r in e35_results]
    e35_mean = float(np.mean(e35_ranks))
    e35_median = float(np.median(e35_ranks))
    print(f"\nE35 (post fine-tune): mean=#{e35_mean:.0f} ({100*e35_mean/n_pool:.2f}%), "
          f"median=#{e35_median:.0f}, "
          f"top10%={sum(1 for r in e35_ranks if r <= n_pool*0.10)}, "
          f"top25%={sum(1 for r in e35_ranks if r <= n_pool*0.25)}, "
          f"top50%={sum(1 for r in e35_ranks if r <= n_pool*0.50)}")

    # ── Load E34 pre-fine-tune results ───────────────────────
    with open(E34_RANKING) as f:
        e34_data = json.load(f)
    e34_results = {r['wetlab_id']: r for r in e34_data['results']}
    e34_mean = e34_data['mean_rank']

    # ── Comparison ───────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  E34 (pre) vs E35 (post) Fine-Tune Comparison")
    print(f"{'='*80}")
    print(f"\n  {'WetLab':>10s} {'MolFactory':>16s} {'E34 Pre':>8s} {'E35 Post':>8s} {'Δ':>8s} {'Better':>8s}")
    print(f"  {'─'*65}")

    deltas = []
    for r in e35_results:
        wid = r['wetlab_id']
        pre_rank = e34_results[wid]['glare_rank'] if wid in e34_results else None
        post_rank = r['glare_rank']
        if pre_rank:
            delta = pre_rank - post_rank  # positive = improved
            deltas.append(delta)
            better = '🟢 +' if delta > 0 else ('🔴 ' if delta < 0 else '  =')
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} #{pre_rank:>6d}  #{post_rank:>6d}  {delta:>+7d}  {better}")
        else:
            print(f"  {wid:>10s} {r['molfactory_id']:>16s} {'N/A':>7s}  #{post_rank:>6d}  {'N/A':>7s}")

    n_improved = sum(1 for d in deltas if d > 0)
    n_worse = sum(1 for d in deltas if d < 0)
    print(f"\n  Improved: {n_improved}/13 | Worse: {n_worse}/13 | "
          f"Mean Δ: {np.mean(deltas):+.0f} ranks")

    # ── Save report ──────────────────────────────────────────
    report = {
        'pool_size': int(n_pool),
        'base_checkpoint': E34_CKPT,
        'fine_tuned_checkpoint': ckpt_path,
        'training': {
            'n_wetlab': int((wetlab_df['pDC50']>=6.5).sum() + (wetlab_df['pDC50']<6.0).sum()),
            'n_decoys': N_DECOYS,
            'n_total': len(train_smiles),
            'n_pos': int(sum(train_labels)),
            'n_neg': int(len(train_labels) - sum(train_labels)),
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
        'e35_post': {
            'mean_rank': e35_mean,
            'median_rank': e35_median,
            'top_10pct': int(sum(1 for r in e35_ranks if r <= n_pool * 0.10)),
            'top_25pct': int(sum(1 for r in e35_ranks if r <= n_pool * 0.25)),
            'top_50pct': int(sum(1 for r in e35_ranks if r <= n_pool * 0.50)),
            'results': e35_results,
        },
        'delta_mean_rank': round(e34_mean - e35_mean, 1),
        'n_improved': n_improved,
        'n_worse': n_worse,
    }

    with open(OUTPUT_DIR / 'wetlab_13_ranking_pre_vs_post.json', 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report saved: {OUTPUT_DIR / 'wetlab_13_ranking_pre_vs_post.json'}")

    # ── Quick viz ────────────────────────────────────────────
    plot_pre_vs_post(e35_results, e34_results, e34_mean, e35_mean, n_pool, OUTPUT_DIR)

    print(f"\n✅ E35 Done.")


def plot_pre_vs_post(e35_results, e34_results, e34_mean, e35_mean, n_pool, out_dir):
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        'font.family': 'sans-serif', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 10,
        'figure.dpi': 150, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
        'axes.spines.top': False, 'axes.spines.right': False,
    })

    labels = [r['wetlab_id'] for r in e35_results]
    pre_ranks = [e34_results[l]['glare_rank'] for l in labels]
    post_ranks = [r['glare_rank'] for r in e35_results]

    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.bar(x - width/2, pre_ranks, width, color='#2166AC', alpha=0.85, label=f'E34 Pre (mean=#{e34_mean:.0f})', zorder=3)
    ax.bar(x + width/2, post_ranks, width, color='#D4A017', alpha=0.9, label=f'E35 Post (mean=#{e35_mean:.0f})', zorder=3)

    ax.axhline(e34_mean, color='#2166AC', linestyle='--', alpha=0.4, linewidth=1)
    ax.axhline(e35_mean, color='#D4A017', linestyle='--', alpha=0.6, linewidth=1.5)
    ax.axhline(n_pool * 0.10, color='gray', linestyle=':', alpha=0.3, linewidth=0.8)

    delta = e34_mean - e35_mean
    arrow = '↑' if delta > 0 else '↓'
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('GLARE Rank (lower = better)')
    ax.set_title(f'E35: 13 Wet-Lab Few-Shot Fine-Tune on E34\n'
                 f'Δ mean rank = {delta:+.0f} {arrow} ({100*e35_mean/n_pool:.1f}% vs {100*e34_mean/n_pool:.1f}%)')
    ax.legend(frameon=False, loc='upper right')
    ax.set_ylim(0, max(max(pre_ranks), max(post_ranks)) * 1.15)
    ax.invert_yaxis()

    plt.tight_layout()
    fig.savefig(out_dir / 'fig_e35_pre_vs_post.png', dpi=300)
    fig.savefig(out_dir / 'fig_e35_pre_vs_post.svg')
    plt.close()
    print("  ✅ fig_e35_pre_vs_post.png/.svg")


if __name__ == '__main__':
    main()