---
name: funnel-glide-sp
description: Use to prepare ligands and run validated Glide SP.
---

# Glide SP

Prepare ligand states and run Glide standard-precision docking against a validated receptor
grid, then rank deterministic best poses at the parent-compound level.

## When to Use

Use for primary H2 docking or H5 redocking/refinement after a qualified pocket and validated
grid exist.

## Prerequisites

- Grid ZIP tied to a prepared receptor and qualified pocket.
- Frozen input SDF with stable parent IDs and preparation-state policy.
- LigPrep, Glide, Job Control, host allocation, and numbered output directory.

## How to Run

Use manifest-declared LigPrep and Glide argv by default. Standalone mode resolves the licensed
installation and runs native `ligprep` followed by `glide` from an isolated working directory.

## Quick Reference

| Input or option | Purpose | Gate |
| --- | --- | --- |
| `-isd` / `-osd` | LigPrep SDF input/output | Parent-state map |
| `GRIDFILE` | Prepared receptor grid | Hash/frame match |
| `PRECISION SP` | Standard precision | Do not substitute XP |
| `_pv.maegz` | Receptor plus poses | Readable records and scores |

## Procedure

1. Validate the frozen parent set and receptor-grid compatibility.
2. Probe LigPrep/Glide, prepare states, and write parent-to-state lineage.
3. Run a one-state noninteractive probe in the final launch pattern.
4. Run the full set, wait for exact JobDJ completion, and recover outputs if needed.
5. Parse numeric scores and freeze the lowest score pose per parent.

Use stage H2 for primary SP and H5 for refined SP. Reuse the manifest grid; do not
rebuild it when a validated ZIP already exists. Preserve `parent_id -> prepared_state`
mapping and rank each parent by numeric minimum `r_i_glide_gscore`.

Before execution resolve `sz.bin.ligprep` and `sz.bin.glide` from the platform registry,
then inspect the resolved executables with `-h`.
Completion requires a non-empty CSV, readable pose viewer, numeric scores, and the
expected parent-level selection manifest.

Schrödinger 2023-3 non-interactive pitfall: a distributed Glide launch can stop at
an `existing job by this name` prompt even after changing the apparent job name.
Do not retry a full ligand set by renaming alone. First run one prepared-state probe
in an isolated task directory. The validated non-interactive pattern is to omit the
`JOBNAME` keyword from the Glide input, pass one unique CLI `-JOBNAME`, and add the
official `-OVERWRITE` startup flag. Require `ExitStatus: finished`, a success log,
and a real `_pv.maegz` before applying the same call to the frozen full input. Clear
project `PYTHONPATH` for Schrödinger tools when a custom `sitecustomize.py` shadows
Schrödinger's own module.

```bash
masld-agent funnel run --manifest MANIFEST --stage H2 --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H2
```

## Detailed Generic Procedure

### 1. Inputs and lineage

The manifest declares a clean receptor or PrepWizard input for Glide, an existing grid
ZIP, frozen ligand SDF, parent IDs, output CWD, precision (`SP`), host/CPU/GPU policy,
and score/pose outputs. Do not rebuild the grid inside H2/H5 unless the manifest explicitly
starts a new grid stage. Validate receptor-grid compatibility and ligand record count.

### 2. LigPrep

Run the installed tool with the manifest's options after probing help. A minimal argv
shape is:

```bash
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
"$LIGPREP" -isd "{campaign_root}/inputs/frozen_ligands.sdf" \
  -osd "{campaign_root}/02_ligprep/prepared.sdf" -epik -WAIT
```

Use the task's required force-field, protonation, tautomer, and stereochemistry policy;
do not hide it in an untracked wrapper. Write a parent-to-state table before docking and
retain invalid/removed states with reasons.

### 3. Glide SP launch

Use an existing Glide input or project adapter. A representative launch is:

```bash
GLIDE="$(masld-agent platform-resolve --id sz.bin.glide)"
"$GLIDE" glide.in -HOST "$HOST_SPEC" -NJOBS "$JOB_COUNT" \
  -WAIT -OVERWRITE -JOBNAME "$UNIQUE_JOB_NAME"
```

The exact flags must come from installed help and the existing adapter. Do not put
`JOBNAME` inside the input and CLI at the same time. Require `ExitStatus: finished`,
numeric `r_i_glide_gscore`, readable `_pv.maegz`, and expected subjob completion. Rank
numeric scores ascending and keep one best pose per parent, with deterministic parent-ID
tie-break.

### 4. Monitoring and recovery

Persist the JobDJ ID, process owner, CWD, input hashes, grid hash, and attempt directory.
Wait with the exact ID using the installed job-control interface. If subjobs completed
but the wrapper checked the wrong directory, recover the task's output and resume parsing;
do not rerun LigPrep or docking. Never use broad `pkill`/`killall`.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-glide-sp --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-glide-sp --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-glide-sp --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-glide-sp --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies the explicit LigPrep/Glide argv, CWD, grid, lineage, resources,
timeouts, and output validation. The launcher never invents a receptor, grid, target,
precision, or score threshold.

## Concrete Operation Procedure

Resolve the binaries from the registry and inspect their installed help:

```bash
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
GLIDE="$(masld-agent platform-resolve --id sz.bin.glide)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$LIGPREP" -h > "$CAMPAIGN_ROOT/02_glide/ligprep.help.txt"
"$GLIDE" -h > "$CAMPAIGN_ROOT/02_glide/glide.help.txt"
"$JOBCONTROL" -h > "$CAMPAIGN_ROOT/02_glide/jobcontrol.help.txt"
```

Run LigPrep into the numbered stage directory, preserving one `parent_id` for every
prepared state:

```bash
"$LIGPREP" -isd "$FROZEN_LIGANDS_SDF" \
  -osd "$CAMPAIGN_ROOT/02_glide/prepared.sdf" -epik -WAIT
```

Use the existing grid and a one-state Glide probe before the full set. The input file
must contain the manifest-declared `GRIDFILE`, `LIGANDFILE`, and SP precision; omit the
`JOBNAME` keyword from the input and give one unique CLI name:

```bash
cd "$CAMPAIGN_ROOT/02_glide/probe"
"$GLIDE" "$PROBE_IN" -HOST "$HOST_SPEC" -NJOBS 1 -WAIT -OVERWRITE \
  -JOBNAME "${TARGET_ID}_h2_probe"
```

Require `ExitStatus: finished`, a numeric `r_i_glide_gscore`, and a readable pose viewer.
Only then launch the full frozen set with the same input/CLI split. Wait with
`"$JOBCONTROL" -wait -int 300 "$JOB_ID"`; on wrong-path recovery use `-show` and
`-files`, then parse without resubmitting. Rank ascending by numeric score and keep one
best pose per parent. Validate score rows, pose records, parent count, grid hash, and
lineage before the next stage.

## Standalone Command-Line Procedure

This is the direct Glide SP route for users who are not running the manifest launcher.
Set `SCHRODINGER` or the individual executable variables; the skill does not assume an
installation directory.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
LIGPREP="${LIGPREP:-$SCHRODINGER/ligprep}"
GLIDE="${GLIDE:-$SCHRODINGER/glide}"
PROPLISTER="${PROPLISTER:-$SCHRODINGER/utilities/proplister}"
GRID_ZIP="$(realpath inputs/receptor_grid.zip)"
INPUT_SDF="$(realpath inputs/frozen_ligands.sdf)"
OUT="$(realpath -m outputs/02_glide_sp)"
mkdir -p "$OUT"
"$LIGPREP" -isd "$INPUT_SDF" -osd "$OUT/prepared.sdf" -epik -WAIT
printf '%s\n' \
  "GRIDFILE $GRID_ZIP" \
  "LIGANDFILE $OUT/prepared.sdf" \
  "PRECISION SP" \
  "POSES_PER_LIG ${POSES_PER_LIG:-5}" \
  "POSTDOCK ${POSTDOCK:-true}" \
  "NREPORT 1" > "$OUT/glide_sp.in"
cd "$OUT"
"$GLIDE" glide_sp.in -HOST "${HOST_SPEC:-localhost}" \
  -NJOBS "${NJOBS:-1}" -WAIT -OVERWRITE -JOBNAME TARGET_glide_sp
"$PROPLISTER" -c -a -o glide_sp_scores.csv TARGET_glide_sp_pv.maegz
```

The grid ZIP must have been generated for the same prepared receptor and pocket. Keep
the LigPrep parent/state table, pose viewer, score CSV, job log, and rejected records.
Select the lowest numeric `r_i_glide_gscore` per parent only after checking completed
subjobs and readable poses; a non-empty output file is not completion.

## Pitfalls

- Do not put `JOBNAME` in both Glide input and CLI arguments.
- Do not count protonation, tautomer, or stereochemical states as separate parent hits.
- A score table without its corresponding readable pose viewer is incomplete.
- Do not rebuild a valid grid merely because a wrapper or output-path check failed.

## Verification

Require input/grid hashes, LigPrep policy and parent-state table, probe success, exact job ID,
finished parent/subjobs, numeric `r_i_glide_gscore`, readable pose viewer, rejected states,
one deterministic pose per parent, and observed parent count matching the frozen result.
