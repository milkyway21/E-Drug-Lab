---
name: desmond-md-campaign
description: End-to-end Schrödinger Desmond campaign workflow for corrected-pose audits, late-trajectory medoid full-system CMS extraction, resumable multi-GPU 2+50 ns or 2+200 ns production, hard trajectory validation, SEA extraction, pocket/contact-aware A/B/C/D classification, incremental candidate merging, and publication RMSD plates. Use when an agent must prepare, launch, recover, monitor, validate, analyze, rank, or plot a protein-ligand MD campaign after docking/IFD, especially membrane systems or campaigns with many ligands; do not use for FEP or DiffDynamic sampling.
---

# Desmond MD Campaign

Operate decision-grade Desmond campaigns without treating a submitted job, a 190 ns partial trajectory, or a readable final CMS as completion.

## Route The Request

1. Use the registered `schrodinger_md_submit` / `schrodinger_md_status` tools for `dry_prep`, smoke, and supported short jobs.
2. Use this skill's scripts for corrected-pose or medoid starts, multi-ligand queues, full 200 ns validation, SEA, unified analysis, and figures.
3. Read [references/campaign-contract.md](references/campaign-contract.md) before preparing or submitting production.
4. Read [references/script-index.md](references/script-index.md) only when selecting a bundled portable implementation.

## Hard Gates

- Require a configured, readable `$SCHRODINGER` for Desmond. Do not create or activate a conda environment for MD or hard-code an installation path.
- Require explicit user confirmation before submitting new 50 ns or 200 ns production jobs. Read-only checks, analysis, plotting, and recovery of already authorized queues do not need a new confirmation.
- Never kill or reassign an existing GPU process unless the user explicitly requests it and the exact process ownership is known.
- Start long MD from a validated corrected pose or a late-pose medoid, never from a known frame-mismatched CMS.
- Preserve the full frame system: protein, ligand, membrane, solvent, ions, cofactors, box, component order, formal charge, and force-field CTs.
- Count 200 ns complete only when the production trajectory covers at least 199.998 ns with continuous times, expected frame spacing, a readable final CMS, and `topo.check_consistency` passing.
- Write each retry to `attempt_XX`; never overwrite another attempt or an older campaign.

## Workflow

### 1. Inspect And Stage

Record molecule IDs, source pose/CMS, source trajectory, ligand ASL, protein ASL, pocket ASL, protocol, GPU set, trajectory interval, and output root. Create a new batch directory.

For late-pose starts, prepare an input CSV and run:

```bash
"$SCHRODINGER/run" python3 scripts/extract_medoid_cms.py \
  --input-csv medoid_inputs.csv \
  --output-root 03_systems/<batch> \
  --ligand-asl '<ligand_asl>' \
  --late-start-ns 40 \
  --cluster-cutoff-a 2.0
```

Run it from this skill directory or use absolute script paths. The CSV contract is in [references/campaign-contract.md](references/campaign-contract.md).

### 2. Submit Or Recover

Prefer the platform tool for supported single jobs. For a multi-GPU campaign, adapt the tested queue/watchdog pair under `scripts/hsd17b13_reference/` to a new project config; replace every target ID, root, ASL, host, GPU, protocol, and completion flag before launch.

Use `prod_2ns_eq_50ns.msj` for screening and `prod_2ns_eq_200ns.msj` for long production. These templates are bundled under `scripts/protocols/`.

Launch persistent campaign workers with a user service or another terminal-independent supervisor. Keep one Desmond job per physical GPU. A watchdog may retry only after both the GPU process disappears and files show no progress for the configured stall period.

### 3. Validate

Validate each finished CMS/DTR pair with the Schrödinger Python runtime:

```bash
"$SCHRODINGER/run" python3 scripts/validate_desmond_trajectory.py \
  --cms /abs/path/<ID>_202ns-out.cms \
  --trajectory /abs/path/<ID>_6_trj \
  --minimum-ns 200 \
  --expected-interval-ps 200 \
  --output /abs/path/attempt_01/attempt_validation.json
```

Summarize a campaign without inferring completion from process names:

```bash
python3 scripts/campaign_status.py \
  --trajectory-root 04_trajectories/<batch> \
  --ids-file 05_analysis/<batch>/selected_ids.txt \
  --csv 05_analysis/<batch>/md_queue_status.csv
```

### 4. Extract SEA

Run only on hard-validated attempts:

```bash
"$SCHRODINGER/run" python3 scripts/run_sea.py \
  --trajectory-root 04_trajectories/<batch> \
  --output-root 05_analysis/<batch>/sea \
  --ids <ID1> <ID2> \
  --jobs 2 \
  --protein-asl protein \
  --ligand-asl '<ligand_asl>' \
  --official-report
```

For campaigns whose validated CMS/DTR files do not use `attempt_XX` layout, provide a
portable CSV instead of writing a target-specific SEA script:

```bash
"$SCHRODINGER/run" python3 scripts/run_sea.py \
  --sources-csv sea_sources.csv \
  --output-root 05_analysis/<batch>/sea \
  --protein-asl '<protein_asl>' \
  --ligand-asl '<ligand_asl>' \
  --jobs 2 --official-report
```

`sea_sources.csv` columns are `molecule_id,cms,trajectory`; relative paths resolve from
the CSV directory. This is the preferred adapter for pilot and legacy campaigns.

### 5. Analyze And Rank

Use pocket retention and direct contacts before absolute ligand RMSD:

```bash
"$SCHRODINGER/run" python3 scripts/analyze_md200.py \
  --ids <ID1> <ID2> \
  --trajectory-root 04_trajectories/<batch> \
  --sea-root 05_analysis/<batch>/sea \
  --manifest 05_analysis/<batch>/selection_manifest.csv \
  --protein-asl '<protein_asl>' \
  --ligand-asl '<ligand_asl>' \
  --target-label '<target_id>' \
  --outdir 05_analysis/<batch>/final_200ns
```

Interpret classes as:

- `A_pose_retained`: original pocket pose retained and late trajectory converged.
- `B_contact_retained_rearrangement`: stable replacement pose with retained or new supported contacts.
- `C_inconclusive`: late transition, conflicting evidence, alignment issue, or insufficient convergence.
- `D_pose_failure`: pocket exit or clear pose failure.

Do not promote a high numeric score over an unfavorable class. Independent repeats remain desirable for borderline candidates.

### 6. Plot

Generate the portrait-A4 5-row by 4-column plate:

```bash
"$SCHRODINGER/run" python3 scripts/plot_md200_plate.py \
  --traces 05_analysis/<batch>/final_200ns/md200_traces.csv \
  --decisions 05_analysis/<batch>/final_200ns/md200_decision_table.csv \
  --output 05_analysis/<batch>/figures/md200_plate
```

The plot uses 5 pt ticks, 7 pt molecule IDs, A/B/C title colors, a white page, pale-blue axes, one adaptive shared axis per molecule, and vector PDF plus 600 dpi PNG output.

## Bundled Implementations

- `scripts/extract_medoid_cms.py`: portable full-system medoid extraction and hard topology/geometry QC.
- `scripts/validate_desmond_trajectory.py`: portable CMS/DTR completion validator.
- `scripts/campaign_status.py`: portable attempt inventory.
- `scripts/run_sea.py`: portable validated-trajectory SEA runner.
- `scripts/analyze_md200.py`: portable pocket/contact-aware 200 ns decision analysis.
- `scripts/plot_md200_plate.py`: portable 20-panel publication plot.
- Target-specific reference implementations are not portable runners. Do not copy their constants, paths, selectors, or IDs into another task.

## Completion Report

Report the exact completed/total count, validated production time and frame count, active GPU mapping, retry count, remaining ETA, class distribution, output paths, and any unresolved C-class evidence. Never report planned jobs as completed.

When this campaign is a funnel stage, hand the validated counts, plots, SEA paths, and
decision table to the `reporting` umbrella. It appends one MD section to the single
`AUTOPILOT_REPORT` set; do not create a separate stage DOCX/PDF.
