# SEA Official Command Reference

Prefer `skills/desmond-md-campaign/scripts/run_sea.py`. Use the commands below
only for diagnosis or report-only recovery.

## Required variables

```bash
: "${SCHRODINGER:?SCHRODINGER is required}"
: "${CMS:?validated final CMS is required}"
: "${TRJ:?validated production trajectory is required}"
: "${OUT_DIR:?SEA output directory is required}"
: "${MOLECULE_ID:?molecule ID is required}"
: "${PROTEIN_ASL:?protein ASL is required}"
: "${LIGAND_ASL:?ligand ASL is required}"

BASE_NAME="${MOLECULE_ID}_sea"
mkdir -p "${OUT_DIR}/data"
cd "${OUT_DIR}"
```

Resolve every path and ASL from the task manifest and hard validation record.
Do not infer the production stage from the largest directory number when a
validation record already identifies the final CMS/DTR.

## Official three-step sequence

```bash
CUDA_VISIBLE_DEVICES="" SCHRODINGER_CUDA_VISIBLE_DEVICES="" \
  "$SCHRODINGER/run" event_analysis.py analyze \
  "$CMS" -prot "$PROTEIN_ASL" -lig "$LIGAND_ASL" -out "$BASE_NAME"

CUDA_VISIBLE_DEVICES="" SCHRODINGER_CUDA_VISIBLE_DEVICES="" \
  nice -n 10 "$SCHRODINGER/run" analyze_simulation.py \
  -LOCAL -WAIT -JOBNAME "SEA_${MOLECULE_ID}" \
  "$CMS" "$TRJ" "${BASE_NAME}-out.eaf" "${BASE_NAME}-in.eaf"

MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
  "$SCHRODINGER/run" event_analysis.py report \
  "${BASE_NAME}-out.eaf" \
  -pdf "data/${BASE_NAME}-out.pdf" -data -plots -data_dir data
```

All three commands must use `OUT_DIR` as their current directory because
`event_analysis.py analyze -out` writes EAF files relative to the current
directory.

## Report-only recovery

If `*-out.eaf` is readable but combined report generation fails, preserve the
EAF and run:

```bash
"$SCHRODINGER/run" event_analysis.py report "${BASE_NAME}-out.eaf" \
  -data -data_dir data
"$SCHRODINGER/run" event_analysis.py report "${BASE_NAME}-out.eaf" \
  -plots -data_dir data
"$SCHRODINGER/run" event_analysis.py report "${BASE_NAME}-out.eaf" \
  -pdf "data/${BASE_NAME}-out.pdf"
```

If EAF files were written in another current directory, move the complete files
to `OUT_DIR` and resume reporting. Do not rerun
`analyze_simulation.py` solely to repair a path mistake.

## Output validation

Require, as applicable to the requested report:

- Non-empty `data/PL_RMSD.dat`.
- Non-empty RMSD plots and official PDF when requested.
- Contact tables needed by the analysis contract.
- Command logs and a completion/validation record.

Derive all frame counts from numeric data rows. Exclude the reference row from
production RMSD statistics, use the actual production rows for the late 20%
window, and use the actual analyzed frame set as contact-occupancy denominator.

## Failure diagnosis

| Symptom | Check | Resume action |
|---|---|---|
| `*-in.eaf` missing | CMS readability and both ASLs | Fix manifest/selector, rerun analyze only |
| `*-out.eaf` missing | DTR readability, disk, memory, analysis log | Rerun analysis only after fixing cause |
| Report missing but out EAF exists | Report log and headless plotting environment | Run report-only recovery |
| Empty or all-zero ligand columns | Ligand ASL atom count in the exact CMS | Correct selector; do not reinterpret zeros |
| Files in unexpected directory | Current directory used for each command | Move completed EAF files and resume |

RMSD cutoffs are screening heuristics. Combine them with pocket retention,
late-window behavior, and persistent direct contacts.
