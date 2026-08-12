---
name: dd-md-desmond-sea-qc
description: Run or resume official Schrödinger Simulation Event Analysis on a hard-validated Desmond CMS/DTR pair, then summarize RMSD and contacts with trajectory-derived frame counts. Use after short or long Desmond production; do not use for unvalidated trajectories or handwritten RMSD/contact analysis.
---

# Desmond SEA QC

Use the bundled `desmond-md-campaign/scripts/run_sea.py` adapter. It preserves
the official `event_analysis.py` → `analyze_simulation.py` → report sequence,
supports resumption, and avoids target-specific scripts.

## Required inputs

Before SEA, require all of the following:

- A readable final CMS and production trajectory containing `clickme.dtr`.
- A hard validation report whose `valid` field is true.
- Explicit protein and ligand ASL values from the task manifest or prepared
  system. Never assume the ligand residue name.
- A manifest-declared output directory and molecule ID.

`res.ptype UNK` is only an example for systems that were actually prepared with
that residue type. It is not a universal ligand selector.

## Preferred execution

For the standard `attempt_XX` layout:

```bash
"$SCHRODINGER/run" python3 skills/desmond-md-campaign/scripts/run_sea.py \
  --trajectory-root <trajectory_root> \
  --output-root <analysis_root>/sea \
  --ids <ID1> <ID2> \
  --jobs <cpu_jobs> \
  --protein-asl '<protein_asl>' \
  --ligand-asl '<ligand_asl>' \
  --official-report
```

For another layout, write `sea_sources.csv` with
`molecule_id,cms,trajectory` and use `--sources-csv`. Relative paths resolve
from the CSV directory. Do not copy or rewrite the SEA runner merely to adapt
paths.

Run SEA as a CPU task. Keep `CUDA_VISIBLE_DEVICES` and
`SCHRODINGER_CUDA_VISIBLE_DEVICES` empty. The adapter runs all official commands
from each molecule's SEA output directory so EAF files remain colocated.

## Resume and recovery

- Reuse readable `*-in.eaf`, `*-out.eaf`, and report data.
- If analysis completed but report generation failed, rerun only the report.
- If EAF files were created in the wrong directory, move them into the declared
  SEA output directory and continue; do not recompute the trajectory analysis.
- Never mark SEA complete from a process exit alone. Require `PL_RMSD.dat`, the
  requested report artifacts, and a success marker or validation record.

The exact official command sequence and report-only recovery procedure are in
[references/sea-commands-cheatsheet.md](references/sea-commands-cheatsheet.md).
Use [references/minimal-adapter-template.md](references/minimal-adapter-template.md)
only when the bundled runner cannot represent an existing directory layout.

## Dynamic statistics

Do not hard-code 52, 51, or any other frame count. Those values describe only a
particular duration and recording interval.

For `PL_RMSD.dat`:

1. Parse only rows whose first field is numeric.
2. Treat frame 0 as the reference row when SEA labels it as such.
3. Exclude the reference row from production RMSD means and extrema.
4. Set `production_frames` to the actual remaining row count.
5. Define the late window as the final `max(1, ceil(0.20 × production_frames))`
   production rows.
6. Record the detected frame count, time range, and interval beside every
   summary so the result is auditable.

For contact tables:

- An event row is not a frame occupancy.
- Deduplicate by frame before computing a residue or interaction occupancy.
- Use the actual analyzed frame set as the denominator.
- Report event count, unique-contact frames, denominator, and occupancy
  separately.

## Interpretation gate

RMSD thresholds are triage aids, not automatic biological proof. Evaluate
protein stability, ligand-to-protein RMSD, late-window drift, pocket retention,
and persistent contacts together. A readable RMSD table cannot rescue a ligand
that leaves the intended pocket.

Report after the stage: validated inputs, exact commands/backend, frame counts,
generated artifacts, failures/retries, and a per-molecule PASS/FAIL decision.
