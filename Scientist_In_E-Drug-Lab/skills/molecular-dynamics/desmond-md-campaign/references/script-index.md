# Portable Desmond Script Index

Run these project-owned utilities from the `desmond-md-campaign` skill directory
or use absolute script paths.

| Script | Purpose | Required explicit policy |
|---|---|---|
| `scripts/extract_medoid_cms.py` | Extract late-trajectory medoid full-system CMS inputs | Ligand ASL, pocket ASL, late window, clash thresholds |
| `scripts/validate_desmond_trajectory.py` | Validate final CMS/DTR duration and continuity | Minimum ns and expected frame interval |
| `scripts/campaign_status.py` | Inventory attempts without inferring completion from process names | Trajectory root and frozen molecule IDs |
| `scripts/run_sea.py` | Run or resume official SEA on validated trajectories | Protein ASL, ligand ASL, source layout |
| `scripts/analyze_md200.py` | Classify 200 ns pocket/contact retention | Target label, protein ASL, ligand ASL, manifest |
| `scripts/plot_md200_plate.py` | Render publication RMSD plates with Schrödinger Python | Valid traces and decision table |

Protocol templates are under `scripts/protocols/`. Reuse them through the
manifest and change only explicitly authorized parameters.

The archive under `scripts/hsd17b13_reference/` preserves historical,
target-specific implementation evidence. It is not a portable runner. Do not
copy its paths, IDs, ASLs, job names, component counts, or host settings into a
new task.
