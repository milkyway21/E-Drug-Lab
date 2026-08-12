---
name: funnel-shape-screen
description: Run H3 pose-based Schrödinger Shape screening from extracted best Glide poses with version-aware command validation and recoverable outputs. Use for pose-shape expansion; do not treat JobDJ submission or wrapper exit as completion.
---

# Shape Screen

Extract real best Glide poses before screening. Resolve Shape tools from the platform
registry and probe the resolved executables before building the command. Under
Schrödinger 2023-3, never supply `-osd` and `-ocsv` together. A JobDJ submission or
outer `-WAIT` process is not completion; require exit 0, a success log, and a readable
non-empty output.

Set the stage command `cwd` to the declared Shape output directory and use absolute
query/database paths. Schrödinger may place output beside the process CWD rather than
the apparent output argument; validate the expected path before any move. If the file
landed in the task root, move the completed artifact once and fix the reusable adapter,
without recomputing the Shape job.

Read `.sdfgz` through gzip binary decompression before RDKit parsing. If internal
subjobs completed but the wrapper is stale, retain outputs and stop only the exact
known wrapper PID—never use pattern-wide `pkill`.

## Detailed Generic Procedure

### 1. Extract a real ligand query

Start from frozen Glide `_pv.maegz`. Select the best numeric pose for each frozen parent,
preserve receptor grid and score metadata, and extract ligand records only. Do not pass a
receptor-containing MAEGZ as a Shape query. Verify query count, unique parent count,
non-empty coordinates, and stable query IDs before screening.

### 2. Route by database format

Probe installed tools and save the output in the task log:

```bash
SHAPE_GPU="$(masld-agent platform-resolve --id sz.bin.shape_screen_gpu)"
QUICK_SHAPE="$(masld-agent platform-resolve --id sz.bin.quick_shape)"
ONED="$(masld-agent platform-resolve --id sz.bin.oned_screen)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$SHAPE_GPU" -h
"$QUICK_SHAPE" -h
"$ONED" -h
"$JOBCONTROL" -h
```

Use `shape_screen_gpu generate` for `.bin` and screen that format with
`shape_screen_gpu`. A Phase 1D database ending in `.1dbin` must use `oned_screen` or
`quick_shape`; never rename it, symlink it under another extension, or feed it to the
GPU `.bin` reader. Use QuickShape for a 1D topology prefilter followed by 3D alignment.

Representative QuickShape argv:

```bash
QUICK_SHAPE="$(masld-agent platform-resolve --id sz.bin.quick_shape)"
"$QUICK_SHAPE" -nocopy -shape "{campaign_root}/inputs/query_poses.sdf" \
  -screen "{campaign_root}/inputs/library.1dbin" -sample rapid \
  -max "$QUERIES_PER_PARENT" -keep "$HIT_CAP" -reduce "$REDUCE_CAP" \
  -osd -best -NJOBS "$CPU_JOBS" -HOST "$HOST_SPEC" \
  -TMPDIR "{campaign_root}/tmp" -JOBNAME "$UNIQUE_JOB_NAME"
```

Use installed help to adjust flags. Where CSV output is selected, use `-ocsv` instead of
`-osd`; never pass both. Set output CWD explicitly because JobDJ may restore files beside
the launch directory.

### 3. Wait, recover, and parse

Treat `JobId:` as submission only. Wait with the exact job ID:

```bash
"$JOBCONTROL" -wait -int 300 <job_id>
```

Require normal parent/subjob exit, success log, readable non-empty SDF/SDFGZ, and numeric
`r_phase_Shape_Sim`. Read SDFGZ as binary gzip. Exclude query records, invalid properties,
and duplicate library states before ranking. If a wrapper failed after subjobs completed,
inspect `jobcontrol -show`/`-files`, recover only this task's output, and resume parsing
without resubmission.

### 4. Exact-N output

For each library ID keep best numeric Shape score, winning query ID, source database,
state ID, and rank. Canonical-deduplicate after ID aggregation. Require exact-N manifest
rows, exact-N readable SDF records, unique library IDs, and unique canonical structures.
Report query records removed, invalid records, database format, backend version, and
score policy.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-shape-screen --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-shape-screen --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-shape-screen --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-shape-screen --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies query, library/database, backend, output CWD, JobDJ resources,
timeouts, and explicit argv. The launcher does not assume a Shape database format or
target-specific output name.

## Concrete Operation Procedure

Resolve Shape tools from the registry and verify the database route:

```bash
SHAPE_GPU="$(masld-agent platform-resolve --id sz.bin.shape_screen_gpu)"
QUICK_SHAPE="$(masld-agent platform-resolve --id sz.bin.quick_shape)"
ONED="$(masld-agent platform-resolve --id sz.bin.oned_screen)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$SHAPE_GPU" -h; "$QUICK_SHAPE" -h; "$ONED" -h; "$JOBCONTROL" -h
```

Extract ligand-only `QUERY_POSE_SDF` from the validated Glide pose set. If the library
ends in `.1dbin`, use QuickShape or `oned_screen`; if it is a GPU-generated `.bin`, use
the registered GPU tool. A representative QuickShape call is:

```bash
cd "$CAMPAIGN_ROOT/03_h3/shape"
"$QUICK_SHAPE" -nocopy -shape "$QUERY_POSE_SDF" -screen "$LIBRARY_DB" \
  -sample rapid -max "$QUERIES_PER_PARENT" -keep "$HIT_CAP" -reduce "$REDUCE_CAP" \
  -osd -best -NJOBS "$CPU_JOBS" -HOST "$HOST_SPEC" \
  -TMPDIR "$CAMPAIGN_ROOT/tmp" -JOBNAME "${TARGET_ID}_h3_shape"
```

Do not pass `-osd` and `-ocsv` together. Treat `JobId:` as submission only; wait with
`"$JOBCONTROL" -wait -int 300 "$JOB_ID"`, then require normal subjobs, success log,
numeric `r_phase_Shape_Sim`, and readable SDF/SDFGZ. Exclude query records, reduce to
best score per library ID, canonical-deduplicate, and freeze exact-N output. If output
landed beside the launch CWD, recover it with `-show`/`-files` and resume parsing without
resubmitting.

## Standalone Command-Line Procedure

Choose the native executable from the database format. The query is ligand-only and the
library is immutable. A `.1dbin` is not interchangeable with a GPU `.bin` database.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
SHAPE_GPU="${SHAPE_GPU:-$SCHRODINGER/shape_screen_gpu}"
QUICK_SHAPE="${QUICK_SHAPE:-$SCHRODINGER/quick_shape}"
ONED="${ONED:-$SCHRODINGER/oned_screen}"
QUERY_SDF="$(realpath inputs/query_poses.sdf)"
LIBRARY_SDF="$(realpath inputs/frozen_library.sdf)"
OUT="$(realpath -m outputs/03_shape)"
mkdir -p "$OUT"
"$SHAPE_GPU" generate -source "$LIBRARY_SDF" \
  -shape_data_dir "$OUT/database" -shape_type pharm -keep_properties \
  -ligprep -JOBNAME TARGET_shape_db
"$SHAPE_GPU" run -shape "$QUERY_SDF" -screen "$OUT/database/TARGET_shape_db.bin" \
  -keep "${HIT_CAP:-1000}" -best -osd -JOBNAME TARGET_shape
```

For a Phase 1D library, create and screen it with the native 1D commands:

```bash
"$ONED" create -source "$LIBRARY_SDF" -dest "$OUT/library.1dbin" \
  -treatment pharm -props "s_user_ID"
"$ONED" run -query "$QUERY_SDF" -screen "$OUT/library.1dbin" \
  -keep "${HIT_CAP:-1000}" -filter "${ONED_FILTER:-0.0}"
```

For the combined 1D-to-3D route use QuickShape instead:

```bash
"$QUICK_SHAPE" -nocopy -shape "$QUERY_SDF" -screen "$OUT/library.1dbin" \
  -sample rapid -max "${MAX_CONFS:-100}" -keep "${HIT_CAP:-1000}" \
  -reduce "${SHAPE_HIT_CAP:-100}" -osd -best -JOBNAME TARGET_quick_shape
```

Use `-ocsv` instead of `-osd`, never both. Wait for the exact JobDJ ID if the native
tool submits asynchronously, then require `r_phase_Shape_Sim`, source library ID,
winning query ID, readable output, and exact-N canonical deduplication.
