---
name: funnel-diffdynamic-prudent
description: Run H1b DiffDynamic Prudent generation, no-Vina physicochemical reconstruction, and canonical deduplication with resume-first behavior. Use for the prudent branch before Glide SP; do not execute Vina docking, scoring, or minimization.
---

# H1b DiffDynamic Prudent

Before generation, read the E2b structure manifest. DiffDynamic protein input must be the
coordinate-cleaned receptor file ending in `.pdb`, and ligand input must be the native ligand
file ending in `.sdf`. Never substitute the untouched complex, CIF/mmCIF, ligand PDB/MOL2,
or PrepWizard MAE/MAEGZ. If `diffdynamic_input.compatible` is false or either exact suffix is
missing, block H1B and return to structure preparation.

Prefer the existing Prudent runner and evaluator. The manifest command must use an
absolute PT path; never obtain it from an unchecked empty shell variable. Before
execution run the runner's `--help` and record the supported spelling of isolation
and timeout options.

The mandatory order is **Prudent generation → no-Vina reconstruction/physchem →
canonical dedup → H2 Glide SP**. Use `--vina-modes none` for analysis; this disables
AutoDock Vina execution. Do not run Vina dock/score/minimize during this analysis.
Existing Prudent Vina metadata embedded in a PT may remain as provenance but is not a
new analysis result.

Use the portable adapter instead of writing extraction code:

```bash
masld-agent funnel prudent-physchem --manifest MANIFEST
masld-agent funnel prudent-physchem --manifest MANIFEST --execute --confirm
```

Resume from already reconstructed SDFs;
do not top up a frozen set unless the user explicitly requests it. Completion
requires a readable unique CSV and valid structures, not the requested target count.

Isolation pitfall: in `evaluate_pt_with_correct_reconstruct.py`, an explicit
`--vina-modes none` parses to an empty tuple. The isolated worker must distinguish
that value from `None`; only `None` may fall back to the legacy default Vina modes.
If a no-Vina run logs dock/score_only/minimize attempts, inspect the worker's
truthiness fallback before rerunning. Preserve the current attempt until it exits,
apply the minimal generic fix, verify with a worker-level empty-mode regression
check, and only then create a new task-local attempt if hard validation fails.

```bash
masld-agent funnel run --manifest MANIFEST --stage H1B
masld-agent funnel validate --manifest MANIFEST --stage H1B
```
