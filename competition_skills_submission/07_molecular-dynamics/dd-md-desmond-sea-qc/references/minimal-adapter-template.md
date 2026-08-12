# SEA Portable Layout Adapter

The bundled runner already supports arbitrary validated CMS/DTR locations through
a source CSV. Use this adapter instead of copying or rewriting the SEA workflow.

## Source CSV contract

Create a stage-owned `sea_sources.csv`:

```csv
molecule_id,cms,trajectory
MOL_001,../../04_trajectories/MOL_001/final.cms,../../04_trajectories/MOL_001/final_trj
MOL_002,../../04_trajectories/MOL_002/final.cms,../../04_trajectories/MOL_002/final_trj
```

Relative paths resolve from the CSV directory. Each trajectory directory must
contain `clickme.dtr`; each CMS/DTR pair must already have a hard validation
record. Keep that validation record beside the source CSV or reference it from
the task manifest.

## Run

```bash
RUN="$(masld-agent platform-resolve --id sz.bin.run)"

"$RUN" python3 skills/desmond-md-campaign/scripts/run_sea.py \
  --run-launcher "$RUN" \
  --sources-csv <stage_dir>/sea_sources.csv \
  --output-root <stage_dir>/sea \
  --jobs <cpu_jobs> \
  --protein-asl '<protein_asl>' \
  --ligand-asl '<ligand_asl>' \
  --official-report
```

Use absolute paths to the bundled runner when the command's current directory is
not the project root. Do not change the runner's scientific sequence to adapt a
directory layout.

## Resume

The runner creates one output directory per molecule and reuses completed EAF
and report artifacts. If a report failed after analysis:

1. Confirm that the molecule's `*-out.eaf` is readable and non-empty.
2. Preserve the EAF and logs.
3. Use the report-only commands in
   [sea-commands-cheatsheet.md](sea-commands-cheatsheet.md).
4. Update the validation report without recomputing completed analysis.

## Validation checklist

- Source CSV has unique, non-empty molecule IDs.
- Every path resolves to the intended immutable CMS/DTR pair.
- Protein and ligand ASLs each select atoms in the exact CMS.
- Each molecule has a non-empty `PL_RMSD.dat` after completion.
- Requested plots/PDF and contact tables are non-empty.
- Numeric frame count and time range agree with the validated trajectory.
- Failures and retries remain isolated and auditable.
