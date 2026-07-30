#!/usr/bin/env python3
"""E34 vs E36 权重对第二轮动力学分子排序对比。

- 待排序分子：/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第二轮动力学指导的分子生成/ (19 SDF)
- 排序池：/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/MolFactory_0711_merged.csv (13,587 分子)
"""
import sys, os, json, time
import numpy as np
import pandas as pd
from pathlib import Path
from rdkit import Chem

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import query

# ── Config ──────────────────────────────────────────────────
E34_CKPT = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e34_full_403/e34_grpo_sup/checkpoints/cycle_7.pt'
E36_CKPT = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e36_full_patent_plus_wetlab/e36_full.pt'
SDF_DIR = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/第二轮动力学指导的分子生成'
POOL_CSV = '/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/MolFactory_0711_merged.csv'
OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/round2_dynamics_ranking')

ENSEMBLE = 3

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

def rank_pool(ckpt_path, pool_smiles, label):
    """Query GLARE on pool and return rank map."""
    print(f"  [{label}] Querying on {len(pool_smiles)} molecules...")
    t0 = time.time()
    qr = query(ckpt_path, pool_smiles, ensemble_size=ENSEMBLE)
    if not qr.get('ok', False) and 'ranked' not in qr:
        print(f"    ❌ Failed: {qr.get('error', str(qr)[:200])}")
        return None
    ranked = qr.get('ranked', [])
    print(f"    ✅ Ranked in {time.time()-t0:.0f}s")
    rank_map = {}
    for r in ranked:
        rank_map[norm(r['smiles'])] = int(r['glare_rank'])
    return rank_map

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("  E34 vs E36 — 第二轮动力学指导分子排序对比")
    print(f"  待排序 SDF: {SDF_DIR}")
    print(f"  排序池: {POOL_CSV}")
    print("=" * 80)

    # ── Step 1: Extract query molecule SMILES ────────────────
    print(f"\n[1/3] Extracting query molecule SMILES...")
    query_mols = []
    for fname in sorted(os.listdir(SDF_DIR)):
        if not fname.endswith('.sdf'):
            continue
        sid = fname.replace('.sdf', '')
        fpath = os.path.join(SDF_DIR, fname)
        canon = extract_smiles_from_sdf(fpath)
        if canon is None:
            print(f"  ❌ {sid}: FAILED to parse")
            continue
        query_mols.append({'id': sid, 'smiles': canon})
        print(f"  ✅ {sid}: {canon[:70]}...")

    query_smiles_set = set(m['smiles'] for m in query_mols)
    print(f"  Total: {len(query_mols)} query molecules ({len(query_smiles_set)} unique)")

    # ── Step 2: Load pool + query molecules, merge ───────────
    print(f"\n[2/3] Loading pool and ranking with E34 & E36...")
    pool_df = pd.read_csv(POOL_CSV)
    pool_smiles = [norm(s) for s in pool_df['smiles'].tolist()]
    pool_smiles = [s for s in pool_smiles if s]

    # Merge query SMILES into pool (dedup)
    all_smiles = list(dict.fromkeys(pool_smiles + list(query_smiles_set)))

    # Rank with both checkpoints
    e34_rank_map = rank_pool(E34_CKPT, all_smiles, "E34")
    e36_rank_map = rank_pool(E36_CKPT, all_smiles, "E36")

    if e34_rank_map is None or e36_rank_map is None:
        print("❌ Ranking failed")
        return

    # ── Step 3: Build comparison report ──────────────────────
    print(f"\n[3/3] Building comparison...")

    n_pool = len(all_smiles)
    results = []
    for mol in query_mols:
        e34_r = e34_rank_map.get(mol['smiles'])
        e36_r = e36_rank_map.get(mol['smiles'])
        e34_rank = e34_r if e34_r else None
        e36_rank = e36_r if e36_r else None
        delta = e34_rank - e36_rank if (e34_rank and e36_rank) else None
        results.append({
            'mol_id': mol['id'],
            'smiles': mol['smiles'][:80],
            'e34_rank': e34_rank,
            'e34_pct': round(100 * e34_rank / n_pool, 2) if e34_rank else None,
            'e36_rank': e36_rank,
            'e36_pct': round(100 * e36_rank / n_pool, 2) if e36_rank else None,
            'delta': delta,
            'e36_better': delta > 0 if delta else None,
        })

    # Stats
    valid = [r for r in results if r['delta'] is not None]
    e34_ranks = [r['e34_rank'] for r in valid]
    e36_ranks = [r['e36_rank'] for r in valid]
    e34_mean = float(np.mean(e34_ranks))
    e36_mean = float(np.mean(e36_ranks))
    n_e36_better = sum(1 for r in valid if r['e36_better'])
    n_e34_better = sum(1 for r in valid if not r['e36_better'])

    # ── Print report ────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  E34 vs E36 — 第二轮动力学分子 (19 SDF) 排序对比")
    print(f"  排序池: {n_pool} molecules")
    print(f"{'='*100}")
    print(f"  {'Mol ID':>16s} {'E34 Rank':>10s} {'E34 %':>8s} {'E36 Rank':>10s} {'E36 %':>8s} {'Δ':>8s} {'E36 Better':>10s}")
    print(f"  {'─'*85}")

    for r in sorted(results, key=lambda x: x['e34_rank'] or 99999):
        e34_r = f"#{r['e34_rank']}" if r['e34_rank'] else "N/A"
        e34_p = f"{r['e34_pct']:.1f}%" if r['e34_pct'] else "N/A"
        e36_r = f"#{r['e36_rank']}" if r['e36_rank'] else "N/A"
        e36_p = f"{r['e36_pct']:.1f}%" if r['e36_pct'] else "N/A"
        d = f"{r['delta']:+d}" if r['delta'] is not None else "N/A"
        better = "🟢 YES" if r['e36_better'] else ("🔴 NO" if r['e36_better'] is False else "—")
        print(f"  {r['mol_id']:>16s} {e34_r:>10s} {e34_p:>8s} {e36_r:>10s} {e36_p:>8s} {d:>8s} {better:>10s}")

    print(f"\n  Summary:")
    print(f"  {'─'*50}")
    print(f"  E34 mean rank: #{e34_mean:.0f} ({100*e34_mean/n_pool:.2f}%)")
    print(f"  E36 mean rank: #{e36_mean:.0f} ({100*e36_mean/n_pool:.2f}%)")
    print(f"  E36 better:   {n_e36_better}/{len(valid)}")
    print(f"  E34 better:   {n_e34_better}/{len(valid)}")
    better_word = "✅ E36 BETTER" if e36_mean < e34_mean else "❌ E34 BETTER"
    print(f"  Verdict:       {better_word} (Δ mean = {e34_mean-e36_mean:+.0f})")

    # Top-5 and Bottom-5 per model
    top5_e34 = sorted(results, key=lambda x: x['e34_rank'] or 99999)[:5]
    top5_e36 = sorted(results, key=lambda x: x['e36_rank'] or 99999)[:5]
    print(f"\n  Top-5 by E34: {', '.join(r['mol_id'] + '(#' + str(r['e34_rank']) + ')' for r in top5_e34)}")
    print(f"  Top-5 by E36: {', '.join(r['mol_id'] + '(#' + str(r['e36_rank']) + ')' for r in top5_e36)}")

    # ── Save ─────────────────────────────────────────────────
    report = {
        'query_sdf_dir': SDF_DIR,
        'pool_csv': POOL_CSV,
        'pool_size': n_pool,
        'n_query_mols': len(results),
        'e34_ckpt': E34_CKPT,
        'e36_ckpt': E36_CKPT,
        'e34_mean_rank': e34_mean,
        'e36_mean_rank': e36_mean,
        'e36_better_count': n_e36_better,
        'e34_better_count': n_e34_better,
        'results': results,
    }
    report_path = OUTPUT_DIR / 'e34_vs_e36_round2_dynamics.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Report: {report_path}")

    # CSV
    csv_path = OUTPUT_DIR / 'e34_vs_e36_round2_dynamics.csv'
    pd.DataFrame(results).to_csv(csv_path, index=False)
    print(f"✅ CSV:    {csv_path}")
    print(f"✅ Done.")


if __name__ == '__main__':
    main()