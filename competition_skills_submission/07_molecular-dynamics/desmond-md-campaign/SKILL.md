---
name: desmond-md-campaign
description: End-to-end Schrödinger Desmond campaign workflow for corrected-pose audits, late-trajectory medoid full-system CMS extraction, resumable multi-GPU 2+50 ns or 2+200 ns production, hard trajectory validation, SEA extraction, pocket/contact-aware A/B/C/D classification, incremental candidate merging, and publication RMSD plates. Use when an agent must prepare, launch, recover, monitor, validate, analyze, rank, or plot a protein-ligand MD campaign after docking/IFD, especially membrane systems or campaigns with many ligands; do not use for FEP or DiffDynamic sampling.
---

# Desmond MD Campaign

## Concrete Operation Procedure

Use registered Desmond tools for supported jobs and registry-resolved scripts for analysis:

```bash
masld-agent platform-catalog --id sz.desmond --json
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
MULTISIM="$(masld-agent platform-resolve --id sz.bin.multisim)"
"$RUN" python3 skills/molecular-dynamics/desmond-md-campaign/scripts/validate_desmond_trajectory.py --help
"$RUN" python3 skills/molecular-dynamics/desmond-md-campaign/scripts/run_sea.py --help
```

For each molecule validate corrected-pose lineage, run `dry_prep`, choose the declared
duration/MSJ, submit one job per approved GPU, record job/attempt IDs, and monitor only
those IDs. Run validation with explicit duration and interval, then SEA and analysis;
reuse readable checkpoints and create a new attempt only for a failed unit.

Operate decision-grade Desmond campaigns without treating a submitted job, a 190 ns partial trajectory, or a readable final CMS as completion.

## Route The Request

1. Use the registered `schrodinger_md_submit` / `schrodinger_md_status` tools for `dry_prep`, smoke, and supported short jobs.
2. Use this skill's scripts for corrected-pose or medoid starts, multi-ligand queues, full 200 ns validation, SEA, unified analysis, and figures.
3. Read [references/campaign-contract.md](references/campaign-contract.md) before preparing or submitting production.
4. Read [references/script-index.md](references/script-index.md) only when selecting a bundled portable implementation.

## Hard Gates

- Require registry resolution for `sz.bin.run`, `sz.bin.multisim`, and `sz.bin.jobcontrol`. Do not create or activate a conda environment for MD or hard-code an installation path.
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
"$RUN" python3 scripts/extract_medoid_cms.py \
  --input-csv medoid_inputs.csv \
  --output-root 03_systems/<batch> \
  --ligand-asl '<ligand_asl>' \
  --late-start-ns 40 \
  --cluster-cutoff-a 2.0
```

Run it from this skill directory or use absolute script paths. The CSV contract is in [references/campaign-contract.md](references/campaign-contract.md).

### 2. Submit Or Recover

Prefer the platform tool for supported single jobs. For a multi-GPU campaign, use the
manifest-declared queue/watchdog adapter and replace every task-specific ID, root, ASL,
host, GPU, protocol, and completion contract before launch. Do not copy a prior target's
queue script as a scientific default.

Use `prod_2ns_eq_50ns.msj` for screening and `prod_2ns_eq_200ns.msj` for long production. These templates are bundled under `scripts/protocols/`.

Launch persistent campaign workers with a user service or another terminal-independent supervisor. Keep one Desmond job per physical GPU. A watchdog may retry only after both the GPU process disappears and files show no progress for the configured stall period.

### 3. Validate

Validate each finished CMS/DTR pair with the Schrödinger Python runtime:

```bash
"$RUN" python3 scripts/validate_desmond_trajectory.py \
  --cms "$CAMPAIGN_ROOT/04_trajectories/<ID>_202ns-out.cms" \
  --trajectory "$CAMPAIGN_ROOT/04_trajectories/<ID>_6_trj" \
  --minimum-ns 200 \
  --expected-interval-ps 200 \
  --output "$CAMPAIGN_ROOT/05_analysis/attempt_01/attempt_validation.json"
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
"$RUN" python3 scripts/run_sea.py \
  --run-launcher "$RUN" \
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
"$RUN" python3 scripts/run_sea.py \
  --run-launcher "$RUN" \
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
"$RUN" python3 scripts/analyze_md200.py \
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
"$RUN" python3 scripts/plot_md200_plate.py \
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

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill desmond-md-campaign --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill desmond-md-campaign --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill desmond-md-campaign --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill desmond-md-campaign --manifest MANIFEST --resume --execute --confirm
```

The manifest explicitly supplies the existing medoid/system/validation/SEA/analysis
commands, duration, ASL selectors, resource allocation, and output contracts. The
campaign skill never chooses a target-specific protocol, ligand selector, GPU count,
trajectory name, or completion marker. Use relative paths in reports; executable
locations come from the platform registry at runtime.

## Standalone Command-Line Procedure

The bundled campaign scripts are portable assets inside this skill. Set `SKILLS_ROOT` to
the installed shared-skill root and resolve Schrödinger from `SCHRODINGER` or your local
registry; no project checkout path is assumed.

```bash
SCHRODINGER="${SCHRODINGER:-}"
RUN="${RUN:-}"
MULTISIM="${MULTISIM:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  RUN="${RUN:-$(masld-agent platform-resolve --id sz.bin.run)}"
  MULTISIM="${MULTISIM:-$(masld-agent platform-resolve --id sz.bin.multisim)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
RUN="${RUN:-$SCHRODINGER/run}"
MULTISIM="${MULTISIM:-$SCHRODINGER/utilities/multisim}"
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
CMS="$(realpath inputs/validated_system.cms)"
MSJ="$(realpath inputs/prod_2ns_eq_50ns.msj)"
OUT="$(realpath -m outputs/md/attempt_01)"
mkdir -p "$OUT"
JOBNAME="${JOBNAME:-md_campaign}"
FINAL_CMS="$OUT/${JOBNAME}-out.cms"
CUDA_VISIBLE_DEVICES="${GPU_ID:?approved GPU}" \
SCHRODINGER_CUDA_VISIBLE_DEVICES="${GPU_ID}" \
  "$MULTISIM" -WAIT -HOST "${HOST_SPEC:-localhost}" -maxjob 1 -JOBNAME "$JOBNAME" \
  -m "$MSJ" -o "$FINAL_CMS" "$CMS"
"$RUN" python3 \
  "$SKILLS_ROOT/molecular-dynamics/desmond-md-campaign/scripts/validate_desmond_trajectory.py" \
  --cms "$OUT"/*out.cms --trajectory "$OUT"/*trj \
  --minimum-ns "${MINIMUM_NS:?declared duration}" \
  --expected-interval-ps "${INTERVAL_PS:?declared recording interval}" \
  --output "$OUT/validation.json"
```

Run `run_sea.py`, `analyze_md200.py`, and plotting only after `validation.json` says
`valid=true`. Preserve corrected-pose lineage, ASLs, attempt ID, active GPU, observed
frames, and all failed rows.
