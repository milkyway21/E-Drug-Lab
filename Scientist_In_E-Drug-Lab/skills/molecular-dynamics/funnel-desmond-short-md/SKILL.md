---
name: funnel-desmond-short-md
description: Use to run the corrected-pose Desmond short-MD gate.
---

# H8 Short MD

Run a manifest-defined short Desmond production from a corrected pose, validate the real
trajectory, and apply official SEA before deciding whether a candidate advances.

## When to Use

Use after validated MMGBSA/pose selection for a pilot or standard short-MD gate whose duration
and recording interval are explicitly declared.

## Prerequisites

- Corrected-pose full-system CMS or authorized build command and stable parent/pose lineage.
- Validated short-production MSJ, explicit duration/interval, ASLs, and pass criteria.
- One approved GPU/host, disk/runtime budget, attempt root, and explicit compute confirmation.

## How to Run

Use the H8 manifest stage or invoke native multisim with `-m MSJ -o final.cms input.cms`, then
run the trajectory validator with the exact requested duration and interval.

## Quick Reference

| State | Meaning |
| --- | --- |
| Dry preparation | Inputs/protocol staged only |
| Submitted | Job exists but is not complete |
| Trajectory valid | Duration, frames, interval, topology pass |
| H8 pass | Valid trajectory plus SEA/pocket criteria |

## Procedure

1. Validate H7 handoff, corrected frame, system components, protocol, and selectors.
2. Resolve multisim/jobcontrol, isolate an attempt, and verify GPU ownership.
3. Launch, record exact job ID, and monitor process plus artifact progress.
4. Validate actual duration, frame spacing, continuity, topology, and final CMS/DTR.
5. Run SEA and freeze PASS/FAIL with pocket/contact rationale.

## Concrete Operation Procedure

Resolve multisim and the validator, then validate H7:

```bash
MULTISIM="$(masld-agent platform-resolve --id sz.bin.multisim)"
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
"$MULTISIM" -h
masld-agent funnel validate --manifest "$MANIFEST" --stage H7
```

Use the declared 10/50 ns duration, interval, corrected CMS, ASLs, MSJ, host, and GPU.
After dry preparation and confirmation submit `"$MULTISIM" -WAIT -HOST "$HOST_SPEC"
-maxjob 1 -m "$MSJ" -o "$FINAL_CMS" "$CMS"`; record the job ID and set both CUDA
variables. Validate with explicit `--minimum-ns "$DURATION_NS"` and
`--expected-interval-ps "$INTERVAL_PS"`, then run SEA QC.

Use the registry-resolved `RUN` and `MULTISIM` launchers, not a new conda environment.
Reuse validated CMS systems and MSJ templates. Short production may be a pilot 10 ns or standard 50 ns, but the manifest
must state the duration and equilibration protocol. Submission requires explicit
confirmation and one known GPU per job.

Validate the final production CMS/DTR with the bundled
`desmond-md-campaign/scripts/validate_desmond_trajectory.py`, then run SEA only on
validated trajectories. Always pass `--minimum-ns` equal to the manifest's short
production duration and `--expected-interval-ps` equal to its recording interval;
never rely on validator defaults. A submitted job, readable CMS alone, or dry prep
is not PASS.

## Detailed Generic Procedure

### 1. Preflight and system gate

Require a validated XP/MMGBSA handoff, corrected pose, full-system CMS or a manifest
authorized system-build command, explicit protein/ligand ASL, production duration, frame
interval, and one approved GPU. Resolve `sz.bin.run`, `sz.bin.multisim`, and
`sz.bin.jobcontrol` from the registry and inspect them with the bundled validator. Compare CMS
component counts with manifest ranges; do not copy counts from another target.

### 2. Submit the short run

Use an existing protocol such as `scripts/protocols/prod_2ns_eq_50ns.msj` only when its
equilibration and recording settings match the manifest. A representative explicit argv
is:

```bash
MULTISIM="$(masld-agent platform-resolve --id sz.bin.multisim)"
"$MULTISIM" -WAIT -HOST "$HOST_SPEC" -maxjob 1 \
  -m "$MANIFEST_MSJ" -o "{campaign_root}/08_h8_short/${MOLECULE_ID}-out.cms" \
  "{campaign_root}/inputs/${MOLECULE_ID}.cms"
```

Use the installed multisim help and project launcher to resolve the exact input order.
Set `CUDA_VISIBLE_DEVICES` and `SCHRODINGER_CUDA_VISIBLE_DEVICES` to the manifest GPU,
record the JobDJ ID and attempt directory, and verify GPU placement shortly after launch.

### 3. Validate and analyze

Run the bundled validator with explicit `--minimum-ns` equal to the manifest duration and
`--expected-interval-ps` equal to its interval. Require continuous time, monotonic frames,
readable final CMS/DTR, topology consistency, and `valid=true`. Run official SEA only
after this gate, then report protein/ligand RMSD, pocket contacts, late-window behavior,
frame counts, and PASS/FAIL per molecule.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-desmond-short-md --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-desmond-short-md --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-desmond-short-md --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-desmond-short-md --manifest MANIFEST --resume --execute --confirm
```

The manifest explicitly chooses 10 or 50 ns, protocol, GPU, command, and outputs. The
launcher never treats a test duration or a target-specific CMS as universal.

## Standalone Command-Line Procedure

Launch a validated short production directly with the native Desmond executable:

```bash
SCHRODINGER="${SCHRODINGER:-}"
MULTISIM="${MULTISIM:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  MULTISIM="${MULTISIM:-$(masld-agent platform-resolve --id sz.bin.multisim)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
MULTISIM="${MULTISIM:-$SCHRODINGER/utilities/multisim}"
CMS="$(realpath inputs/corrected_pose.cms)"
MSJ="$(realpath inputs/prod_2ns_eq_50ns.msj)"
OUT="$(realpath -m outputs/08_h8_short/attempt_01)"
mkdir -p "$OUT"
JOBNAME="${JOBNAME:-h8_short}"
FINAL_CMS="$OUT/${JOBNAME}-out.cms"
CUDA_VISIBLE_DEVICES="${GPU_ID:?approved GPU}" \
SCHRODINGER_CUDA_VISIBLE_DEVICES="${GPU_ID}" \
  "$MULTISIM" -WAIT -HOST "${HOST_SPEC:-localhost}" -maxjob 1 -JOBNAME "$JOBNAME" \
  -m "$MSJ" -o "$FINAL_CMS" "$CMS"
```

Validate with the exact requested `--minimum-ns` and `--expected-interval-ps`; then run
SEA using explicit protein and ligand ASLs. Keep partial trajectories as failed evidence,
not as PASS results.

## Pitfalls

- Dry prep, JobDJ submission, or a readable CMS alone is not a short-MD PASS.
- Do not use validator defaults when duration and interval are task inputs.
- Do not promote on RMSD alone without pocket/contact and continuity evidence.

## Verification

Require corrected input/protocol hashes, component QC, GPU/job/attempt lineage, normal exit,
valid CMS/DTR, actual nanoseconds and frames, exact interval, monotonic/topology checks, SEA
outputs, pocket/contact rationale, and one explicit H8 PASS/FAIL per candidate.
