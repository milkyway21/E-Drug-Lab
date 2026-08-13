---
name: molecular-dynamics
description: Use to route validated Desmond MD and trajectory QC.
---

# Molecular Dynamics

Route corrected-pose Desmond system checks, short and long production, recovery, trajectory
validation, SEA, figures, and evidence-grounded stability classification.

## When to Use

Use after validated docking/MMGBSA complex selection when explicit resources and production
authorization are available.

## Prerequisites

- Corrected-pose complex or validated full-system CMS with protein/ligand lineage.
- Explicit MSJ, duration, frame interval, ASLs, ensemble, force field, and system composition.
- Approved GPU/host allocation, disk budget, monitor cadence, retry policy, and output root.

## How to Run

Use registered submit/status tools or a manifest command for orchestration. Standalone users
invoke native `multisim -m protocol.msj -o output.cms input.cms`, then validate CMS/DTR.

## Quick Reference

| Phase | Required evidence | Gate |
| --- | --- | --- |
| System | Full component and pose continuity | Build QC |
| Short MD | Declared duration and interval | Hard trajectory validation |
| Long MD | Short-MD-qualified start | Independent long-run validation |
| Analysis | Official SEA and pocket/contact QC | Valid CMS/DTR only |

## Procedure

1. Validate pose frame, full-system composition, protocol, and resource ownership.
2. Dry-prepare or reuse a validated CMS and isolate one attempt per job/GPU.
3. Launch native multisim, record exact JobDJ/process IDs, and monitor artifact progress.
4. Validate actual duration, frames, interval, continuity, topology, and normal exit.
5. Run SEA and pocket/contact analysis, classify outcomes, and append one report section.

## Concrete Operation Procedure

Resolve the Desmond route from the registry before production:

```bash
masld-agent platform-catalog --id sz.desmond --json
masld-agent schrodinger-status
masld-agent funnel validate --manifest "$MANIFEST" --stage H7
```

Use registered `schrodinger_md_submit` with `mode=dry_prep`, inspect the returned job
directory and protocol, then submit `mode=short` only with explicit confirmation. For
direct campaigns resolve `sz.bin.multisim` and `sz.bin.run` with `platform-resolve`, set
both CUDA variables, record job IDs, validate CMS/DTR duration, run SEA, and append the
MD section. Dry prep, smoke, and readable CMS are not production completion.

This main skill routes the short-to-long MD handoff and keeps GPU jobs resumable.

## Child skills

- `funnel-desmond-short-md` for H8 short MD
- `funnel-desmond-long-md` for H9 long MD
- `dd-md-desmond` for cross-cutting Desmond operations
- `dd-md-desmond-sea-qc` for trajectory/SEA QC
- `desmond-md-campaign` for campaign monitoring and analysis
- `desmond-membrane-md-ops` for membrane-specific setup

## Gate

Correct pose frames before membrane/system setup, validate job ownership and backend state,
then validate trajectories, RMSD/contacts, and report figures. Do not kill a live task job
because a heartbeat is old; inspect its process group and scheduler state first.

## Universal Manifest Invocation

This skill is reusable for any target and pose when the manifest declares the clean
complex/CMS inputs, simulation phase, GPU/CPU policy, expected trajectories and QC
artifacts, validation rules, reporting location, and explicit argv `command` or
ordered `steps`. Do not infer durations or resource ownership.

```bash
bash scripts/run_skill.sh --skill molecular-dynamics --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill molecular-dynamics --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill molecular-dynamics --manifest MANIFEST --status
```

After checking job ownership and GPU placement, authorize compute and recovery:

```bash
bash scripts/run_skill.sh --skill molecular-dynamics --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill molecular-dynamics --manifest MANIFEST --resume --execute --confirm
```

Keep every attempt and trajectory under `campaign_root`; use validated trajectory,
RMSD/contact, normal-exit, and report artifacts as the completion evidence.

## Generic Desmond Method

The MD manifest declares a corrected-pose complex or CMS, molecule ID, protein and ligand
ASL, system-build status, MSJ protocol, production duration, frame interval, GPU/host,
attempt root, validator output, SEA output, analysis output, and aggregate report section.
Durations such as 10, 50, and 200 ns are policy choices supplied by the manifest, not
hidden defaults. Resolve `sz.bin.run` and `sz.bin.multisim` from the platform registry
before launch; do not create or activate the DiffDynamic conda environment for Desmond.

The generic sequence is: validate pose frame and full-system components, prepare or reuse
CMS, submit one job per approved GPU, record exact JobDJ IDs, monitor only those jobs,
validate continuous CMS/DTR duration and frame spacing, run official SEA, analyze pocket
retention and contacts, classify outcomes, generate figures, and append one MD section
to the aggregate report. A submitted job, readable CMS, or partial trajectory is not
completion.

Recovery is artifact-first: reuse complete build/equilibration/production/SEA outputs,
resume from a readable checkpoint, and create a new `attempt_XX` only for a failed unit.
Never rebuild valid upstream systems because a monitor or report process restarted. Every
final decision states actual nanoseconds, frame count, interval, GPU mapping, retries,
validation status, limitations, and relative output paths.

## Standalone Command-Line Procedure

Use native Desmond commands with explicit task variables when no manifest launcher is
available. The MSJ protocol, CMS, ASLs, duration, interval, and GPU are inputs; this
skill does not invent them.

```bash
SCHRODINGER="${SCHRODINGER:-}"
MULTISIM="${MULTISIM:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  MULTISIM="${MULTISIM:-$(masld-agent platform-resolve --id sz.bin.multisim)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
MULTISIM="${MULTISIM:-$SCHRODINGER/utilities/multisim}"
CMS="$(realpath inputs/validated_system.cms)"
MSJ="$(realpath inputs/prod_protocol.msj)"
OUT="$(realpath -m outputs/md/attempt_01)"
mkdir -p "$OUT"
JOBNAME="${JOBNAME:-md}"
FINAL_CMS="$OUT/${JOBNAME}-out.cms"
CUDA_VISIBLE_DEVICES="${GPU_ID:?approved GPU}" \
SCHRODINGER_CUDA_VISIBLE_DEVICES="${GPU_ID}" \
  "$MULTISIM" -WAIT -HOST "${HOST_SPEC:-localhost}" -maxjob 1 -JOBNAME "$JOBNAME" \
  -m "$MSJ" -o "$FINAL_CMS" "$CMS"
```

Validate the CMS/DTR pair with the shared campaign validator before SEA, then use the
native SEA adapter and the declared protein/ligand ASLs. A readable CMS or a submitted
job is not a completed simulation; report observed trajectory time and frame spacing.

## Pitfalls

- A submitted job, readable CMS, stopped PID, or duration-like filename is not completion.
- Do not start from a frame-mismatched pose or drop membrane, solvent, ions, or cofactors.
- Do not rerun valid production because monitoring, SEA, plotting, or reporting restarted.
- Never kill broad process patterns; verify exact job ownership and artifact progress first.

## Verification

Require input/protocol hashes, component QC, GPU and job IDs, attempt lineage, normal exit,
readable CMS/DTR, observed nanoseconds and frame interval, monotonic/topology checks, SEA rows,
pocket/contact classification, figures, failed cases, and relative report paths.
