---
name: "desmond-membrane-md-ops"
description: "Desmond membrane MD operations: POPC system build QC, GPU parallel launch rules, launcher templates. Invoke when running membrane MD on multi-GPU machines, building POPC systems, or parallelizing Desmond jobs."
---

# Desmond Membrane MD Operations

Operational knowledge for running **Schrödinger Desmond** membrane MD
campaigns on multi-GPU Linux machines. Covers system build QC and
GPU-parallel launch patterns. Complementary to `dd-md-desmond` (which
covers pose correction, SEA analysis, and triage heuristics) and the
funnel skills (which cover stage orchestration).

## When to invoke

- Building POPC membrane systems and need a build-QC checklist
- Launching multiple Desmond MD jobs in parallel across GPUs
- User says "reuse the existing wrapper / don't hand-write MSJ"
- Need a reliable launcher script template

## 1. Reuse verified protocol templates — do NOT hand-write MSJ

Prefer templates already validated in the campaign repo. Look in
`<campaign_root>/HSD17B13_MD/scripts/protocols/` or `scripts/protocols/`.

| Template | Purpose | Modification rule |
|----------|---------|-------------------|
| `build_membrane_system.msj` | POPC membrane build via `desmond:auto` (3 stages). Output: `*_3-out.cms` | **Do not modify.** SPC water, 0.15 M NaCl, OPLS4. |
| `prod_2ns_eq_50ns.msj` | Standard 2 ns eq + 50 ns production (5 simulate blocks) | Short pilot: change ONLY `time = 50000.0` → target (e.g. `10000.0`). NEVER touch equilibration stages. |

**After modifying production time, verify:**
- 5 `simulate {` blocks total
- 100 ps Brownian (10K) unchanged
- 500 ps NPT strong restraints unchanged
- 500 ps NPT weaker restraints unchanged
- 1000 ps NPT unrestrained equilibration unchanged
- 1× production with the new time value

## 2. Post-build CMS composition QC (required)

Run with `$SCHRODINGER/run python3` + `schrodinger.structure`:

```python
from schrodinger import structure
from collections import Counter

st = next(structure.StructureReader("build_XXX_3/build_XXX_3-out.cms"))
print(f"Total atoms: {st.atom_total}")

popc = sum(1 for r in st.residue if r.pdbres.strip() == 'POPC')
spc  = sum(1 for r in st.residue if r.pdbres.strip() in ('SPC','TIP3','HOH','WAT','SPW'))
na   = sum(1 for r in st.residue if r.pdbres.strip() in ('NA','SOD','Na','NA+'))
cl   = sum(1 for r in st.residue if r.pdbres.strip() in ('CL','CLA','Cl','CL-'))
nad  = sum(1 for r in st.residue if r.pdbres.strip() == 'NAD')

# Ligand = non-standard residue not in AA/lipid/water/ion/cofactor
standard_aa = set('ALA ARG ASN ASP CYS GLN GLU GLY HIS HIE HID HIP ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split())
lipid_ion_water = {'POPC','SPC','NA','CL','NAD','TIP3','HOH','WAT','SPW','SOD','CLA'}
lig_res = [r for r in st.residue if r.pdbres.strip() not in standard_aa and r.pdbres.strip() not in lipid_ion_water]
print(f"Ligand residues: {len(lig_res)} ({Counter(r.pdbres.strip() for r in lig_res)})")

for chain in st.chain:
    nres = sum(1 for _ in chain.residue)
    natoms = sum(1 for _ in chain.atom)
    print(f"  Chain {chain.name}: {nres} res, {natoms} atoms")
```

### HSD17B13 dimer + POPC reference (8G9V, chains A+B, ~284 res each)

| Component | Typical | Notes |
|-----------|---------|-------|
| Total atoms | ~83,000 | |
| POPC | ~177 | ±1 normal between ligands |
| SPC water | ~16,700 | |
| Na+ | ~46 | |
| Cl- | ~55–60 | Depends on system charge |
| NAD cofactor | 2 | One per chain |
| Ligand | 1 (UNK) | |
| Protein chains | 2 (A, B) | 284 res each |

Small differences (±1 lipid, ±few ions) between ligands are normal.

## 3. GPU parallel launch rules

### Always do
1. Check `nvidia-smi` first; pick idle GPUs only.
2. Set **both** `CUDA_VISIBLE_DEVICES=N` AND `SCHRODINGER_CUDA_VISIBLE_DEVICES=N`.
3. Use a **standalone shell-script launcher per job** — write the file,
   chmod +x, run it. Never fold multi-line commands into a single
   terminal call.
4. Submit with `nohup launcher.sh &`; each job has its own log file.
5. Verify placement ~30 s after launch:
   - Log contains `JobId: ...` line
   - Target GPU memory rises in `nvidia-smi`
   - Other GPUs unaffected
6. Use `-WAIT -LOCAL -HOST localhost -maxjob 1` for controlled single-GPU runs.

### Pitfalls (learned the hard way)
- **Inline multi-line commands with backslashes fail in `terminal()`** —
  backslashes get passed as literal arguments, `cd` misses its
  separator, etc. Always use a launcher script file.
- **Never assume GPU 0 is idle** — always check `nvidia-smi`.
- **Never share a GPU between Desmond jobs** — they will contend and
  slow down or crash.

## 4. Launcher script template

```bash
#!/bin/bash
# Launch <MOL_ID> <NS> ns production MD on GPU $GPU_ID
# Input: final membrane CMS from build stage 3
# Protocol: prod_<NS>ns.msj (derived from prod_2ns_eq_50ns.msj)

export CUDA_VISIBLE_DEVICES=$GPU_ID
export SCHRODINGER_CUDA_VISIBLE_DEVICES=$GPU_ID
export SCHRODINGER=/opt/schrodinger2023-3

MOL=<MOL_ID>
WD=/absolute/path/to/md_dir/$MOL
INPUT_CMS=$WD/build_${MOL}_3/build_${MOL}_3-out.cms
LOG=$WD/prod_multisim.log
JOBNAME=PREFIX_${MOL}_<NS>ns

cd "$WD"

echo "Launching $MOL <NS>ns MD on GPU $GPU_ID at $(date)" > "$LOG"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}" >> "$LOG"
echo "SCHRODINGER_CUDA_VISIBLE_DEVICES=${SCHRODINGER_CUDA_VISIBLE_DEVICES}" >> "$LOG"
echo "INPUT_CMS=${INPUT_CMS}" >> "$LOG"
echo "JOBNAME=${JOBNAME}" >> "$LOG"
echo "" >> "$LOG"

"$SCHRODINGER/utilities/multisim" \
  -HOST localhost \
  -maxjob 1 \
  -JOBNAME "$JOBNAME" \
  -m prod_<NS>ns.msj \
  "$INPUT_CMS" \
  -mode umbrella \
  -WAIT \
  -LOCAL \
  >> "$LOG" 2>&1

RC=$?
echo "" >> "$LOG"
echo "Finished with exit code $RC at $(date)" >> "$LOG"
exit $RC
```

Pattern adapted from HSD17B13_MD `05_phaseA_6gpu_queue.py` (which also
uses `numactl --physcpubind` for CPU pinning — optional for small
campaigns, recommended for 4+ GPU setups).
