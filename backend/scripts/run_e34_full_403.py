#!/usr/bin/env python3
"""E34 — E32 方法全量 403 专利训练：GRPO selection + Supervised training。
全部 403 分子用于 AL 训练，无 train/test 拆分。每轮评估 13 相似分子排名。
"""
import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import train, query

# ── Config ──────────────────────────────────────────────────
EXP_NAME = "e34_grpo_sup"
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403')
E33_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709')
DATA_DIR = OUTPUT_DIR / 'data'
CKPT_DIR = OUTPUT_DIR / EXP_NAME / 'checkpoints'

PATENT_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv'
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'

# AL params (E32 optimal)
START_NUM = 64
BATCH_SIZE = 64
MAX_SCREEN = 500
N_CYCLES = 7
EPOCHS = 5
LR = 3e-4
ENSEMBLE = 3
STRATEGY = "supervised"
UCB_RATIO = 0.2

# Eval thresholds
PDC50_STRONG = 7.0
PDC50_EVAL_LO = 6.5
PDC50_EVAL_HI = 6.0

RANDOM_SEED = 42
rng = np.random.default_rng(RANDOM_SEED)

# 13 Wet-Lab → MolFactory mapping
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

def load_data():
    """Load ALL 403 patent molecules + decoys."""
    patent_df = pd.read_csv(PATENT_CSV)
    print(f"Loaded patent: {len(patent_df)} molecules "
          f"(active={int((patent_df['label_active']==1).sum())}, "
          f"inactive={int((patent_df['label_active']==0).sum())}, "
          f"weak={int((patent_df['label_active']==-1).sum())})")

    with open(E33_DIR / 'data' / 'decoys_10k.json') as f:
        decoys = json.load(f)
    return patent_df, decoys

def build_ranking_pool(patent_df, decoy_smiles):
    """Combine patent + decoys into ranking pool."""
    pool = []
    for _, row in patent_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if canon:
            pool.append({
                'smiles': canon,
                'label': int(row['label_active']),
                'pdc50': float(row['pdc50_raw']),
                'strong': int(row['strong_active']),
                'source': 'patent',
                'molecule_id': row['molecule_id'],
            })
    for smi in decoy_smiles:
        canon = norm(smi)
        if canon:
            pool.append({
                'smiles': canon,
                'label': 0,
                'pdc50': 0.0,
                'strong': 0,
                'source': 'decoy',
                'molecule_id': '',
            })
    return pool

def compute_self_eval(ranked_list, pool):
    """Self-eval: rank_strong and rank_all403 within ranking pool."""
    rank_map = {}
    for r in ranked_list:
        rank_map[norm(r['smiles'])] = {
            'rank': r['glare_rank'],
            'score': r['glare_select_prob'],
        }

    strong_ranks = []
    all_ranks = []
    for p in pool:
        if p['source'] != 'patent':
            continue
        entry = rank_map.get(p['smiles'])
        if not entry:
            continue
        all_ranks.append(entry['rank'])
        if p['strong'] == 1:
            strong_ranks.append(entry['rank'])

    return {
        'rank_strong': round(float(np.mean(strong_ranks)), 1) if strong_ranks else None,
        'rank_all403': round(float(np.mean(all_ranks)), 1) if all_ranks else None,
        'n_strong': len(strong_ranks),
        'n_all': len(all_ranks),
    }

def compute_13mol_ranking(ckpt_path, pool_df, mf_id_to_canon):
    """Query 10K MolFactory pool, compute 13 similar molecules mean rank."""
    pool_smiles = [norm(s) for s in pool_df['smiles'].tolist()]
    pool_smiles = list(dict.fromkeys([s for s in pool_smiles if s]))

    qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
    if not qr.get('ok', False) and 'ranked' not in qr:
        return None, f"Query failed: {qr.get('error', str(qr)[:200])}"

    ranked = qr.get('ranked', [])
    n_pool = len(ranked)

    rank_map = {}
    for r in ranked:
        rank_map[norm(r['smiles'])] = {
            'rank': r['glare_rank'],
            'score': r['glare_select_prob'],
        }

    results = []
    for wetlab_id, mf_id, tanimoto in WETLAB_MAP:
        canon = mf_id_to_canon.get(mf_id)
        if not canon:
            continue
        entry = rank_map.get(canon)
        if entry:
            results.append({
                'wetlab_id': wetlab_id,
                'molfactory_id': f'MolFactory_{mf_id}',
                'tanimoto': tanimoto,
                'glare_rank': entry['rank'],
                'glare_score': round(entry['score'], 6),
                'glare_pct': round(100 * entry['rank'] / n_pool, 2),
                'carsi_rank': int(pool_df[pool_df['ID'].astype(str) == mf_id].index[0] + 1)
                    if mf_id in pool_df['ID'].astype(str).values else None,
            })

    if not results:
        return None, "No matches found"

    ranks = [r['glare_rank'] for r in results if r['glare_rank']]
    return {
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
    }, None

def grpo_select(ranked, labeled_canons, n_select, train_canons, ucb_ratio=UCB_RATIO):
    """GRPO-style selection: UCB on select_prob, only from training pool."""
    candidates = []
    for r in ranked:
        canon = norm(r['smiles'])
        if canon in labeled_canons or canon not in train_canons:
            continue
        score = r.get('glare_select_prob', 0.0)
        unc = r.get('glare_uncertainty', 0.0)
        noise = rng.normal(0, 1) * unc * ucb_ratio
        ucb_score = score + noise
        candidates.append((canon, ucb_score))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:n_select]]

# ── Main ──────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("  E34 — GLARE Full 403 Patent Training (E32 method)")
    print("  Config: GRPO selection + Supervised training")
    print(f"  Train: ALL 403 patent | Decoys: 10,000")
    print(f"  Cycles: {N_CYCLES} | Epochs: {EPOCHS} | LR: {LR}")
    print("=" * 80)

    # ── Setup dirs ───────────────────────────────────────────
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data ────────────────────────────────────────────
    patent_df, decoy_smiles = load_data()

    # Build ranking pool (AL training)
    pool = build_ranking_pool(patent_df, decoy_smiles)
    pool_smiles = [p['smiles'] for p in pool]
    pool_canon_map = {p['smiles']: i for i, p in enumerate(pool)}
    print(f"Ranking pool: {len(pool)} molecules ({len(pool_smiles)} unique)")

    # Build train_canons set for selection filtering
    train_canons = set()
    for _, row in patent_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if canon:
            train_canons.add(canon)
    print(f"Train canons: {len(train_canons)}")

    # ── Load MolFactory pool for 13-mol ranking ──────────────
    print(f"\nLoading MolFactory pool for 13-mol evaluation...")
    mf_pool_df = pd.read_csv(POOL_CSV)
    mf_id_to_canon = {}
    for i, row in mf_pool_df.iterrows():
        mf_id = str(row['ID'])
        mf_id_to_canon[mf_id] = norm(row['smiles'])
    print(f"MolFactory pool: {len(mf_pool_df)} molecules")

    # ── Seed ─────────────────────────────────────────────────
    patent_actives = patent_df[patent_df['label_active'] == 1]
    patent_inactives = patent_df[patent_df['label_active'] == 0]
    patent_weak = patent_df[patent_df['label_active'] == -1]

    n_seed_actives = min(1, len(patent_actives))
    n_seed_rest = START_NUM - n_seed_actives

    seed_actives = patent_actives.sample(n=n_seed_actives, random_state=RANDOM_SEED)
    rest_pool_df = pd.concat([
        patent_inactives,
        patent_weak,
        patent_actives.drop(seed_actives.index) if n_seed_actives < len(patent_actives) else patent_actives.iloc[0:0],
    ])
    seed_rest = rest_pool_df.sample(n=min(n_seed_rest, len(rest_pool_df)), random_state=RANDOM_SEED)
    seed_df = pd.concat([seed_actives, seed_rest])

    labeled_canons = set()
    labeled_data = []
    for _, row in seed_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if canon:
            labeled_canons.add(canon)
            labeled_data.append({
                'smiles': canon,
                'label': 1 if int(row['label_active']) == 1 else 0,
                'weight': float(row['sample_weight']),
            })

    print(f"\nSeed: {len(labeled_data)} labeled "
          f"(actives={sum(1 for d in labeled_data if d['label']==1)}, "
          f"inactives={sum(1 for d in labeled_data if d['label']==0)})")

    # ── AL Loop ──────────────────────────────────────────────
    cycles_log = []
    cycle_13mol_log = []
    prev_ckpt = None

    for cycle in range(N_CYCLES + 1):
        t0 = time.time()
        print(f"\n{'─'*60}")
        print(f"  Cycle {cycle}/{N_CYCLES} — Labeled: {len(labeled_data)}/{len(patent_df)}")

        # Train
        ckpt_path = str(CKPT_DIR / f'cycle_{cycle}.pt')
        train_smiles = [d['smiles'] for d in labeled_data]
        train_labels = [d['label'] for d in labeled_data]
        train_weights = [d['weight'] for d in labeled_data]

        n_pos = sum(train_labels)
        print(f"  Training on {len(train_smiles)} molecules (pos={n_pos}, neg={len(train_smiles)-n_pos})...")

        result = train(
            checkpoint_path=ckpt_path,
            train_smiles=train_smiles,
            train_labels=train_labels,
            sample_weights=train_weights,
            prev_checkpoint=prev_ckpt,
            epochs=EPOCHS,
            ensemble_size=ENSEMBLE,
            lr=LR,
            strategy=STRATEGY,
        )

        if not result.get('ok', False):
            print(f"  ❌ Train failed: {result.get('error', str(result)[:300])}")
            break

        loss = result.get('final_loss', None)
        print(f"  ✅ Trained in {time.time()-t0:.0f}s, loss={loss}")

        # Query AL ranking pool
        print(f"  Querying AL ranking pool ({len(pool_smiles)} molecules)...")
        tq = time.time()
        qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
        if not qr.get('ok', False) and 'ranked' not in qr:
            print(f"  ❌ Query failed: {qr.get('error', str(qr)[:300])}")
            break
        ranked = qr.get('ranked', [])
        print(f"  ✅ Ranked {len(ranked)} molecules in {time.time()-tq:.0f}s")

        # Self-eval metrics
        self_eval = compute_self_eval(ranked, pool)
        print(f"  Self-eval: rank_strong={self_eval['rank_strong']}, "
              f"rank_all403={self_eval['rank_all403']}")

        # 13-mol ranking on MolFactory pool
        print(f"  Querying MolFactory pool for 13-mol ranking...")
        t13 = time.time()
        mf_result, mf_error = compute_13mol_ranking(ckpt_path, mf_pool_df, mf_id_to_canon)
        if mf_result:
            print(f"  ✅ 13-mol: mean_rank={mf_result['mean_rank']:.1f} "
                  f"(top {mf_result['mean_pct']:.2f}%), "
                  f"top10%={mf_result['top_10pct']}, top25%={mf_result['top_25pct']}, "
                  f"top50%={mf_result['top_50pct']} "
                  f"({time.time()-t13:.0f}s)")
            cycle_13mol_log.append({'cycle': cycle, **mf_result})
        else:
            print(f"  ⚠️ 13-mol ranking: {mf_error}")

        cycles_log.append({
            'cycle': cycle,
            'rank_strong': self_eval['rank_strong'],
            'rank_all403': self_eval['rank_all403'],
            'n_strong': int(self_eval['n_strong']),
            'n_all': int(self_eval['n_all']),
            'n_ranking_pool': int(len(ranked)),
            'train_n': int(len(labeled_data)),
            'train_pos': int(n_pos),
            'train_neg': int(len(labeled_data) - n_pos),
            'loss': loss,
            'molfactory_13mol_mean_rank': float(mf_result['mean_rank']) if mf_result else None,
            'molfactory_13mol_mean_pct': float(mf_result['mean_pct']) if mf_result else None,
            'molfactory_13mol_top10pct': int(mf_result['top_10pct']) if mf_result else None,
            'molfactory_13mol_top25pct': int(mf_result['top_25pct']) if mf_result else None,
            'molfactory_13mol_top50pct': int(mf_result['top_50pct']) if mf_result else None,
        })

        prev_ckpt = ckpt_path

        # Selection for next cycle
        if cycle < N_CYCLES:
            remaining = len(train_canons) - len(labeled_canons)
            if remaining == 0:
                print(f"  ⚠️ AL pool exhausted! All {len(train_canons)} molecules labeled. "
                      f"Continuing to train on full data.")
                continue

            n_select = min(BATCH_SIZE, remaining)
            selected = grpo_select(ranked, labeled_canons, n_select, train_canons)
            n_new_actives = 0
            for smi in selected:
                if smi in pool_canon_map:
                    idx = pool_canon_map[smi]
                    p = pool[idx]
                    if p['source'] == 'patent':
                        lbl = 1 if p['label'] == 1 else 0
                        w = 1.2 if p['strong'] == 1 else (1.0 if p['label'] == 1 else (0.5 if p['label'] == -1 else 1.0))
                        if lbl == 1:
                            n_new_actives += 1
                    else:
                        lbl = 0; w = 1.0
                else:
                    lbl = 0; w = 1.0
                labeled_canons.add(smi)
                labeled_data.append({'smiles': smi, 'label': lbl, 'weight': w})

            print(f"  Selected {len(selected)} new molecules ({n_new_actives} actives), "
                  f"remaining: {len(train_canons) - len(labeled_canons)}")

    # ── Summary ──────────────────────────────────────────────
    summary = {
        'name': EXP_NAME,
        'gpu': 5,
        'experiment': 'E34',
        'config': {
            'select': 'grpo',
            'train_strategy': STRATEGY,
            'start_num': START_NUM,
            'batch_size': BATCH_SIZE,
            'max_screen': MAX_SCREEN,
            'n_cycles': N_CYCLES,
            'epochs': EPOCHS,
            'lr': LR,
            'ensemble': ENSEMBLE,
            'ucb_ratio': UCB_RATIO,
            'desc': 'E32 method on ALL 403 patent molecules (no test split), 13-mol external eval',
        },
        'pool_stats': {
            'total': len(pool),
            'n_patent': len(patent_df),
            'n_decoys': len(decoy_smiles),
        },
        'final_state': {
            'n_labeled': len(labeled_data),
            'n_cycles_completed': len(cycles_log) - 1 if cycles_log else 0,
        },
        'cycles': cycles_log,
        'cycle_13mol_ranking': cycle_13mol_log,
        'summary': {},
    }

    if len(cycles_log) >= 2:
        r0 = cycles_log[0]
        rf = cycles_log[-1]
        summary['summary'] = {
            'r0_rank_strong': r0.get('rank_strong'),
            'rf_rank_strong': rf.get('rank_strong'),
            'r0_rank_all403': r0.get('rank_all403'),
            'rf_rank_all403': rf.get('rank_all403'),
            'delta_rank_strong': round(rf.get('rank_strong', 0) - r0.get('rank_strong', 0), 1),
            'delta_rank_all403': round(rf.get('rank_all403', 0) - r0.get('rank_all403', 0), 1),
            'r0_13mol_mean_rank': r0.get('molfactory_13mol_mean_rank'),
            'rf_13mol_mean_rank': rf.get('molfactory_13mol_mean_rank'),
            'r0_13mol_mean_pct': r0.get('molfactory_13mol_mean_pct'),
            'rf_13mol_mean_pct': rf.get('molfactory_13mol_mean_pct'),
        }

    # Save summary
    with open(OUTPUT_DIR / EXP_NAME / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Summary saved: {OUTPUT_DIR / EXP_NAME / 'summary.json'}")

    # Save cycle_13mol_ranking
    with open(OUTPUT_DIR / EXP_NAME / 'cycle_13mol_ranking.json', 'w') as f:
        json.dump(cycle_13mol_log, f, indent=2, ensure_ascii=False)
    print(f"✅ 13mol ranking history saved")

    # ── Final 13-mol report with best checkpoint ─────────────
    if cycle_13mol_log:
        # Find best by mean_rank
        best = min(cycle_13mol_log, key=lambda x: x['mean_rank'])
        print(f"\n{'='*80}")
        print(f"  Best 13-mol ranking: cycle {best['cycle']}, "
              f"mean_rank={best['mean_rank']:.1f} (top {best['mean_pct']:.2f}%)")
        print(f"{'='*80}")
        for r in best['results']:
            print(f"  {r['wetlab_id']:>10s} → {r['molfactory_id']:>16s}  "
                  f"GLARE=#{r['glare_rank']:>5d} ({r['glare_pct']:.1f}%)  "
                  f"Carsi=#{r['carsi_rank']:>5d}")

        best_report = {
            'pool_size': best['n_pool'],
            'best_cycle': best['cycle'],
            'checkpoint': str(CKPT_DIR / f'cycle_{best["cycle"]}.pt'),
            'mean_rank': best['mean_rank'],
            'median_rank': best['median_rank'],
            'best_rank': best['best_rank'],
            'worst_rank': best['worst_rank'],
            'mean_pct': best['mean_pct'],
            'top_10pct': best['top_10pct'],
            'top_25pct': best['top_25pct'],
            'top_50pct': best['top_50pct'],
            'results': best['results'],
        }
        with open(OUTPUT_DIR / 'wetlab_13_similar_ranking.json', 'w') as f:
            json.dump(best_report, f, indent=2, ensure_ascii=False)
        print(f"✅ Final report saved: {OUTPUT_DIR / 'wetlab_13_similar_ranking.json'}")

    print(f"\n✅ E34 Done.")


if __name__ == '__main__':
    main()