---
name: funnel-desmond-long-md
description: Use to run long Desmond MD after short-MD qualification.
---

# H9 Long MD

Run an explicitly authorized long Desmond production from a short-MD-qualified corrected or
late-medoid full-system start, then validate and classify the complete trajectory.

## When to Use

Use only after H8 PASS and explicit authorization for the declared long production duration.

## Prerequisites

- H8 validator and decision, qualified full-system CMS, stable parent/pose/trajectory lineage.
- Long-production MSJ, duration, interval, ASLs, contact/pocket criteria, and classification.
- Owned GPU/host, disk/runtime estimate, attempt root, monitor cadence, and retry policy.

## How to Run

Use the H9 manifest stage or native multisim, then validate with the exact declared duration
(200 ns only when that is the task protocol) and interval before SEA or promotion.

## Quick Reference

| Evidence | Requirement |
| --- | --- |
| Entry gate | H8 PASS and validated start |
| Completion | Continuous declared duration, not filename |
| Analysis | SEA plus pocket/contact/convergence |
| Recovery | Checkpoint or failed unit in new attempt |

## Procedure

1. Validate H8 and freeze the corrected/medoid full-system start.
2. Confirm long-run resources and launch one isolated authorized attempt.
3. Persist job IDs, progress timestamps, checkpoints, and artifact growth.
4. Hard-validate actual duration, interval, continuity, topology, and normal exit.
5. Run SEA/analysis and classify retained, rearranged, inconclusive, or failed poses.

## Concrete Operation Procedure

Resolve the launcher and require H8 validation:

```bash
MULTISIM="$(masld-agent platform-resolve --id sz.bin.multisim)"
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
"$MULTISIM" -h
masld-agent funnel validate --manifest "$MANIFEST" --stage H8
```

Use the declared 200 ns protocol, corrected/medoid CMS, ASLs, interval, host, and GPU.
Submit from a new `attempt_XX` with confirmation, record the Job Control ID, monitor
process/file progress, and validate with explicit `--minimum-ns 200` plus interval.
Run SEA and analysis only after that gate; promote only from continuity, pocket retention,
contacts, and normal exit.

Only H8-qualified corrected-pose or validated late-medoid systems may enter H9.
Use the bundled 200 ns protocol and attempt directories. Confirm completion from
continuous trajectory time, expected frame spacing, final CMS readability, topology
consistency, and normal job exit—not filenames or process absence.

Do not submit without `--execute --confirm`. Recovery may resume an authorized queue
but must not overwrite prior attempts.

## Detailed Generic Procedure

Require H8 validation and a declared corrected-pose or late-medoid full-system CMS before
H9. The manifest supplies the 200 ns protocol, recording interval, protein/ligand ASL,
approved GPU/host, attempt root, validator, SEA, analysis, and report outputs. Do not
assume that a file containing `200ns` is complete.

Launch the existing `prod_2ns_eq_200ns.msj` through the registry-resolved `MULTISIM` or
the project-owned adapter with explicit argv, `-HOST`, `-maxjob`, output directory, and
one physical GPU. Record exact JobDJ ID, process ownership, input hashes, and attempt
number. Monitor the declared job at the manifest cadence; a stall requires both process
loss and no file progress beyond the configured timeout.

Validate with `validate_desmond_trajectory.py --minimum-ns 200` and the manifest's exact
interval. Require at least the configured continuous duration, final CMS/DTR readability,
monotonic frames, topology consistency, normal exit, and `attempt_validation.json` before
SEA. Run `run_sea.py`, then `analyze_md200.py`; classify pose retained, rearrangement,
inconclusive, or pose failure using pocket retention and contacts before score. Recover
only failed units and never overwrite an older attempt.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-desmond-long-md --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-desmond-long-md --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-desmond-long-md --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-desmond-long-md --manifest MANIFEST --resume --execute --confirm
```

The manifest explicitly chooses duration, protocol, resources, command, and outputs; no
target, trajectory, GPU, or completion flag is inferred.

## Standalone Command-Line Procedure

Run H9 only from an H8-qualified corrected pose or validated late-medoid system:

```bash
SCHRODINGER="${SCHRODINGER:-}"
MULTISIM="${MULTISIM:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  MULTISIM="${MULTISIM:-$(masld-agent platform-resolve --id sz.bin.multisim)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
MULTISIM="${MULTISIM:-$SCHRODINGER/utilities/multisim}"
CMS="$(realpath inputs/h8_qualified_system.cms)"
MSJ="$(realpath inputs/prod_2ns_eq_200ns.msj)"
OUT="$(realpath -m outputs/09_h9_long/attempt_01)"
mkdir -p "$OUT"
JOBNAME="${JOBNAME:-h9_long}"
FINAL_CMS="$OUT/${JOBNAME}-out.cms"
CUDA_VISIBLE_DEVICES="${GPU_ID:?approved GPU}" \
SCHRODINGER_CUDA_VISIBLE_DEVICES="${GPU_ID}" \
  "$MULTISIM" -WAIT -HOST "${HOST_SPEC:-localhost}" -maxjob 1 -JOBNAME "$JOBNAME" \
  -m "$MSJ" -o "$FINAL_CMS" "$CMS"
```

Require at least the declared 200 ns, continuous times, expected frame spacing, readable
final CMS/DTR, and topology consistency before SEA or promotion. A filename containing
`200ns` is not completion evidence.

## Pitfalls

- Do not infer completion from `200ns` in a filename or from process absence.
- Do not submit a long run for candidates that failed the short-MD gate.
- Do not overwrite prior attempts or recompute valid upstream short MD during recovery.

## Verification

Require H8 provenance, start/protocol hashes, authorization, GPU/job/attempt/checkpoint history,
normal exit, complete declared duration and frame interval, monotonic/topology validation, SEA
and pocket/contact metrics, classification rationale, failed rows, and report artifacts.
