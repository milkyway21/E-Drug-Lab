---
name: virtual-docking
description: Routes Glide SP, Glide XP, and MMGBSA refinement with lineage and validation. Use for H2 primary docking or H5-H7 refinement of validated compounds.
---

# Virtual Docking

This main skill owns structure-based ranking after generation or ADMET filtering.

## Child skills

- `funnel-glide-sp` for primary and refinement Glide SP
- `ddfast-07-glide-sp` only for legacy manifests
- `funnel-glide-xp` for H6 XP refinement
- `funnel-mmgbsa` for H7 MMGBSA

## Order

1. Run H2 Glide SP on validated H1 output and preserve parent IDs.
2. Validate poses, scores, counts, and receptor/grid compatibility.
3. Run H5 SP refinement, H6 XP, and H7 MMGBSA only on the frozen parent set.
4. Pass validated complexes and scores to `molecular-dynamics` or `all-analysis`.

Never use a legacy alias for new work, never mix receptor frames, and never call a score
an experimental binding measurement.

## Universal Manifest Invocation

This skill is reusable across targets and receptors when the manifest supplies the
validated receptor/grid, candidate structures, lineage fields, output contracts,
resources, reporting location, and an explicit argv `command` or ordered `steps`.
Never infer a grid, receptor frame, ligand set, or score threshold from the skill name.

```bash
bash scripts/run_skill.sh --skill virtual-docking --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill virtual-docking --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill virtual-docking --manifest MANIFEST --status
```

Execution and recovery are explicit:

```bash
bash scripts/run_skill.sh --skill virtual-docking --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill virtual-docking --manifest MANIFEST --resume --execute --confirm
```

Use relative paths and preserve parent, prepared-state, pose, and receptor lineage.
Do not treat a dry run, submitted job, or numeric prediction as a completed stage;
advance only when the declared pose and score artifacts validate.

## Generic Glide-to-Energy Method

For any target, keep the receptor coordinate frame fixed from structure preparation and
reuse the manifest-declared grid. The generic sequence is LigPrep, primary or refined
Glide SP, frozen-parent ranking, optional XP refinement, Prime MMGBSA, then a validated
complex handoff to MD. LigPrep states are preparation states, not independent parents.
Every table joins `molecule_id`, `parent_id`, `prepared_state_id`, `pose_id`, receptor
frame, grid ID, backend, and source file.

Before submission resolve `sz.bin.ligprep` and `sz.bin.glide` from the platform registry,
probe those executables, and record the version/help output. Use an isolated
numbered working directory and explicit CWD. For distributed jobs, omit the `JOBNAME`
keyword from the Glide input, pass one unique CLI `-JOBNAME`, and include `-OVERWRITE`.
Do not launch a full set after a prompt or wrapper failure until the one-state probe
finishes normally.

H2/H5 completion requires a numeric score table, readable `_pv.maegz`, normal parent and
subjob exit, expected parent count, and deterministic best-pose selection. H6 consumes
only the frozen H5 parents and preserves their SP poses. H7 consumes only validated XP
poses; MMGBSA values are ranking evidence, not binding measurements. Missing score or
energy rows remain missing and block automatic promotion.

## Concrete Operation Procedure

Resolve every Schrödinger executable through the registry before launching a stage:

```bash
masld-agent platform-health
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
GLIDE="$(masld-agent platform-resolve --id sz.bin.glide)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
MMGBSA="$(masld-agent platform-resolve --id sz.bin.prime_mmgbsa)"
"$LIGPREP" -h; "$GLIDE" -h; "$JOBCONTROL" -h; "$MMGBSA" -h
```

Use H2/H5/H6/H7 counts from `masld-agent funnel plan --final-count N --profile full`.
For each stage: validate the previous stage, create a numbered output directory, run one
ligand probe, wait on the exact Job Control ID, parse numeric rows, and freeze parent-level
results before moving on. H2/H5 use SP, H6 uses XP only on the H5 frozen set, and H7 uses
MMGBSA only on H6 validated poses.

## Standalone Command-Line Procedure

The following is the public native Schrödinger route. It does not require a manifest or
`masld-agent`; set `SCHRODINGER` yourself, or use any local registry only to discover
that variable and executable paths. Run every command from its numbered output directory.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
PREPWIZARD="${PREPWIZARD:-$SCHRODINGER/utilities/prepwizard}"
LIGPREP="${LIGPREP:-$SCHRODINGER/ligprep}"
GLIDE="${GLIDE:-$SCHRODINGER/glide}"
PRIME_MMGBSA="${PRIME_MMGBSA:-$SCHRODINGER/prime_mmgbsa}"
PROPLISTER="${PROPLISTER:-$SCHRODINGER/utilities/proplister}"
JOBCONTROL="${JOBCONTROL:-$SCHRODINGER/jobcontrol}"
RECEPTOR_PDB="$(realpath inputs/receptor_clean.pdb)"
LIGANDS_SDF="$(realpath inputs/frozen_ligands.sdf)"
ROOT="$(realpath -m tasks/TARGET_ID)"
mkdir -p "$ROOT/02_grid" "$ROOT/02_glide" "$ROOT/07_mmgbsa"
"$PREPWIZARD" "$RECEPTOR_PDB" "$ROOT/02_grid/receptor_prepared.maegz" \
  -epik_pH "${EPIK_PH:-7.0}" -fillsidechains -disulfides \
  -propka_pH "${PROPKA_PH:-7.0}" -captermini -WAIT
```

Create a grid input using the pocket center and validated dimensions, then generate it:

```bash
printf '%s\n' \
  "GRID_CENTER ${CX} ${CY} ${CZ}" \
  "INNERBOX ${INNER_X} ${INNER_Y} ${INNER_Z}" \
  "OUTERBOX ${OUTER_X} ${OUTER_Y} ${OUTER_Z}" \
  "RECEP_FILE $ROOT/02_grid/receptor_prepared.maegz" \
  "GRIDFILE $ROOT/02_grid/receptor_grid.zip" \
  > "$ROOT/02_grid/grid.in"
cd "$ROOT/02_grid"
"$GLIDE" grid.in -WAIT -OVERWRITE -JOBNAME TARGET_grid
```

LigPrep the frozen ligand set, write a parent-to-state table, and use a docking input
with `GRIDFILE`, `LIGANDFILE`, `PRECISION SP` or `PRECISION XP`, and no `JOBNAME` line:

```bash
"$LIGPREP" -isd "$LIGANDS_SDF" -osd "$ROOT/02_glide/prepared.sdf" -epik -WAIT
printf '%s\n' \
  "GRIDFILE $ROOT/02_grid/receptor_grid.zip" \
  "LIGANDFILE $ROOT/02_glide/prepared.sdf" \
  "PRECISION ${PRECISION:-SP}" \
  "POSES_PER_LIG ${POSES_PER_LIG:-5}" \
  "POSTDOCK ${POSTDOCK:-true}" \
  "NREPORT 1" \
  > "$ROOT/02_glide/dock.in"
cd "$ROOT/02_glide"
"$GLIDE" dock.in -HOST "${HOST_SPEC:-localhost}" -NJOBS "${NJOBS:-1}" \
  -WAIT -OVERWRITE -JOBNAME TARGET_glide_${PRECISION:-SP}
"$PROPLISTER" -c -a -o scores.csv TARGET_glide_${PRECISION:-SP}_pv.maegz
```

For MMGBSA, use the XP pose viewer as the input Maestro file. `prime_mmgbsa` expects
the receptor as the first entry and ligand poses after it; do not feed it an SDF:

```bash
cd "$ROOT/07_mmgbsa"
"$PRIME_MMGBSA" "$ROOT/02_glide/TARGET_glide_XP_pv.maegz" \
  -job_type ENERGY -csv_output yes -JOBNAME TARGET_mmgbsa -WAIT
```

Wait on asynchronous jobs with `jobcontrol -wait -int 300 JOB_ID`, inspect `-show` and
`-files` for recovery, and only promote rows with numeric score/energy fields, readable
pose viewers, completed subjobs, and intact parent lineage.
