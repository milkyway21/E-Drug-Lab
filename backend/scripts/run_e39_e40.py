#!/usr/bin/env python3
"""E39+E40 — 验证 IG 归因在 ensemble=3/10 下的真实作用。

核心问题：E37b（ens=3, stub=无IG） #4174 >> E38a（ens=10, 真IG） #6432
两个变量同时变了（ens 3→10, IG stub→real）。需要隔离：
  - E39: ensemble=3 + 真 IG —— IG 在 ens=3 下是否有用？
  - E40a: ensemble=3 + 禁 IG —— 是否复现 E37b #4174？
  - E40b: ensemble=10 + 禁 IG —— IG 是问题，还是 ensemble=10 本身就是问题？

实验：
  E39  — GRPO, ens=3, real IG,  403+13, l2=3e-4
  E40a — GRPO, ens=3, disable IG, 403+13, l2=3e-4
  E40b — GRPO, ens=10, disable IG, 403+13, l2=3e-4

基线：E34 #6583, E37b #4174, E38a #6432
评估：19 round-2 molecules on MolFactory 0711 pool (11697 molecules)
"""
import sys, os, json, time
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import train, query

# ── Paths ───────────────────────────────────────────────────
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e39_e40')
SDF_DIR_R1 = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第一轮分子生成15个实体分子'
SDF_DIR_R2 = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第二轮动力学指导的分子生成'
POOL_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/MolFactory_0711_merged.csv'
PATENT_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv'
WETLAB_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv'

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

def load_r2_query_smiles():
    mols = []
    for fname in sorted(os.listdir(SDF_DIR_R2)):
        if not fname.endswith('.sdf'): continue
        sid = fname.replace('.sdf', '')
        canon = extract_smiles_from_sdf(os.path.join(SDF_DIR_R2, fname))
        if canon: mols.append({'id': sid, 'smiles': canon})
    return mols

def rank_and_eval(ckpt_path, label, r2_mols, pool_csv, ensemble_size):
    pool_df = pd.read_csv(pool_csv)
    pool_smiles = [norm(s) for s in pool_df['smiles'].tolist()]
    pool_smiles = [s for s in pool_smiles if s]
    r2_smiles_set = set(m['smiles'] for m in r2_mols)
    all_smiles = list(dict.fromkeys(pool_smiles + list(r2_smiles_set)))
    print(f"  [{label}] Querying {len(all_smiles)} molecules (ensemble={ensemble_size})...")
    t0 = time.time()
    qr = query(ckpt_path, all_smiles, ensemble_size=ensemble_size)
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
        'results': results, 'n_pool': len(all_smiles),
        'mean_rank': float(np.mean(ranks)) if ranks else None,
        'median_rank': float(np.median(ranks)) if ranks else None,
    }

def train_and_eval(key, label, train_smiles, train_labels, train_weights, *,
                    strategy, l2_lambda, ensemble_size, disable_ig, r2_mols):
    """训练 + 评估，checkpoint 存在则跳过训练只 query。"""
    ckpt_path = str(OUTPUT_DIR / f'{key.lower()}.pt')
    if not Path(ckpt_path).exists():
        print(f"\n  [{key}] Training ({label})...")
        t0 = time.time()
        r = train(
            ckpt_path, train_smiles, train_labels, train_weights,
            prev_checkpoint=None,
            epochs=50, lr=3e-4,
            ensemble_size=ensemble_size,
            l2_lambda=l2_lambda,
            weight_decay=0.0,
            batch_size=64,
            strategy=strategy,
            disable_ig=disable_ig,
        )
        train_time = time.time() - t0
        if not r.get('ok', False):
            print(f"    ❌ Train failed: {r.get('error', str(r)[:200])}")
            return {'ok': False, 'key': key, 'label': label, 'checkpoint': ckpt_path}
        print(f"    ✅ Trained in {train_time:.0f}s, loss={r.get('final_loss')}")
    else:
        print(f"\n  [{key}] ⏭️  Checkpoint exists, skip training")

    ev = rank_and_eval(ckpt_path, key, r2_mols, POOL_CSV, ensemble_size=ensemble_size)
    return {'ok': True, 'key': key, 'label': label, 'checkpoint': ckpt_path, 'eval': ev,
            'strategy': strategy, 'l2_lambda': l2_lambda,
            'ensemble_size': ensemble_size, 'disable_ig': disable_ig}


# ── Main ─────────────────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E39+E40 — IG Attribution: Bug or Feature?")
    print("=" * 80)

    w13_smi, w13_lab, w13_wgt = load_wetlab_13()
    p403_smi, p403_lab, p403_wgt = load_patent_403()
    r2_mols = load_r2_query_smiles()

    smi_403_13 = p403_smi + w13_smi
    lab_403_13 = p403_lab + w13_lab
    wgt_403_13 = p403_wgt + w13_wgt

    print(f"\nWet-lab: {len(w13_smi)} (pos={sum(w13_lab)})")
    print(f"Patent:  {len(p403_smi)} (pos={sum(p403_lab)})")
    print(f"R2 query: {len(r2_mols)} mols")

    # ═══════════════════════════════════════════════════════════
    # 3 Schemes
    # ═══════════════════════════════════════════════════════════
    schemes_def = [
        # (key, label, smi, lab, wgt, strategy, l2, ens, disable_ig)
        ('E39',  'GRPO ens=3 + real IG (verify IG effect @ ens=3)',
         smi_403_13, lab_403_13, wgt_403_13, 'grpo', 3e-4, 3, False),
        ('E40a', 'GRPO ens=3 + NO IG (confirm E37b = no-IG)',
         smi_403_13, lab_403_13, wgt_403_13, 'grpo', 3e-4, 3, True),
        ('E40b', 'GRPO ens=10 + NO IG (isolate: IG vs ensemble size)',
         smi_403_13, lab_403_13, wgt_403_13, 'grpo', 3e-4, 10, True),
    ]

    results_all = {}
    for key, label, smi, lab, wgt, strategy, l2_lambda, ensemble_size, disable_ig in schemes_def:
        print(f"\n{'─'*60}")
        print(f"  {key}: {label}")
        ig_label = "NO-IG" if disable_ig else "real-IG"
        print(f"  data={len(smi)}, ens={ensemble_size}, l2={l2_lambda}, IG={ig_label}")
        print(f"{'─'*60}")

        res = train_and_eval(key, label, smi, lab, wgt,
                             strategy=strategy, l2_lambda=l2_lambda,
                             ensemble_size=ensemble_size, disable_ig=disable_ig,
                             r2_mols=r2_mols)
        results_all[key] = res

    # ═══════════════════════════════════════════════════════════
    # Comparison Report
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*100}")
    print(f"  E39+E40 Results — 19 Round-2 Molecules")
    print(f"{'='*100}")

    e34_mean = 6582.6
    e37b_mean = 4174.0
    e38a_mean = 6431.5

    print(f"\n  {'Scheme':>8s} {'Strategy':>12s} {'ens':>4s} {'IG':>8s} {'l2':>8s} {'Mean Rank':>12s} {'vs E34':>10s} {'vs E37b':>10s} {'vs E38a':>10s}")
    print(f"  {'─'*95}")
    print(f"  {'E34':>8s} {'—':>12s} {'—':>4s} {'—':>8s} {'—':>8s} #{e34_mean:>11.0f} {'—':>10s} {'—':>10s} {'—':>10s}")
    print(f"  {'E37b':>8s} {'GRPO':>12s} {'3':>4s} {'stub':>8s} {'3e-4':>8s} #{e37b_mean:>11.0f} {'+2409':>10s} {'—':>10s} {'+2258':>10s}")
    print(f"  {'E38a':>8s} {'GRPO':>12s} {'10':>4s} {'real':>8s} {'3e-4':>8s} #{e38a_mean:>11.0f} {'+151':>10s} {'-2258':>10s} {'—':>10s}")

    best_key, best_mean = None, e34_mean
    for key in ['E39', 'E40a', 'E40b']:
        r = results_all.get(key, {})
        if not r.get('ok') or not r.get('eval') or r['eval']['mean_rank'] is None:
            print(f"  {key:>8s} {'FAILED':>12s}")
            continue
        ev = r['eval']
        mean_r = ev['mean_rank']
        ig_label = 'NO-IG' if r.get('disable_ig') else 'real'
        delta_e34 = e34_mean - mean_r
        delta_e37b = e37b_mean - mean_r
        delta_e38a = e38a_mean - mean_r
        better = "✅" if delta_e34 > 0 else "❌"
        print(f"  {key:>8s} {'GRPO':>12s} {r['ensemble_size']:>4d} {ig_label:>8s} "
              f"{r['l2_lambda']:.0e} #{mean_r:>11.0f} "
              f"{delta_e34:>+10.0f} {delta_e37b:>+10.0f} {delta_e38a:>+10.0f} {better:>6s}")
        if mean_r < best_mean:
            best_mean, best_key = mean_r, key

    print(f"\n  🏆 Best: {best_key} (#{best_mean:.0f})")
    if best_mean < e37b_mean:
        print(f"  🔥 超越 E37b! Δ = {e37b_mean - best_mean:+.0f}")

    # ── Top-3 detail ──────────────────────────────────────────
    sorted_keys = sorted(
        [(k, v) for k, v in results_all.items() if v.get('ok') and v.get('eval') and v['eval']['mean_rank']],
        key=lambda x: x[1]['eval']['mean_rank']
    )
    for skey, sval in sorted_keys[:3]:
        ev = sval['eval']
        ig = 'NO-IG' if sval.get('disable_ig') else 'real-IG'
        print(f"\n  {skey} ({sval['label']}): mean=#{ev['mean_rank']:.0f}")
        for r_ in sorted(ev['results'], key=lambda x: x['glare_rank'] or 99999):
            print(f"    {r_['mol_id']:>16s} {'#'+str(r_['glare_rank']) if r_['glare_rank'] else 'N/A':>8s} "
                  f"{('('+str(r_['glare_pct'])+'%)') if r_['glare_pct'] else ''}")

    # ── Save ──────────────────────────────────────────────────
    report = {
        'description': 'E39+E40 — IG attribution: bug or feature?',
        'e34_baseline': e34_mean,
        'e37b_baseline': e37b_mean,
        'e38a_baseline': e38a_mean,
        'schemes': {}
    }
    for key, r in results_all.items():
        report['schemes'][key] = {
            'label': r['label'], 'checkpoint': r['checkpoint'],
            'strategy': r.get('strategy'), 'l2_lambda': r.get('l2_lambda'),
            'ensemble_size': r.get('ensemble_size'), 'disable_ig': r.get('disable_ig'),
            'mean_rank': r['eval']['mean_rank'] if r.get('eval') else None,
            'median_rank': r['eval']['median_rank'] if r.get('eval') else None,
            'n_pool': r['eval']['n_pool'] if r.get('eval') else None,
            'results': r['eval']['results'] if r.get('eval') else None,
        }

    report_path = OUTPUT_DIR / 'e39_e40_comparison.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report: {report_path}")

    csv_rows = []
    for key, r in results_all.items():
        if not r.get('eval') or not r['eval'].get('results'): continue
        for r_ in r['eval']['results']:
            csv_rows.append({
                'scheme': key, 'strategy': r.get('strategy'), 'l2_lambda': r.get('l2_lambda'),
                'ensemble_size': r.get('ensemble_size'), 'disable_ig': r.get('disable_ig'),
                'mol_id': r_['mol_id'], 'glare_rank': r_['glare_rank'], 'glare_pct': r_['glare_pct'],
            })
    pd.DataFrame(csv_rows).to_csv(OUTPUT_DIR / 'e39_e40_comparison.csv', index=False)
    print(f"✅ CSV:    {OUTPUT_DIR / 'e39_e40_comparison.csv'}")
    print(f"\n✅ E39+E40 Done.")

if __name__ == '__main__':
    main()
