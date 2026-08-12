# Schrödinger distributed-job probes and recovery

This reference captures a tested recovery pattern for Glide and QuickShape under
Schrödinger 2023-3. Replace placeholders with manifest paths; do not copy a prior
task's scientific outputs.

## Capability probes

Run help with the exact installed binary before composing arguments:

```bash
GLIDE="$(masld-agent platform-resolve --id sz.bin.glide)"
ONED="$(masld-agent platform-resolve --id sz.bin.oned_screen)"
QUICK_SHAPE="$(masld-agent platform-resolve --id sz.bin.quick_shape)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$GLIDE" -h
"$ONED" -h
"$QUICK_SHAPE" -h
"$JOBCONTROL" -h
```

If help imports a project `sitecustomize.py` instead of Schrödinger's module, the
fix is a subprocess-local empty `PYTHONPATH`, followed by a fresh probe. Do not
change the global environment unless required.

## Glide non-interactive single-ligand probe

Create a one-state prepared-ligand SDF and a minimal Glide input. Do not put
`JOBNAME` in the input during this diagnostic. Launch:

```bash
"$GLIDE" probe.in \
  -HOST localhost:1 \
  -WAIT \
  -OVERWRITE \
  -JOBNAME target_stage_probe01
```

Require all of:

- launcher reports `ExitStatus: finished`;
- Glide log says receptor/grid setup completed;
- one real docking result has a numeric `r_i_glide_gscore`;
- `_pv.maegz` is readable and contains receptor + ligand pose.

Only then apply the same input/CLI split to the full prepared set. If full Glide
fails, propagate a non-zero exit from the reusable runner; do not let a missing pose
file surface later as a misleading `proplister` failure.

## Phase 1D / QuickShape route

A `.1dbin` file is a Phase 1D database. `shape_screen_gpu run` expects a generated
`.bin` database and will reject `.1dbin`. Use QuickShape for 1D prefilter + 3D Shape:

```bash
cd MANIFEST_NUMBERED_SHAPE_DIR
"$QUICK_SHAPE" \
  -nocopy \
  -shape query_ligand_poses.sdf \
  -screen "$LIBRARY_1DBIN" \
  -sample rapid \
  -max 20 \
  -keep 100 \
  -reduce 30 \
  -osd \
  -best \
  -NJOBS 4 \
  -HOST localhost:4 \
  -TMPDIR "$CAMPAIGN_ROOT/tmp" \
  -JOBNAME target_stage_quick_shape
```

The command normally returns `JobId:` before completion. Parse that ID and wait:

```bash
"$JOBCONTROL" -wait -int 300 JOB_ID
```

Do not poll at 30- or 60-second intervals for the full job.

## Completion evidence

A robust full run should show:

- 1D unique-hit count;
- every distributed subjob finished normally;
- per-query `REPORT OF BEST N POSES` messages;
- final `quick_shape successfully completed`;
- readable `<jobname>-out.sdfgz`.

The output SDFGZ may contain the query structures followed by aligned hits. For
example, ten queries with 30 retained hits per query can yield 310 records, not 300.
Count only records with numeric `r_phase_Shape_Sim` as hits.

## Wrong-path recovery without resubmission

If Job Control says `finished` but the wrapper reports a missing output:

```bash
"$JOBCONTROL" -show JOB_ID
"$JOBCONTROL" -files JOB_ID
```

The `Dir`/`output` entries reveal the recovery location. Move only files belonging
to that job into the manifest's numbered output directory. Correct the launcher to
`cd` there before future submission. Preserve the completed job and resume from
property parsing/freeze; never resubmit solely because the wrapper checked the wrong
path.

## Safety

- Never use broad `pkill -f` against Schrödinger jobs.
- Check exact job ID/PID ownership before stopping a stale wrapper.
- Do not delete completed upstream LigPrep, docking, Morgan, or Shape artifacts while
  fixing a downstream adapter.
- After two same-class errors, stop full-set retries and return to a one-item probe.
