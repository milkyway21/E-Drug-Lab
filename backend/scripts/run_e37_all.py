#!/usr/bin/env python3
"""E37 — 10 种训练方案：基于 E36 成功经验 + 论文方法。

所有方案用 13 round-1 wet-lab 分子训练，评估 19 round-2 分子在 MolFactory 0711 池中的排名。
E34 baseline: 19mol mean #6583, E36 baseline: #6233
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

# ── Paths ───────────────────────────────────────────────────
E34_CKPT = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403/e34_grpo_sup/checkpoints/cycle_7.pt'
E36_CKPT = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e36_full_patent_plus_wetlab/e36_full.pt'
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e37_transfer')
SDF_DIR_R1 = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第一轮分子生成15个实体分子'
SDF_DIR_R2 = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第二轮动力学指导的分子生成'
DECOY_JSON = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709/data/decoys_10k.json'
POOL_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/MolFactory_0711_merged.csv'
PATENT_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv'
E34_RANKING = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/round2_dynamics_ranking/e34_vs_e36_round2_dynamics.json'
WETLAB_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv'

ENSEMBLE = 3
RANDOM_SEED = 42
POSITIVE_IDS = {'0228390', '0228414', 'LXC-106'}

# ── Helpers ──────────────────────────────────────────────────
def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def extract_smiles_from_sdf(sdf_path):
    suppl = Chem.SDMolSupplier(sdf_path)
    if not suppl or len(suppl) == 0: return None
    mol = suppl[0]
    return Chem.MolToSmiles(mol) if mol else None

def load_wetlab_13():
    """Load 13 round-1 wet-lab molecules (SDF first, CSV fallback)."""
    smi_map = {}
    wetlab_df = pd.read_csv(WETLAB_CSV)
    for _, row in wetlab_df.iterrows():
        smi_map[str(row['SDF_ID'])] = str(row['SMILES'])

    smiles, labels, weights = [], [], []
    for fname in sorted(os.listdir(SDF_DIR_R1)):
        if not fname.endswith('.sdf'): continue
        sid = fname.replace('.sdf', '')
        canon = extract_smiles_from_sdf(os.path.join(SDF_DIR_R1, fname))
        if canon is None:
            csv_smi = smi_map.get(sid)
            if csv_smi: canon = norm(csv_smi)
            else: continue
        is_pos = sid in POSITIVE_IDS
        smiles.append(canon)
        labels.append(1 if is_pos else 0)
        weights.append(5.0 if is_pos else 1.0)
    return smiles, labels, weights

def load_patent_403():
    """Load 403 patent molecules with original labels/weights."""
    patent_df = pd.read_csv(PATENT_CSV)
    smiles, labels, weights = [], [], []
    for _, row in patent_df.iterrows():
        canon = norm(row['canonical_smiles'])
        if not canon: continue
        la = int(row['label_active'])
        smiles.append(canon)
        labels.append(1 if la == 1 else 0)
        weights.append(float(row['sample_weight']))
    return smiles, labels, weights

def load_patent_balanced(n_pos_target=100):
    """Load patent with positive samples downsampled."""
    patent_df = pd.read_csv(PATENT_CSV)
    pos_rows = patent_df[patent_df['label_active'] == 1]
    neg_rows = patent_df[patent_df['label_active'] != 1]
    rng = np.random.default_rng(RANDOM_SEED)
    pos_sampled = pos_rows.iloc[rng.choice(len(pos_rows), size=min(n_pos_target, len(pos_rows)), replace=False)]
    combined = pd.concat([pos_sampled, neg_rows])
    smiles, labels, weights = [], [], []
    for _, row in combined.iterrows():
        canon = norm(row['canonical_smiles'])
        if not canon: continue
        la = int(row['label_active'])
        smiles.append(canon)
        labels.append(1 if la == 1 else 0)
        weights.append(float(row['sample_weight']))
    return smiles, labels, weights

def load_decoys(n, existing_smiles, rng):
    with open(DECOY_JSON) as f:
        decoys = json.load(f)
    idxs = rng.choice(len(decoys), size=n, replace=False)
    added = []
    for i in idxs:
        canon = norm(decoys[i])
        if canon and canon not in existing_smiles:
            added.append(canon)
            existing_smiles.add(canon)
    return added

def load_r2_query_smiles():
    """Load 19 round-2 molecule SMILES for query."""
    mols = []
    for fname in sorted(os.listdir(SDF_DIR_R2)):
        if not fname.endswith('.sdf'): continue
        sid = fname.replace('.sdf', '')
        canon = extract_smiles_from_sdf(os.path.join(SDF_DIR_R2, fname))
        if canon:
            mols.append({'id': sid, 'smiles': canon})
    return mols

def rank_and_eval(ckpt_path, label, r2_mols, pool_csv):
    """Query GLARE on pool + r2 molecules, return r2 rankings."""
    pool_df = pd.read_csv(pool_csv)
    pool_smiles = [norm(s) for s in pool_df['smiles'].tolist()]
    pool_smiles = [s for s in pool_smiles if s]

    r2_smiles_set = set(m['smiles'] for m in r2_mols)
    all_smiles = list(dict.fromkeys(pool_smiles + list(r2_smiles_set)))

    print(f"  [{label}] Querying {len(all_smiles)} molecules...")
    t0 = time.time()
    qr = query(ckpt_path, all_smiles, ensemble_size=ENSEMBLE)
    elapsed = time.time() - t0
    if not qr.get('ok', False) and 'ranked' not in qr:
        print(f"    ❌ Failed: {qr.get('error', str(qr)[:200])}")
        return None
    ranked = qr.get('ranked', [])
    print(f"    ✅ {len(ranked)} ranked in {elapsed:.0f}s")

    rank_map = {}
    for r in ranked:
        rank_map[norm(r['smiles'])] = int(r['glare_rank'])

    results = []
    for m in r2_mols:
        rank = rank_map.get(m['smiles'])
        results.append({
            'mol_id': m['id'], 'glare_rank': rank,
            'glare_pct': round(100*rank/len(all_smiles), 2) if rank else None,
        })
    ranks = [r['glare_rank'] for r in results if r['glare_rank'] is not None]
    return {
        'results': results,
        'mean_rank': float(np.mean(ranks)) if ranks else None,
        'median_rank': float(np.median(ranks)) if ranks else None,
        'n_pool': len(all_smiles),
        'query_time': elapsed,
    }

# ── Main ─────────────────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(RANDOM_SEED)

    print("=" * 80)
    print("  E37 — 10 Training Schemes: 13 Wet-Lab → 19 Round-2 Transfer")
    print("=" * 80)

    # ── Load shared data ──────────────────────────────────────
    w13_smi, w13_lab, w13_wgt = load_wetlab_13()
    n_wpos = sum(w13_lab)
    print(f"\nWet-lab 13: {len(w13_smi)} mols (pos={n_wpos}, neg={len(w13_smi)-n_wpos})")

    p403_smi, p403_lab, p403_wgt = load_patent_403()
    n_ppos = sum(p403_lab)
    print(f"Patent 403: {len(p403_smi)} mols (pos={n_ppos}, neg={len(p403_smi)-n_ppos})")

    pbal_smi, pbal_lab, pbal_wgt = load_patent_balanced(100)
    n_pbpos = sum(pbal_lab)
    print(f"Patent Balanced: {len(pbal_smi)} mols (pos={n_pbpos}, neg={len(pbal_smi)-n_pbpos})")

    r2_mols = load_r2_query_smiles()
    print(f"Round-2 query: {len(r2_mols)} molecules")

    all_schemes = {}

    # ═══════════════════════════════════════════════════════════
    # Group A: From-Scratch (E37a/b/c/j)
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print("  Group A: From-Scratch Training")
    print(f"{'='*60}")

    # E37a = E36 (already done)
    print("\n--- E37a: E36 Reproduce (use existing checkpoint) ---")
    e37a_eval = rank_and_eval(E36_CKPT, "E37a=E36", r2_mols, POOL_CSV)
    all_schemes['E37a'] = {
        'label': 'E36 Reproduce (from scratch, 403+13, sup, pos_w=5.0)',
        'checkpoint': E36_CKPT, 'eval': e37a_eval,
        'paradigm': 'from_scratch', 'group': 'A',
    }

    # E37b: GRPO from scratch
    print("\n--- E37b: GRPO from Scratch ---")
    smi_b = p403_smi + w13_smi
    lab_b = p403_lab + w13_lab
    wgt_b = p403_wgt + w13_wgt
    ckpt_b = str(OUTPUT_DIR / 'e37b_grpo.pt')
    t0 = time.time()
    r_b = train(ckpt_b, smi_b, lab_b, wgt_b, prev_checkpoint=None,
                epochs=50, lr=3e-4, ensemble_size=ENSEMBLE, strategy="grpo")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_b.get('final_loss')}")
    e37b_eval = rank_and_eval(ckpt_b, "E37b", r2_mols, POOL_CSV) if r_b.get('ok') else None
    all_schemes['E37b'] = {
        'label': 'GRPO from Scratch (403+13, grpo, ep=50)',
        'checkpoint': ckpt_b, 'eval': e37b_eval,
        'paradigm': 'from_scratch', 'group': 'A',
    }

    # E37c: Balanced Patent
    print("\n--- E37c: Balanced Patent + 13 Wet-Lab ---")
    smi_c = pbal_smi + w13_smi
    lab_c = pbal_lab + w13_lab
    wgt_c = pbal_wgt + w13_wgt
    ckpt_c = str(OUTPUT_DIR / 'e37c_balanced.pt')
    t0 = time.time()
    r_c = train(ckpt_c, smi_c, lab_c, wgt_c, prev_checkpoint=None,
                epochs=50, lr=3e-4, ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_c.get('final_loss')}")
    e37c_eval = rank_and_eval(ckpt_c, "E37c", r2_mols, POOL_CSV) if r_c.get('ok') else None
    all_schemes['E37c'] = {
        'label': 'Balanced Patent (pos~100) + 13 Wet-Lab, sup, ep=50',
        'checkpoint': ckpt_c, 'eval': e37c_eval,
        'paradigm': 'from_scratch', 'group': 'A',
    }

    # E37j: High pos_weight
    print("\n--- E37j: High Pos Weight (pos_w=10.0) ---")
    wgt_j = []
    for w in p403_wgt:
        wgt_j.append(w)
    for i, l in enumerate(w13_lab):
        wgt_j.append(10.0 if l == 1 else 1.0)
    ckpt_j = str(OUTPUT_DIR / 'e37j_highpos.pt')
    t0 = time.time()
    r_j = train(ckpt_j, smi_b, lab_b, wgt_j, prev_checkpoint=None,
                epochs=50, lr=3e-4, ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_j.get('final_loss')}")
    e37j_eval = rank_and_eval(ckpt_j, "E37j", r2_mols, POOL_CSV) if r_j.get('ok') else None
    all_schemes['E37j'] = {
        'label': 'High Pos Weight (403+13, sup, pos_w=10.0, ep=50)',
        'checkpoint': ckpt_j, 'eval': e37j_eval,
        'paradigm': 'from_scratch', 'group': 'D',
    }

    # ═══════════════════════════════════════════════════════════
    # Group B+C: Fine-Tune from E34 with L2-SP (E37d/e/f/g/h/i)
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print("  Group B+C: E34 Fine-Tune + L2-SP")
    print(f"{'='*60}")

    # Prep decoy sets for fine-tune
    decoy_200 = load_decoys(200, set(w13_smi), rng)
    decoy_500 = load_decoys(500, set(w13_smi), rng)
    pat100_idx = rng.choice(len(p403_smi), size=100, replace=False)
    pat100_smi = [p403_smi[i] for i in pat100_idx]
    pat100_lab = [p403_lab[i] for i in pat100_idx]
    pat100_wgt = [p403_wgt[i] for i in pat100_idx]

    # E37d: 13 only, no aux data
    print("\n--- E37d: Pure L2-SP (13 only) ---")
    ckpt_d = str(OUTPUT_DIR / 'e37d_pure_l2sp.pt')
    t0 = time.time()
    r_d = train(ckpt_d, w13_smi[:], w13_lab[:], w13_wgt[:],
                prev_checkpoint=E34_CKPT, epochs=5, lr=3e-4, l2_lambda=1e-2,
                ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_d.get('final_loss')}")
    e37d_eval = rank_and_eval(ckpt_d, "E37d", r2_mols, POOL_CSV) if r_d.get('ok') else None
    all_schemes['E37d'] = {
        'label': 'Pure L2-SP (E34+13 only, l2=1e-2, ep=5)',
        'checkpoint': ckpt_d, 'eval': e37d_eval,
        'paradigm': 'ft_l2sp', 'group': 'B',
    }

    # E37e: +200 decoys
    print("\n--- E37e: L2-SP + Decoys ---")
    smi_e = w13_smi + decoy_200
    lab_e = w13_lab + [0]*len(decoy_200)
    wgt_e = w13_wgt + [1.0]*len(decoy_200)
    ckpt_e = str(OUTPUT_DIR / 'e37e_l2sp_decoys.pt')
    t0 = time.time()
    r_e = train(ckpt_e, smi_e, lab_e, wgt_e,
                prev_checkpoint=E34_CKPT, epochs=5, lr=3e-4, l2_lambda=1e-2,
                ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_e.get('final_loss')}")
    e37e_eval = rank_and_eval(ckpt_e, "E37e", r2_mols, POOL_CSV) if r_e.get('ok') else None
    all_schemes['E37e'] = {
        'label': 'L2-SP + Decoys (E34+13+200d, l2=1e-2, ep=5)',
        'checkpoint': ckpt_e, 'eval': e37e_eval,
        'paradigm': 'ft_l2sp', 'group': 'B',
    }

    # E37f: +100 patent + 200 decoys
    print("\n--- E37f: L2-SP + Patent Anchor ---")
    smi_f = w13_smi + pat100_smi + decoy_200
    lab_f = w13_lab + pat100_lab + [0]*len(decoy_200)
    wgt_f = w13_wgt + pat100_wgt + [1.0]*len(decoy_200)
    ckpt_f = str(OUTPUT_DIR / 'e37f_l2sp_patent.pt')
    t0 = time.time()
    r_f = train(ckpt_f, smi_f, lab_f, wgt_f,
                prev_checkpoint=E34_CKPT, epochs=5, lr=3e-4, l2_lambda=1e-2,
                ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_f.get('final_loss')}")
    e37f_eval = rank_and_eval(ckpt_f, "E37f", r2_mols, POOL_CSV) if r_f.get('ok') else None
    all_schemes['E37f'] = {
        'label': 'L2-SP + Patent (E34+13+100p+200d, l2=1e-2, ep=5)',
        'checkpoint': ckpt_f, 'eval': e37f_eval,
        'paradigm': 'ft_l2sp', 'group': 'B',
    }

    # E37g: +403 patent + 200 decoys
    print("\n--- E37g: L2-SP + Full 403 Patent ---")
    smi_g = w13_smi + p403_smi + decoy_200
    lab_g = w13_lab + p403_lab + [0]*len(decoy_200)
    wgt_g = w13_wgt + p403_wgt + [1.0]*len(decoy_200)
    ckpt_g = str(OUTPUT_DIR / 'e37g_l2sp_fullpatent.pt')
    t0 = time.time()
    r_g = train(ckpt_g, smi_g, lab_g, wgt_g,
                prev_checkpoint=E34_CKPT, epochs=5, lr=3e-4, l2_lambda=1e-2,
                ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_g.get('final_loss')}")
    e37g_eval = rank_and_eval(ckpt_g, "E37g", r2_mols, POOL_CSV) if r_g.get('ok') else None
    all_schemes['E37g'] = {
        'label': 'L2-SP + Full 403 Patent (E34+13+403p+200d, l2=1e-2, ep=5)',
        'checkpoint': ckpt_g, 'eval': e37g_eval,
        'paradigm': 'ft_l2sp', 'group': 'B',
    }

    # E37h: Weak L2-SP (l2=3e-3)
    print("\n--- E37h: Weak L2-SP (l2=3e-3) ---")
    ckpt_h = str(OUTPUT_DIR / 'e37h_weak_l2sp.pt')
    t0 = time.time()
    r_h = train(ckpt_h, smi_e, lab_e, wgt_e,       # same data as E37e
                prev_checkpoint=E34_CKPT, epochs=5, lr=3e-4, l2_lambda=3e-3,
                ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_h.get('final_loss')}")
    e37h_eval = rank_and_eval(ckpt_h, "E37h", r2_mols, POOL_CSV) if r_h.get('ok') else None
    all_schemes['E37h'] = {
        'label': 'Weak L2-SP (E34+13+200d, l2=3e-3, ep=5)',
        'checkpoint': ckpt_h, 'eval': e37h_eval,
        'paradigm': 'ft_l2sp', 'group': 'C',
    }

    # E37i: Low LR + More Epochs
    print("\n--- E37i: Low LR + More Epochs ---")
    ckpt_i = str(OUTPUT_DIR / 'e37i_lowlr.pt')
    t0 = time.time()
    r_i = train(ckpt_i, smi_e, lab_e, wgt_e,       # same data as E37e
                prev_checkpoint=E34_CKPT, epochs=10, lr=1e-4, l2_lambda=1e-2,
                ensemble_size=ENSEMBLE, strategy="supervised")
    print(f"  Trained in {time.time()-t0:.0f}s, loss={r_i.get('final_loss')}")
    e37i_eval = rank_and_eval(ckpt_i, "E37i", r2_mols, POOL_CSV) if r_i.get('ok') else None
    all_schemes['E37i'] = {
        'label': 'Low LR (E34+13+200d, l2=1e-2, ep=10, lr=1e-4)',
        'checkpoint': ckpt_i, 'eval': e37i_eval,
        'paradigm': 'ft_l2sp', 'group': 'C',
    }

    # ═══════════════════════════════════════════════════════════
    # Comparison Report
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print(f"  E37: 10 Schemes Comparison — 19 Round-2 Molecules")
    print(f"{'='*90}")

    # Load E34 baseline
    with open(E34_RANKING) as f:
        e34_eval = json.load(f)
    e34_mean = e34_eval['e34_mean_rank']

    # Print per-molecule comparison for each scheme
    r2_ids = [m['id'] for m in r2_mols]

    print(f"\n  {'Scheme':>8s} {'Mean Rank':>12s} {'vs E34':>10s} {'Top-5 Count':>12s} {'Status':>8s}")
    print(f"  {'─'*55}")
    print(f"  {'E34':>8s} #{e34_mean:>11.0f} {'—':>10s} —           —")

    best_scheme = None
    best_mean = e34_mean

    for key in sorted(all_schemes.keys()):
        s = all_schemes[key]
        ev = s['eval']
        if ev is None or ev['mean_rank'] is None:
            print(f"  {key:>8s} {'FAILED':>12s}")
            continue
        mean_r = ev['mean_rank']
        delta = e34_mean - mean_r
        better = '✅' if delta > 0 else '❌'
        print(f"  {key:>8s} #{mean_r:>11.0f} {delta:>+10.0f} —           {better}")
        if mean_r < best_mean:
            best_mean = mean_r
            best_scheme = key

    print(f"\n  Best: {best_scheme} (#{best_mean:.0f}, Δ vs E34 = {e34_mean-best_mean:+.0f})")

    # ── Detailed per-molecule for top-3 schemes ───────────────
    top_schemes = sorted(
        [(k, v) for k, v in all_schemes.items() if v['eval'] and v['eval']['mean_rank']],
        key=lambda x: x[1]['eval']['mean_rank']
    )[:3]

    for skey, sval in top_schemes:
        ev = sval['eval']
        print(f"\n  {skey} ({sval['label']}): mean=#{ev['mean_rank']:.0f}")
        for r in sorted(ev['results'], key=lambda x: x['glare_rank'] or 99999):
            rank_str = f"#{r['glare_rank']}" if r['glare_rank'] else "N/A"
            pct_str = f"({r['glare_pct']}%)" if r['glare_pct'] else ""
            print(f"    {r['mol_id']:>16s} {rank_str:>8s} {pct_str}")

    # ── Save full report ──────────────────────────────────────
    report = {
        'e34_baseline_mean_rank': e34_mean,
        'r2_query_molecules': r2_ids,
        'schemes': {},
    }
    for key, s in all_schemes.items():
        report['schemes'][key] = {
            'label': s['label'],
            'paradigm': s['paradigm'],
            'group': s['group'],
            'checkpoint': s['checkpoint'],
            'mean_rank': s['eval']['mean_rank'] if s['eval'] else None,
            'median_rank': s['eval']['median_rank'] if s['eval'] else None,
            'n_pool': s['eval']['n_pool'] if s['eval'] else None,
            'results': s['eval']['results'] if s['eval'] else None,
        }

    report_path = OUTPUT_DIR / 'e37_10schemes_comparison.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report: {report_path}")

    # CSV
    csv_rows = []
    for key, s in all_schemes.items():
        if not s['eval'] or not s['eval']['results']:
            continue
        for r in s['eval']['results']:
            csv_rows.append({
                'scheme': key, 'paradigm': s['paradigm'],
                'mol_id': r['mol_id'], 'glare_rank': r['glare_rank'],
                'glare_pct': r['glare_pct'],
            })
    csv_path = OUTPUT_DIR / 'e37_10schemes_comparison.csv'
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"✅ CSV:    {csv_path}")

    print(f"\n✅ E37 — All 10 schemes complete.")
    print(f"   Best: {best_scheme} (#{best_mean:.0f})")

if __name__ == '__main__':
    main()