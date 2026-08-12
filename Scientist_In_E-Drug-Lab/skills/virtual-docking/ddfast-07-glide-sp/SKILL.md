---
name: ddfast-07-glide-sp
description: Compatibility alias for single-receptor LigPrep and Glide SP after QikProp filtering. Use only when an existing task names ddfast-07; route new H2/H5 work to funnel-glide-sp and never use this alias for multi-receptor or HSV workflows.
---

# DDFast 07 Glide SP Compatibility

Use `funnel-glide-sp` for all new work. Keep this skill only to resume manifests that
already identify the stage as `ddfast-07-glide-sp`.

## Resume Contract

1. Read the manifest and run `masld-agent funnel validate` before computing.
2. Reuse the manifest-declared prepared receptor and grid; do not rebuild validated
   inputs merely because a wrapper failed.
3. Preserve parent-to-prepared-state lineage through LigPrep and rank each parent by
   its numeric minimum `r_i_glide_gscore`.
4. For non-interactive Schrödinger 2023-3 Glide, omit `JOBNAME` from the input,
   provide one CLI `-JOBNAME`, and include `-OVERWRITE`.
5. Require a finished log, readable pose viewer, numeric score table, and exact-N
   parent manifest before marking completion.

```bash
masld-agent funnel run --manifest MANIFEST --stage H2
masld-agent funnel run --manifest MANIFEST --stage H2 --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H2
```

Capability catalog IDs: `sz.prepwizard`, `sz.ligprep`, `sz.grid`, `sz.glide_sp`,
and `ed.svc.schrodinger`.

## Universal Manifest Invocation

This compatibility skill accepts only an existing manifest that explicitly names the
legacy stage and command. New tasks should use `funnel-glide-sp`, but this alias remains
portable because it does not select a receptor, grid, target, or ligand set.

```bash
bash scripts/run_skill.sh --skill ddfast-07-glide-sp --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill ddfast-07-glide-sp --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill ddfast-07-glide-sp --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill ddfast-07-glide-sp --manifest MANIFEST --resume --execute --confirm
```

## Concrete Operation Procedure

This compatibility alias still resolves the installed tools through the registry:

```bash
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
GLIDE="$(masld-agent platform-resolve --id sz.bin.glide)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$LIGPREP" -h; "$GLIDE" -h; "$JOBCONTROL" -h
masld-agent funnel validate --manifest "$MANIFEST" --stage H2
```

Then follow `funnel-glide-sp`: LigPrep the declared frozen SDF, run one non-interactive
SP probe with CLI `-JOBNAME` and `-OVERWRITE`, wait by exact job ID, parse numeric scores,
and freeze one best pose per parent. New tasks must not enter through this alias.

## Standalone Command-Line Procedure

For a new task, invoke Schrödinger directly and use the same procedure as
`funnel-glide-sp`; no manifest or agent path is required:

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
LIGPREP="${LIGPREP:-$SCHRODINGER/ligprep}"
GLIDE="${GLIDE:-$SCHRODINGER/glide}"
INPUT_SDF="${INPUT_SDF:?input SDF}"
GRID_ZIP="${GRID_ZIP:?Glide grid ZIP}"
OUT_DIR="${OUT_DIR:-glide_sp}"
mkdir -p "$OUT_DIR"
"$LIGPREP" -isd "$INPUT_SDF" -osd "$OUT_DIR/ligands.sdf" -epik -WAIT
printf '%s\n' 'GRIDFILE grid.zip' 'LIGANDFILE ligands.sdf' 'PRECISION SP' \
  'POSTDOCK true' 'POSES_PER_LIG 3' > "$OUT_DIR/dock.in"
cp "$GRID_ZIP" "$OUT_DIR/grid.zip"
(cd "$OUT_DIR" && "$GLIDE" dock.in -WAIT -OVERWRITE -JOBNAME glide_sp)
```

Parse the pose viewer and score table by stable ligand ID, retain input/grid hashes and
job status, and never treat an SP score as measured affinity. Use `PRECISION XP` only in
the XP skill.
