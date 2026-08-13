---
name: funnel-glide-xp
description: Use to refine a frozen parent set with Glide XP.
---

# H6 Glide XP

Refine only the validated SP-selected parent set with extra-precision docking on the same
receptor grid and preserve SP-to-XP pose lineage.

## When to Use

Use after H5 SP validation when the funnel requests XP refinement of a frozen subset.

## Prerequisites

- Frozen H5 parent and pose manifest, prepared states, and unchanged grid ZIP.
- Glide/Job Control executables, host policy, and isolated H6 directory.

## How to Run

Use the manifest stage for normal orchestration or create a native Glide input containing
`PRECISION XP` and launch it directly with one CLI job name.

## Quick Reference

| Rule | Requirement |
| --- | --- |
| Population | H5 frozen parents only |
| Grid | Same validated H5 grid |
| Precision | `XP` |
| Result | Numeric XP score and readable pose per parent |

## Procedure

1. Validate H5 and freeze the exact parent/pose input.
2. Probe the installed Glide command with one representative pose.
3. Launch XP on the frozen set and wait for exact job completion.
4. Join XP rows back to SP parent and pose IDs.
5. Preserve failed/missing rows and freeze only validated XP results.

Select unique parents from validated H5 SP results, preserve their actual poses and
reuse the same grid. Configure an existing XP runner as `stages.H6.command`.
Validate numeric XP scores and a readable pose viewer before advancing.

Preview first; production requires `--execute --confirm`. Never XP the full upstream
library when a frozen target subset exists.

## Detailed Generic Procedure

The H6 manifest declares the validated H5 parent manifest, the actual H5 pose viewer,
the same receptor grid, the XP input/output, and an explicit existing Glide XP command.
Create a new numbered H6 directory, but do not recreate LigPrep or redock the upstream
library. Preserve `parent_id`, selected SP pose, XP state, grid hash, and source paths.

Before full XP, probe one frozen pose and installed Glide help. Use an explicit CLI
`-JOBNAME` and `-OVERWRITE`, wait for the exact JobDJ ID, and require normal parent/subjob
completion. Validate numeric XP score fields and a readable XP `_pv.maegz`; a non-empty
file without score rows is incomplete. Join XP scores back to the H5 manifest and retain
missing/failed parents visibly.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-glide-xp --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-glide-xp --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-glide-xp --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-glide-xp --manifest MANIFEST --resume --execute --confirm
```

The manifest explicitly chooses the XP runner, frozen parent set, output contract,
resources, and report. No target-specific pose, grid, or count is inferred.

## Concrete Operation Procedure

Resolve and probe the same Glide/Job Control entries used for SP:

```bash
GLIDE="$(masld-agent platform-resolve --id sz.bin.glide)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$GLIDE" -h
"$JOBCONTROL" -h
masld-agent funnel validate --manifest "$MANIFEST" --stage H5
```

Create the H6 input from the validated H5 parent manifest and the same grid. Probe one
pose with XP precision, `-OVERWRITE`, a unique CLI `-JOBNAME`, and the exact host
allocation; wait with `"$JOBCONTROL" -wait -int 300 "$JOB_ID"`. Launch the complete
H5-frozen set only after the probe has a numeric XP score and readable `_pv.maegz`.
Join XP results by `parent_id`/`pose_id`, retain failed or missing rows, and validate the
promoted count before H7. Never rebuild LigPrep or redock the upstream library here.

## Standalone Command-Line Procedure

XP is a refinement of a frozen SP parent set. It uses the same grid and prepared states;
do not pass the original large library or silently rerun LigPrep.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
GLIDE="${GLIDE:-$SCHRODINGER/glide}"
PROPLISTER="${PROPLISTER:-$SCHRODINGER/utilities/proplister}"
GRID_ZIP="$(realpath inputs/receptor_grid.zip)"
H5_SDF="$(realpath inputs/h5_frozen_prepared.sdf)"
OUT="$(realpath -m outputs/06_glide_xp)"
mkdir -p "$OUT"
printf '%s\n' \
  "GRIDFILE $GRID_ZIP" \
  "LIGANDFILE $H5_SDF" \
  "PRECISION XP" \
  "POSES_PER_LIG ${POSES_PER_LIG:-5}" \
  "POSTDOCK ${POSTDOCK:-true}" \
  "NREPORT 1" > "$OUT/glide_xp.in"
cd "$OUT"
"$GLIDE" glide_xp.in -HOST "${HOST_SPEC:-localhost}" \
  -NJOBS "${NJOBS:-1}" -WAIT -OVERWRITE -JOBNAME TARGET_glide_xp
"$PROPLISTER" -c -a -o glide_xp_scores.csv TARGET_glide_xp_pv.maegz
```

Require a numeric XP score and one readable pose per promoted parent. Preserve missing
rows and the SP-to-XP join table; never fill a failed XP result from an SP score.

## Pitfalls

- Do not rerun LigPrep or the upstream library at H6.
- Do not silently substitute an SP score for a missing XP row.
- Do not change receptor grid, frame, or preparation policy between SP and XP.

## Verification

Confirm identical grid hash, frozen-parent count, probe success, normal JobDJ completion,
numeric XP scores, readable poses, complete SP-to-XP joins, explicit failed rows, and one
validated XP result per promoted parent.
