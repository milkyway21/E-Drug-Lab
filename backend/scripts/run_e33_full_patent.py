#!/usr/bin/env python3
"""E33 — E32 方法全专利集训练：GRPO selection + Supervised training，303 train / 100 test。

AL 循环: R0(seed=64) → 7 cycles of select→label→retrain → evaluate on test set.
"""
import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem
from sklearn.metrics import roc_auc_score, average_precision_score

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import train, query

# ── Config ──────────────────────────────────────────────────
EXP_NAME = "e33_grpo_sup"
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709')
DATA_DIR = OUTPUT_DIR / 'data'
CKPT_DIR = OUTPUT_DIR / EXP_NAME / 'checkpoints'

# AL params (E32 optimal)
START_NUM = 64
BATCH_SIZE = 64
MAX_SCREEN = 500
N_CYCLES = 7
EPOCHS = 5
LR = 3e-4
ENSEMBLE = 3
STRATEGY = "supervised"  # NOT grpo training

# GRPO selection params
UCB_RATIO = 0.2  # exploration noise ratio (mean + ratio * std)

# Eval thresholds
PDC50_STRONG = 7.0    # strong active label
PDC50_EVAL_LO = 6.5   # eval positive
PDC50_EVAL_HI = 6.0   # eval negative cutoff (>=HI but <LO excluded)

RANDOM_SEED = 42
rng = np.random.default_rng(RANDOM_SEED)

# ── Helpers ──────────────────────────────────────────────────
def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def load_data():
    """Load train/test splits."""
    train_df = pd.read_csv(DATA_DIR / 'patent_train_303.csv')
    test_df = pd.read_csv(DATA_DIR / 'patent_test_100.csv')
    with open(DATA_DIR / 'decoys_10k.json') as f:
        decoys = json.load(f)
    return train_df, test_df, decoys

def build_ranking_pool(train_df, decoy_smiles, test_df):
    """Combine all SMILES into ranking pool. Returns list of dicts with metadata."""
    pool = []
    # Training molecules (with labels)
    for _, row in train_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if canon:
            pool.append({
                'smiles': canon,
                'label': int(row['label_active']),
                'pdc50': float(row['pdc50_raw']),
                'strong': int(row['strong_active']),
                'source': 'train',
                'molecule_id': row['molecule_id'],
            })
    # Decoys (label=0)
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
    # Test molecules
    for _, row in test_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if canon:
            pool.append({
                'smiles': canon,
                'label': int(row['label_active']),
                'pdc50': float(row['pdc50_raw']),
                'strong': int(row['strong_active']),
                'source': 'test',
                'molecule_id': row['molecule_id'],
            })
    return pool

def compute_metrics(ranked_list, pool, test_df):
    """Compute ROC/PRAUC/EF on test set from ranked results."""
    # Build rank map from ranked list
    rank_map = {}
    for r in ranked_list:
        rank_map[norm(r['smiles'])] = {
            'rank': r['glare_rank'],
            'score': r['glare_select_prob'],
        }

    # Get test set predictions
    test_canons = []
    test_labels_eval = []  # for ROC (>=6.5 vs <6.0, exclude [6.0, 6.5))
    test_scores = []
    test_ranks = []
    test_strong_ranks = []

    for _, row in test_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if not canon or canon not in rank_map:
            continue

        pdc50 = float(row['pdc50_raw'])
        entry = rank_map[canon]
        test_ranks.append(entry['rank'])

        # Eval label: >=6.5 → 1, <6.0 → 0, [6.0, 6.5) → exclude
        if pdc50 >= PDC50_EVAL_LO:
            test_labels_eval.append(1)
            test_scores.append(entry['score'])
            test_canons.append(canon)
        elif pdc50 < PDC50_EVAL_HI:
            test_labels_eval.append(0)
            test_scores.append(entry['score'])
            test_canons.append(canon)
        # else: pdc50 in [6.0, 6.5) excluded from ROC

        # Strong active rank tracking
        if int(row['label_active']) == 1:  # pDC50 >= 7.0
            test_strong_ranks.append(entry['rank'])

    n_pool = len(ranked_list)

    # ROC/PRAUC
    roc = None
    prauc = None
    if len(set(test_labels_eval)) >= 2 and len(test_labels_eval) > 0:
        roc = roc_auc_score(test_labels_eval, test_scores)
        prauc = average_precision_score(test_labels_eval, test_scores)

    combined = None
    if roc is not None and prauc is not None and (roc + prauc) > 0:
        combined = 2 * roc * prauc / (roc + prauc)

    # Rank metrics
    rank_strong_mean = float(np.mean(test_strong_ranks)) if test_strong_ranks else None
    rank_all_mean = float(np.mean(test_ranks)) if test_ranks else None

    # EF (enrichment factor): properly compute using eval_active canons
    # Get test eval active canons
    test_eval_active_canons = set()
    test_eval_inactive_canons = set()
    for _, row in test_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if not canon:
            continue
        pdc50 = float(row['pdc50_raw'])
        if pdc50 >= PDC50_EVAL_LO:
            test_eval_active_canons.add(canon)
        elif pdc50 < PDC50_EVAL_HI:
            test_eval_inactive_canons.add(canon)

    n_actives_total = len(test_eval_active_canons)
    n_eval_active = len(test_eval_active_canons)
    ef_metrics = {}
    for pct in [0.01, 0.05, 0.10]:
        cutoff = int(n_pool * pct)
        top_canons = {norm(r['smiles']) for r in ranked_list[:cutoff]}
        actives_found = len(top_canons & test_eval_active_canons)
        expected = n_actives_total * pct
        ef = actives_found / expected if expected > 0 else 0.0
        ef_metrics[f'ef_{int(pct*100)}pct'] = round(ef, 2)
        ef_metrics[f'actives_{int(pct*100)}pct'] = actives_found

    return {
        'roc': round(roc, 4) if roc is not None else None,
        'prauc': round(prauc, 4) if prauc is not None else None,
        'combined': round(combined, 4) if combined is not None else None,
        'rank_strong': round(rank_strong_mean, 1) if rank_strong_mean is not None else None,
        'rank_all': round(rank_all_mean, 1) if rank_all_mean is not None else None,
        'n_eval_total': len(test_labels_eval),
        'n_eval_active': n_eval_active,
        'n_actives_total': n_actives_total,
        **ef_metrics,
    }

def grpo_select(ranked, labeled_canons, n_select, train_canons, ucb_ratio=UCB_RATIO):
    """GRPO-style selection: UCB (mean + ratio * std) on select_prob.
    Only selects from training pool molecules (has labels to reveal).
    """
    candidates = []
    for r in ranked:
        canon = norm(r['smiles'])
        # Only select from training pool, skip already labeled
        if canon in labeled_canons or canon not in train_canons:
            continue
        score = r.get('glare_select_prob', 0.0)
        unc = r.get('glare_uncertainty', 0.0)
        # UCB: add scaled uncertainty for exploration
        noise = rng.normal(0, 1) * unc * ucb_ratio
        ucb_score = score + noise
        candidates.append((canon, ucb_score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = [c[0] for c in candidates[:n_select]]
    return selected

def determine_pass(r0_roc, rf_roc, r0_rank_strong, rf_rank_strong):
    """PASS = (ΔRank_strong < 0) AND (ΔROC >= -0.03)."""
    delta_roc = rf_roc - r0_roc if (r0_roc is not None and rf_roc is not None) else -999
    delta_rank = rf_rank_strong - r0_rank_strong if (r0_rank_strong is not None and rf_rank_strong is not None) else 999
    success_rank = delta_rank < 0
    success_roc = delta_roc >= -0.03
    return bool(success_rank and success_roc), {
        'delta_roc': round(delta_roc, 4),
        'delta_rank_strong': round(delta_rank, 1),
        'success_rank_improved': success_rank,
        'success_roc_preserved': success_roc,
    }

# ── Main ──────────────────────────────────────────────────────
def main():
    print("=" * 80)
    print("  E33 — GLARE Full Patent Training (E32 method)")
    print("  Config: GRPO selection + Supervised training")
    print(f"  Train: 303 | Test: 100 | Decoys: 10,000")
    print(f"  Cycles: {N_CYCLES} | Epochs: {EPOCHS} | LR: {LR}")
    print("=" * 80)

    # Load data
    train_df, test_df, decoy_smiles = load_data()
    print(f"\nLoaded: train={len(train_df)}, test={len(test_df)}, decoys={len(decoy_smiles)}")

    # Build ranking pool
    pool = build_ranking_pool(train_df, decoy_smiles, test_df)
    pool_smiles = [p['smiles'] for p in pool]
    pool_canon_map = {}  # canon → pool index
    for i, p in enumerate(pool):
        pool_canon_map[p['smiles']] = i
    print(f"Ranking pool: {len(pool)} molecules")

    # Build train_canons set for selection filtering
    train_canons = set()
    for _, row in train_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if canon:
            train_canons.add(canon)
    print(f"Train canons: {len(train_canons)}")

    # Initialize labeled set: seed with active molecules
    train_actives = train_df[train_df['label_active'] == 1]
    train_inactives = train_df[train_df['label_active'] == 0]
    train_weak = train_df[train_df['label_active'] == -1]

    n_seed_actives = min(1, len(train_actives))  # 1 active for seed
    n_seed_rest = START_NUM - n_seed_actives

    seed_actives = train_actives.sample(n=n_seed_actives, random_state=RANDOM_SEED)
    # Fill rest from inactives + weak + remaining actives
    rest_pool = pd.concat([
        train_inactives,
        train_weak,
        train_actives.drop(seed_actives.index) if n_seed_actives < len(train_actives) else train_actives.iloc[0:0],
    ])
    seed_rest = rest_pool.sample(n=min(n_seed_rest, len(rest_pool)), random_state=RANDOM_SEED)
    seed_df = pd.concat([seed_actives, seed_rest])

    labeled_canons = set()
    labeled_data = []  # List of {"smiles": canon, "label": int, "weight": float}
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
          f"(actives={(sum(1 for d in labeled_data if d['label']==1))}, "
          f"inactives={(sum(1 for d in labeled_data if d['label']==0))})")

    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    cycles_log = []
    prev_ckpt = None

    for cycle in range(N_CYCLES + 1):  # 0..7
        t0 = time.time()
        print(f"\n{'─'*60}")
        print(f"  Cycle {cycle}/{N_CYCLES} — Labeled: {len(labeled_data)}")

        # Train
        ckpt_path = str(CKPT_DIR / f'cycle_{cycle}.pt')
        train_smiles = [d['smiles'] for d in labeled_data]
        train_labels = [d['label'] for d in labeled_data]
        train_weights = [d['weight'] for d in labeled_data]

        print(f"  Training on {len(train_smiles)} molecules "
              f"(pos={sum(train_labels)}, neg={len(train_labels)-sum(train_labels)})...")

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

        # Query ranking pool
        print(f"  Querying ranking pool ({len(pool_smiles)} molecules)...")
        tq = time.time()
        qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
        if not qr.get('ok', False) and 'ranked' not in qr:
            print(f"  ❌ Query failed: {qr.get('error', str(qr)[:300])}")
            break
        ranked = qr.get('ranked', [])
        print(f"  ✅ Ranked {len(ranked)} molecules in {time.time()-tq:.0f}s")

        # Compute metrics on test set
        metrics = compute_metrics(ranked, pool, test_df)
        n_pos = sum(1 for d in labeled_data if d['label'] == 1)
        n_neg = sum(1 for d in labeled_data if d['label'] == 0)

        cycle_entry = {
            'cycle': cycle,
            'roc': metrics['roc'],
            'prauc': metrics.get('prauc'),
            'combined': metrics.get('combined'),
            'rank_strong': metrics['rank_strong'],
            'rank_all': metrics['rank_all'],
            'ef_1pct': metrics.get('ef_1pct'),
            'actives_1pct': metrics.get('actives_1pct'),
            'ef_5pct': metrics.get('ef_5pct'),
            'actives_5pct': metrics.get('actives_5pct'),
            'ef_10pct': metrics.get('ef_10pct'),
            'actives_10pct': metrics.get('actives_10pct'),
            'n_ranking_pool': len(ranked),
            'n_actives_total': metrics.get('n_actives_total'),
            'train_n': len(labeled_data),
            'train_pos': n_pos,
            'train_neg': n_neg,
            'loss': loss,
        }
        cycles_log.append(cycle_entry)
        print(f"  ROC={metrics['roc']}, rank_strong={metrics['rank_strong']}, "
              f"EF_1%={metrics.get('ef_1pct')}")

        prev_ckpt = ckpt_path

        # Selection for next cycle (skip after final cycle)
        if cycle < N_CYCLES:
            selected = grpo_select(ranked, labeled_canons, BATCH_SIZE, train_canons)
            n_new_actives = 0
            for smi in selected:
                if smi in pool_canon_map:
                    idx = pool_canon_map[smi]
                    p = pool[idx]
                    if p['source'] == 'train':
                        lbl = 1 if p['label'] == 1 else 0
                        w = 1.2 if p['strong'] == 1 else (1.0 if p['label'] == 1 else (0.5 if p['label'] == -1 else 1.0))
                        if lbl == 1:
                            n_new_actives += 1
                    else:
                        lbl = 0  # decoy
                        w = 1.0
                else:
                    lbl = 0
                    w = 1.0
                labeled_canons.add(smi)
                labeled_data.append({'smiles': smi, 'label': lbl, 'weight': w})

            print(f"  Selected {len(selected)} new molecules ({n_new_actives} actives)")

    # ── Summary ──────────────────────────────────────────────
    if len(cycles_log) >= 2:
        r0 = cycles_log[0]
        rf = cycles_log[-1]
        passed, pass_detail = determine_pass(
            r0.get('roc'), rf.get('roc'),
            r0.get('rank_strong'), rf.get('rank_strong'),
        )
    else:
        passed = False
        pass_detail = {}

    summary = {
        'name': EXP_NAME,
        'gpu': 5,
        'experiment': 'E33',
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
            'desc': 'E32 method (GRPO select + Supervised train) on full patent 303/100 split',
        },
        'pool_stats': {
            'total': len(pool),
            'n_train': len(train_df),
            'n_test': len(test_df),
            'n_decoys': len(decoy_smiles),
        },
        'final_state': {
            'n_labeled': len(labeled_data) if cycles_log else 0,
            'n_cycles_completed': len(cycles_log) - 1 if cycles_log else 0,
        },
        'cycles': cycles_log,
        'summary': {},
    }

    if len(cycles_log) >= 2:
        r0 = cycles_log[0]
        rf = cycles_log[-1]
        summary['summary'] = {
            'r0_roc': r0.get('roc'),
            'rf_roc': rf.get('roc'),
            'r0_prauc': r0.get('prauc'),
            'rf_prauc': rf.get('prauc'),
            'r0_combined': r0.get('combined'),
            'rf_combined': rf.get('combined'),
            'r0_rank_strong': r0.get('rank_strong'),
            'rf_rank_strong': rf.get('rank_strong'),
            'r0_rank_all': r0.get('rank_all'),
            'rf_rank_all': rf.get('rank_all'),
            **pass_detail,
            'PASS': passed,
            'prauc_threshold': f'pDC50 >= {PDC50_EVAL_LO}',
        }

    with open(OUTPUT_DIR / EXP_NAME / 'summary.json', 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Save cycle metrics CSV
    if cycles_log:
        df_metrics = pd.DataFrame(cycles_log)
        df_metrics.to_csv(OUTPUT_DIR / EXP_NAME / 'cycle_metrics.csv', index=False)

    print(f"\n{'='*80}")
    print(f"  E33 Complete!")
    if len(cycles_log) >= 2:
        print(f"  R0 ROC={r0.get('roc'):.4f} → Rf ROC={rf.get('roc'):.4f}")
        print(f"  ΔROC={pass_detail.get('delta_roc', 'N/A')}")
        print(f"  ΔRank_strong={pass_detail.get('delta_rank_strong', 'N/A')}")
        print(f"  PASS={passed}")
    print(f"  Output: {OUTPUT_DIR / EXP_NAME}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
