#!/usr/bin/env python3
"""E38 — 官方 GLARE 配置 + 3 个变体。

GLARE 官方 LIT-PCBA 推荐: GRPO + ginl + ensemble=10 + epochs=50 + l2_lambda=3e-4

4 个方案:
  E38a: 官方 GRPO — ensemble=10, GRPO, 403+13
  E38b: 官方 supervised — ensemble=10, supervised, 403+13 (对比 GRPO vs sup at ensemble=10)
  E38c: GRPO 403-only — ensemble=10, GRPO, 403 only (对比 E37b: wet-lab 数据贡献)
  E38d: GRPO 强 L2 — ensemble=10, GRPO, 403+13, l2_lambda=1e-2 (L2-SP 强度对 GRPO 的影响)

评估: 19 round-2 分子 on MolFactory 0711 pool (11697 molecules)
基线: E34 #6583, E37b(GRPO ens=3) #4174
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
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e38_official')
SDF_DIR_R1 = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第一轮分子生成15个实体分子'
SDF_DIR_R2 = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第二轮动力学指导的分子生成'
POOL_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/MolFactory_0711_merged.csv'
PATENT_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv'
E34_RANKING = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/round2_dynamics_ranking/e34_vs_e36_round2_dynamics.json'
WETLAB_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e26_patent_320_83_20260630/data/new_13_molecules.csv'

# ── Official GLARE config ───────────────────────────────────
OFFICIAL = dict(
    epochs=50, lr=3e-4, ensemble_size=10, l2_lambda=3e-4,
    weight_decay=0.0, batch_size=64, strategy="grpo",
)
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

def rank_and_eval(ckpt_path, label, r2_mols, pool_csv, ensemble_size=10):
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

def train_and_eval(key, label, train_smiles, train_labels, train_weights, *, strategy, l2_lambda, r2_mols):
    """训练 + 评估，checkpoint 存在则跳过训练只 query。"""
    ckpt_path = str(OUTPUT_DIR / f'{key.lower()}.pt')
    if not Path(ckpt_path).exists():
        print(f"\n  [{key}] Training ({label})...")
        t0 = time.time()
        r = train(
            ckpt_path, train_smiles, train_labels, train_weights,
            prev_checkpoint=None,
            epochs=OFFICIAL['epochs'], lr=OFFICIAL['lr'],
            ensemble_size=OFFICIAL['ensemble_size'],
            l2_lambda=l2_lambda,
            weight_decay=OFFICIAL['weight_decay'],
            batch_size=OFFICIAL['batch_size'],
            strategy=strategy,
        )
        train_time = time.time() - t0
        if not r.get('ok', False):
            print(f"    ❌ Train failed: {r.get('error', str(r)[:200])}")
            return {'ok': False, 'key': key, 'label': label, 'checkpoint': ckpt_path}
        print(f"    ✅ Trained in {train_time:.0f}s, loss={r.get('final_loss')}")
    else:
        print(f"\n  [{key}] ⏭️  Checkpoint exists, skip training")

    ev = rank_and_eval(ckpt_path, key, r2_mols, POOL_CSV, ensemble_size=OFFICIAL['ensemble_size'])
    return {'ok': True, 'key': key, 'label': label, 'checkpoint': ckpt_path, 'eval': ev,
            'strategy': strategy, 'l2_lambda': l2_lambda}


# ── Main ─────────────────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E38 — Official GLARE Config + 3 Variants")
    print(f"  ensemble=10, epochs=50, ginl")
    print("=" * 80)

    w13_smi, w13_lab, w13_wgt = load_wetlab_13()
    p403_smi, p403_lab, p403_wgt = load_patent_403()
    r2_mols = load_r2_query_smiles()

    print(f"\nWet-lab: {len(w13_smi)} (pos={sum(w13_lab)})")
    print(f"Patent:  {len(p403_smi)} (pos={sum(p403_lab)})")
    print(f"R2 query: {len(r2_mols)} mols")

    # ── Prepare data ──────────────────────────────────────────
    smi_403_13 = p403_smi + w13_smi
    lab_403_13 = p403_lab + w13_lab
    wgt_403_13 = p403_wgt + w13_wgt

    # ── 4 Schemes ─────────────────────────────────────────────
    schemes_def = [
        ('E38a', 'Official GRPO (ens=10, 403+13, l2=3e-4)', smi_403_13, lab_403_13, wgt_403_13,
         'grpo', 3e-4),
        ('E38b', 'Official Supervised (ens=10, 403+13, l2=3e-4)', smi_403_13, lab_403_13, wgt_403_13,
         'supervised', 3e-4),
        ('E38c', 'GRPO 403-only (ens=10, no wet-lab, l2=3e-4)', p403_smi, p403_lab, p403_wgt,
         'grpo', 3e-4),
        ('E38d', 'GRPO Strong L2 (ens=10, 403+13, l2=1e-2)', smi_403_13, lab_403_13, wgt_403_13,
         'grpo', 1e-2),
    ]

    results_all = {}
    for key, label, smi, lab, wgt, strategy, l2_lambda in schemes_def:
        print(f"\n{'─'*60}")
        print(f"  {key}: {label}")
        print(f"  data={len(smi)} mols, strategy={strategy}, l2_lambda={l2_lambda}")
        print(f"{'─'*60}")

        res = train_and_eval(key, label, smi, lab, wgt, strategy=strategy, l2_lambda=l2_lambda, r2_mols=r2_mols)
        results_all[key] = res

    # ═══════════════════════════════════════════════════════════
    # Comparison Report
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*95}")
    print(f"  E38 Results — 19 Round-2 Molecules")
    print(f"{'='*95}")

    with open(E34_RANKING) as f:
        e34_eval = json.load(f)
    e34_mean = e34_eval['e34_mean_rank']

    # Baselines from E37
    e37b_mean = 4174.0  # E37b GRPO ensemble=3 的最佳结果

    print(f"\n  {'Scheme':>8s} {'Strategy':>12s} {'ens':>4s} {'l2_lambda':>10s} {'Data':>10s} {'Mean Rank':>12s} {'vs E34':>10s} {'vs E37b':>10s}")
    print(f"  {'─'*85}")
    print(f"  {'E34':>8s} {'—':>12s} {'—':>4s} {'—':>10s} {'403':>10s} #{e34_mean:>11.0f} {'—':>10s} {'—':>10s}")
    print(f"  {'E37b':>8s} {'GRPO':>12s} {'3':>4s} {'3e-4':>10s} {'403+13':>10s} #{e37b_mean:>11.0f} {'+2409':>10s} {'—':>10s}")

    best_key, best_mean = None, e34_mean
    for key in ['E38a', 'E38b', 'E38c', 'E38d']:
        r = results_all.get(key, {})
        if not r.get('ok') or not r.get('eval') or r['eval']['mean_rank'] is None:
            print(f"  {key:>8s} {'FAILED':>12s}")
            continue
        ev = r['eval']
        mean_r = ev['mean_rank']
        delta_e34 = e34_mean - mean_r
        delta_e37b = e37b_mean - mean_r
        print(f"  {key:>8s} {r['strategy']:>12s} {OFFICIAL['ensemble_size']:>4d} "
              f"{r['l2_lambda']:.0e} {'403+13' if 'only' not in r['label'] else '403':>10s} "
              f"#{mean_r:>11.0f} {delta_e34:>+10.0f} {delta_e37b:>+10.0f} "
              f"{'✅' if delta_e34 > 0 else '❌':>6s}")
        if mean_r < best_mean:
            best_mean, best_key = mean_r, key

    print(f"\n  🏆 Best E38: {best_key} (#{best_mean:.0f})")
    if best_mean < e37b_mean:
        print(f"  🔥 E38 超越了 E37b! Δ = {e37b_mean - best_mean:+.0f}")

    # ── Top-3 detail ──────────────────────────────────────────
    sorted_keys = sorted(
        [(k, v) for k, v in results_all.items() if v.get('ok') and v.get('eval') and v['eval']['mean_rank']],
        key=lambda x: x[1]['eval']['mean_rank']
    )
    for skey, sval in sorted_keys[:3]:
        ev = sval['eval']
        print(f"\n  {skey} ({sval['label']}): mean=#{ev['mean_rank']:.0f}")
        for r_ in sorted(ev['results'], key=lambda x: x['glare_rank'] or 99999):
            print(f"    {r_['mol_id']:>16s} {'#'+str(r_['glare_rank']) if r_['glare_rank'] else 'N/A':>8s} "
                  f"{('('+str(r_['glare_pct'])+'%)') if r_['glare_pct'] else ''}")

    # ── Save ──────────────────────────────────────────────────
    report = {
        'description': 'E38 — Official GLARE config + variants',
        'official_config': OFFICIAL,
        'e34_baseline': e34_mean,
        'e37b_baseline': e37b_mean,
        'schemes': {}
    }
    for key, r in results_all.items():
        report['schemes'][key] = {
            'label': r['label'], 'checkpoint': r['checkpoint'],
            'strategy': r.get('strategy'), 'l2_lambda': r.get('l2_lambda'),
            'mean_rank': r['eval']['mean_rank'] if r.get('eval') else None,
            'median_rank': r['eval']['median_rank'] if r.get('eval') else None,
            'n_pool': r['eval']['n_pool'] if r.get('eval') else None,
            'results': r['eval']['results'] if r.get('eval') else None,
        }

    report_path = OUTPUT_DIR / 'e38_official_comparison.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report: {report_path}")

    csv_rows = []
    for key, r in results_all.items():
        if not r.get('eval') or not r['eval'].get('results'): continue
        for r_ in r['eval']['results']:
            csv_rows.append({
                'scheme': key, 'strategy': r.get('strategy'), 'l2_lambda': r.get('l2_lambda'),
                'mol_id': r_['mol_id'], 'glare_rank': r_['glare_rank'], 'glare_pct': r_['glare_pct'],
            })
    pd.DataFrame(csv_rows).to_csv(OUTPUT_DIR / 'e38_official_comparison.csv', index=False)
    print(f"✅ CSV:    {OUTPUT_DIR / 'e38_official_comparison.csv'}")
    print(f"\n✅ E38 Done.")

if __name__ == '__main__':
    main()
