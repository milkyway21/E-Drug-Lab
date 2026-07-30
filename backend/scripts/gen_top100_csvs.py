#!/usr/bin/env python3
"""Generate top-100 CSVs: CarsiScore, GLARE(E33), and weighted 0.3*Carsi+0.7*GLARE."""
import sys, os, json, time
import numpy as np
from pathlib import Path
from rdkit import Chem
import pandas as pd

os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import query

# ── Config ──────────────────────────────────────────────────
E33_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709')
POOL_CSV = '/data/ye/e-drug-lab/molfactory/MolFactory_merged_6files_dedup_sorted_by_CarsiScore.csv'
CKPT = str(E33_DIR / 'e33_grpo_sup' / 'checkpoints' / 'cycle_6.pt')
FULL_RANK_JSON = str(E33_DIR / 'ranked_10k_e33_grpo_sup.json')
OUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709')

def norm(smi):
    mol = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(mol) if mol else smi

def main():
    print("=" * 80)
    print("  Generate Top-100 CSVs: CarsiScore | GLARE E33 | Weighted 0.3/0.7")
    print("=" * 80)

    # ── Step 1: Load or run GLARE query ─────────────────────
    if Path(FULL_RANK_JSON).exists():
        print(f"\n✅ Loading cached GLARE ranking from {FULL_RANK_JSON}")
        with open(FULL_RANK_JSON) as f:
            rank_data = json.load(f)
        ranked = rank_data['ranked']
    else:
        # Load pool SMILES
        print(f"\nLoading 10K MolFactory pool...")
        pool_df = pd.read_csv(POOL_CSV)
        pool_smiles_raw = pool_df['smiles'].tolist()
        pool_smiles = list(dict.fromkeys([norm(s) for s in pool_smiles_raw if s and norm(s)]))
        print(f"Pool: {len(pool_smiles)} unique SMILES")

        # Run GLARE query
        print(f"\nRunning GLARE E33 query (GPU 5, ensemble=3) on {len(pool_smiles)} mols...")
        t0 = time.time()
        result = query(CKPT, pool_smiles, ensemble_size=3)
        elapsed = time.time() - t0

        if not result.get('ok', False) and 'ranked' not in result:
            print(f"❌ Query failed: {result.get('error', str(result)[:300])}")
            return

        ranked = result.get('ranked', [])
        print(f"✅ Ranked {len(ranked)} molecules in {elapsed:.0f}s ({elapsed/60:.1f} min)")

        # Save full ranking
        rank_data = {
            'checkpoint': CKPT,
            'n': len(ranked),
            'ranked': ranked,
        }
        with open(FULL_RANK_JSON, 'w') as f:
            json.dump(rank_data, f, ensure_ascii=False)
        print(f"💾 Saved full ranking to {FULL_RANK_JSON}")

    # ── Step 2: Build GLARE lookup ──────────────────────────
    glare_map = {}
    for i, r in enumerate(ranked):
        smi_norm = norm(r['smiles'])
        glare_map[smi_norm] = {
            'glare_rank': i + 1,
            'glare_score': r.get('glare_select_prob', 0.0),
            'glare_uncertainty': r.get('glare_uncertainty', 0.0),
        }

    # ── Step 3: Load pool CSV & merge ────────────────────────
    print(f"\nLoading pool CSV for CarsiScore data...")
    pool_df = pd.read_csv(POOL_CSV)

    rows = []
    for i, row in pool_df.iterrows():
        smi_norm = norm(row['smiles'])
        if not smi_norm:
            continue
        g = glare_map.get(smi_norm, {})
        rows.append({
            'ID': row['ID'],
            'smiles': row['smiles'],
            'canonical_smiles': smi_norm,
            'CarsiScore': float(row['CarsiScore']),
            'RTMScore': float(row['RTMScore']),
            'similarity': float(row['similarity']),
            'MW': float(row['MW']),
            'TPSA': float(row['TPSA']),
            'LogP': float(row['LogP']),
            'LogS': float(row.get('LogS', 0)),
            'Cluster_ID': row.get('Cluster ID', ''),
            'Algorithm': row.get('Algorithm', ''),
            'glare_score': g.get('glare_score', np.nan),
            'glare_rank': g.get('glare_rank', np.nan),
            'glare_uncertainty': g.get('glare_uncertainty', np.nan),
        })

    df = pd.DataFrame(rows)
    n_matched = df['glare_score'].notna().sum()
    print(f"Merged: {len(df)} rows, {n_matched}/{len(df)} matched GLARE scores")

    # ── Step 4: Normalize scores ────────────────────────────
    carsi_col = df['CarsiScore'].values  # more negative = better
    glare_col = df['glare_score'].values  # higher = better

    carsi_min, carsi_max = np.nanmin(carsi_col), np.nanmax(carsi_col)
    glare_min, glare_max = np.nanmin(glare_col), np.nanmax(glare_col)

    # CarsiScore: map [-14.5 (best) → 1.0] ... [-1 (worst) → 0.0]
    df['carsi_norm'] = (carsi_max - df['CarsiScore']) / (carsi_max - carsi_min)

    # GLARE score: map [0 (worst) → 0.0] ... [1 (best) → 1.0]
    df['glare_norm'] = (df['glare_score'] - glare_min) / (glare_max - glare_min)

    # Weighted: 0.3 * CarsiScore + 0.7 * GLARE
    df['combined_03_07'] = 0.3 * df['carsi_norm'] + 0.7 * df['glare_norm']

    print(f"CarsiScore  range: [{carsi_min:.3f}, {carsi_max:.3f}]")
    print(f"GLARE score range: [{glare_min:.4f}, {glare_max:.4f}]")
    print(f"Combined   range: [{df['combined_03_07'].min():.4f}, {df['combined_03_07'].max():.4f}]")

    # ── Step 5: Sort & select top 100 ────────────────────────
    df_carsi = df.sort_values('CarsiScore', ascending=True).head(100).copy()
    df_carsi['rank'] = range(1, 101)
    df_carsi['method'] = 'CarsiScore'

    df_glare = df.sort_values('glare_score', ascending=False).head(100).copy()
    df_glare['rank'] = range(1, 101)
    df_glare['method'] = 'GLARE_E33'

    df_combined = df.sort_values('combined_03_07', ascending=False).head(100).copy()
    df_combined['rank'] = range(1, 101)
    df_combined['method'] = 'Weighted_0.3Carsi_0.7GLARE'

    # ── Step 6: Output columns ───────────────────────────────
    out_cols = [
        'rank', 'ID', 'smiles', 'canonical_smiles',
        'CarsiScore', 'carsi_norm',
        'glare_score', 'glare_norm', 'glare_rank', 'glare_uncertainty',
        'combined_03_07',
        'RTMScore', 'similarity', 'MW', 'TPSA', 'LogP', 'LogS',
        'Cluster_ID', 'Algorithm', 'method',
    ]

    # ── Step 7: Write CSVs ───────────────────────────────────
    out_carsi = OUT_DIR / 'top100_carsiscore.csv'
    out_glare = OUT_DIR / 'top100_glare_e33.csv'
    out_combined = OUT_DIR / 'top100_weighted_03carsi_07glare.csv'

    df_carsi[out_cols].to_csv(out_carsi, index=False)
    df_glare[out_cols].to_csv(out_glare, index=False)
    df_combined[out_cols].to_csv(out_combined, index=False)

    print(f"\n{'='*80}")
    print(f"  ✅ 3 CSVs written:")
    print(f"     {out_carsi}")
    print(f"     {out_glare}")
    print(f"     {out_combined}")
    print(f"{'='*80}")

    # ── Step 8: Summary stats ────────────────────────────────
    print(f"\n{'─'*80}")
    print(f"  Top 100 Summary")
    print(f"{'─'*80}")

    for label, d in [('CarsiScore', df_carsi), ('GLARE E33', df_glare), ('Weighted 0.3/0.7', df_combined)]:
        print(f"\n  📊 {label} Top 100:")
        print(f"     CarsiScore: {d['CarsiScore'].min():.2f} ~ {d['CarsiScore'].max():.2f} (mean {d['CarsiScore'].mean():.2f})")
        print(f"     GLARE score: {d['glare_score'].min():.4f} ~ {d['glare_score'].max():.4f} (mean {d['glare_score'].mean():.4f})")
        print(f"     GLARE rank:  #{int(d['glare_rank'].min())} ~ #{int(d['glare_rank'].max())} (mean #{d['glare_rank'].mean():.0f})")
        print(f"     RTMScore:    {d['RTMScore'].min():.1f} ~ {d['RTMScore'].max():.1f} (mean {d['RTMScore'].mean():.1f})")
        print(f"     MW:          {d['MW'].min():.1f} ~ {d['MW'].max():.1f} (mean {d['MW'].mean():.1f})")

    # ── Step 9: Overlap analysis ─────────────────────────────
    print(f"\n{'─'*80}")
    print(f"  Overlap Between Top 100 Lists")
    print(f"{'─'*80}")
    carsi_ids = set(df_carsi['ID'])
    glare_ids = set(df_glare['ID'])
    combined_ids = set(df_combined['ID'])

    print(f"  CarsiScore ∩ GLARE:      {len(carsi_ids & glare_ids)} molecules")
    print(f"  CarsiScore ∩ Combined:   {len(carsi_ids & combined_ids)} molecules")
    print(f"  GLARE ∩ Combined:        {len(glare_ids & combined_ids)} molecules")
    print(f"  All 3 agree:             {len(carsi_ids & glare_ids & combined_ids)} molecules")

    # Overlap table
    overlap_carsi_glare = sorted(carsi_ids & glare_ids)
    if overlap_carsi_glare:
        overlap_df = df[df['ID'].isin(overlap_carsi_glare)].sort_values('combined_03_07', ascending=False)
        print(f"\n  🎯 Molecules in BOTH CarsiScore Top 100 AND GLARE Top 100 ({len(overlap_carsi_glare)} total):")
        for _, r in overlap_df.iterrows():
            c_rank = df_carsi[df_carsi['ID'] == r['ID']]['rank'].values[0]
            g_rank = df_glare[df_glare['ID'] == r['ID']]['rank'].values[0]
            print(f"     ID={r['ID']:>6s}  Carsi=#{int(c_rank):<4d}  GLARE=#{int(g_rank):<4d}  "
                  f"CarsiScore={r['CarsiScore']:.2f}  GLARE={r['glare_score']:.4f}  RTM={r['RTMScore']:.1f}")

    print(f"\n✅ Done.")


if __name__ == '__main__':
    main()
