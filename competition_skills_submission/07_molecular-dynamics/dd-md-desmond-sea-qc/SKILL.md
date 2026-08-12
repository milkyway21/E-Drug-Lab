---
name: dd-md-desmond-sea-qc
description: Run or resume official Schrödinger Simulation Event Analysis on a hard-validated Desmond CMS/DTR pair, then summarize RMSD and contacts with trajectory-derived frame counts. Use after short or long Desmond production; do not use for unvalidated trajectories or handwritten RMSD/contact analysis.
---

# Desmond SEA QC

## Concrete Operation Procedure

Validate production before SEA and resolve the Schrödinger Python launcher:

```bash
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
test -s "$CMS" && test -d "$TRAJECTORY_ROOT"
test "$(jq -r '.valid' "$VALIDATION_JSON")" = true
"$RUN" python3 skills/molecular-dynamics/desmond-md-campaign/scripts/run_sea.py \
  --run-launcher "$RUN" \
  --trajectory-root "$TRAJECTORY_ROOT" --output-root "$CAMPAIGN_ROOT/sea" \
  --ids "$MOLECULE_ID" --jobs "$CPU_JOBS" --protein-asl "$PROTEIN_ASL" \
  --ligand-asl "$LIGAND_ASL" --official-report
```

For another layout use `--sources-csv` with `molecule_id,cms,trajectory`. Parse numeric
`PL_RMSD.dat`, derive the late window from observed frames, calculate contact occupancy
by unique frame, and write per-molecule PASS/FAIL. SEA cannot rescue an invalid trajectory.

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
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
"$RUN" python3 skills/desmond-md-campaign/scripts/run_sea.py \
  --run-launcher "$RUN" \
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

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill dd-md-desmond-sea-qc --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill dd-md-desmond-sea-qc --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill dd-md-desmond-sea-qc --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill dd-md-desmond-sea-qc --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies validated CMS/DTR sources, explicit protein/ligand ASL, SEA command,
output directory, CPU resources, and report artifacts. The launcher does not infer a
residue selector, frame count, trajectory interval, or target label.

## Standalone Command-Line Procedure

Run the official SEA sequence only on a hard-validated CMS/DTR pair. Use the bundled
adapter with an installed Schrödinger `run` launcher:

```bash
SCHRODINGER="${SCHRODINGER:-}"
RUN="${RUN:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  RUN="${RUN:-$(masld-agent platform-resolve --id sz.bin.run)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
RUN="${RUN:-$SCHRODINGER/run}"
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
CMS="$(realpath inputs/validated_final.cms)"
TRJ="$(realpath inputs/validated_trj)"
OUT="$(realpath -m outputs/sea/MOLECULE_ID)"
mkdir -p "$OUT"
CUDA_VISIBLE_DEVICES="" SCHRODINGER_CUDA_VISIBLE_DEVICES="" \
  "$RUN" python3 \
  "$SKILLS_ROOT/molecular-dynamics/desmond-md-campaign/scripts/run_sea.py" \
  --run-launcher "$RUN" --sources-csv "$OUT/sea_sources.csv" \
  --output-root "$OUT" --protein-asl "${PROTEIN_ASL:?explicit protein ASL}" \
  --ligand-asl "${LIGAND_ASL:?explicit ligand ASL}" --official-report
```

The CSV must contain `molecule_id,cms,trajectory`. Check numeric RMSD rows, actual frame
counts, contact occupancy denominator, and report artifacts; SEA cannot rescue invalid
trajectory topology or an incorrect ligand selector.
