#!/usr/bin/env python3
"""Batch GLARE inference: rank 2134 MolFactory molecules with top 15 checkpoints."""
import sys, json, os, time
os.environ.setdefault('PYTHONPATH', '/data/ye/e-drug-lab/backend')
os.environ['CUDA_VISIBLE_DEVICES'] = '5'
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

from app.pipelines.vav1_rl.glare_gnn_adapter import query
from pathlib import Path

OUTPUT_DIR = Path('/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/molfactory_screen_20260706')

# Load pool (original 2134)
with open(OUTPUT_DIR / 'pool_smiles.json') as f:
    pool_smiles = json.load(f)
print(f'Pool: {len(pool_smiles)} molecules')

# Load checkpoint list
with open(OUTPUT_DIR / 'top_checkpoints.json') as f:
    checkpoints = json.load(f)
print(f'Checkpoints to run: {len(checkpoints)}')

# Skip already-done ones
DONE = {'ranked_e32_grpo_sup.json', 'ranked_e30_sup_5e4.json'}
results = {}
errors = []

for i, ck in enumerate(checkpoints):
    label = f'{ck["exp"]}_{ck["config"]}'
    out_file = OUTPUT_DIR / f'ranked_{label}.json'

    if out_file.name in DONE or out_file.exists():
        print(f'\n[{i+1}/{len(checkpoints)}] SKIP {label} (already done)')
        continue

    ckpt_path = ck['ckpt_path']
    if not Path(ckpt_path).exists():
        print(f'\n[{i+1}/{len(checkpoints)}] SKIP {label} (ckpt not found: {ckpt_path})')
        continue

    print(f'\n[{i+1}/{len(checkpoints)}] {label} (Combined={ck["r1_combined"]:.4f})')
    print(f'  Checkpoint: {Path(ckpt_path).parent.name}/{Path(ckpt_path).name}')

    t0 = time.time()
    try:
        result = query(ckpt_path, pool_smiles, ensemble_size=3)
        elapsed = time.time() - t0

        if result.get('ok', False) or 'ranked' in result:
            ranked = result.get('ranked', [])
            with open(out_file, 'w') as f:
                json.dump({'checkpoint': label, 'ckpt_path': ckpt_path,
                          'n': len(ranked), 'ranked': ranked}, f, indent=2)
            print(f'  ✅ {len(ranked)} molecules ranked in {elapsed:.0f}s → {out_file.name}')
            results[label] = len(ranked)
        else:
            print(f'  ❌ Error: {result.get("error", str(result)[:200])}')
            errors.append(label)
    except Exception as e:
        elapsed = time.time() - t0
        print(f'  ❌ Exception after {elapsed:.0f}s: {e}')
        errors.append(label)

print(f'\n{"="*60}')
print(f'Done! Success: {len(results)}, Errors: {len(errors)}')
if errors:
    print(f'Errors: {errors}')
print(f'Results in: {OUTPUT_DIR}')
