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

## Universal Manifest Invocation

Use this skill for any target with a clean receptor PDB, same-frame native ligand
SDF, and validated Prudent artifacts declared in the manifest. Supply outputs,
resources, validation, reporting, and an explicit argv `command` or ordered `steps`.

```bash
bash scripts/run_skill.sh --skill funnel-diffdynamic-prudent --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-diffdynamic-prudent --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-diffdynamic-prudent --manifest MANIFEST --status
bash scripts/run_skill.sh --skill funnel-diffdynamic-prudent --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-diffdynamic-prudent --manifest MANIFEST --resume --execute --confirm
```

The explicit command may call `masld-agent funnel prudent-physchem`; preserve
`--vina-modes none` and all target-local outputs under `campaign_root`.

## Detailed Prudent Procedure

### 1. Separate generation from analysis

Use `masld-agent funnel prudent-generate --manifest MANIFEST` for the existing Prudent
sampler and `masld-agent funnel prudent-physchem --manifest MANIFEST` for reconstruction
and physicochemical analysis. They are separate resumable units:

```bash
masld-agent funnel prudent-generate --manifest MANIFEST
masld-agent funnel prudent-generate --manifest MANIFEST --execute --confirm
masld-agent funnel prudent-physchem --manifest MANIFEST
masld-agent funnel prudent-physchem --manifest MANIFEST --execute --confirm
```

The first command reads the clean receptor PDB and same-frame native ligand SDF, renders
the configured template, derives batch size from the manifest target, and runs the
existing sampler. The second selects explicit `stages.H1B.pt_path` or a manifest-scoped
`pt_glob`, calls the existing evaluator, and writes reconstructed SDF and summary. Do not
replace either operation with a task-local Python program.

### 2. Required manifest fields

`stages.H1B` may declare `target_count`, `config_template`, `diffdynamic_python`,
`sampler`, `generation_output_dir`, `generated_config_dir`, `pt_path` or `pt_glob`,
`evaluator`, `physchem_output_dir`, `dedup_output_dir`, generation/physchem timeouts,
and `save_intermediate_interval`. The manifest also declares PT, reconstructed SDF,
unique CSV, summary JSON, logs, GPU, timeout, and report outputs.

### 3. No-Vina analysis gate

The evaluator argv must contain the explicit pair:

```text
["--vina-modes", "none"]
```

The report states `vina_executed=false` and `vina_modes=none`. Prudent internal selection
is not retroactively called a Vina result. If the log contains `dock`, `score_only`, or
`minimize` execution, stop and inspect empty-mode handling before accepting output; do
not delete the failed attempt.

### 4. Physchem and dedup validation

For every reconstructed record retain PT index, generated ID, source file, parse status,
canonical SMILES, QED, SA, MW, LogP, TPSA, and invalid/duplicate reason. Deduplicate after
parse validation with a deterministic canonical key. Require readable `unique.csv`, a
non-empty unique SDF directory, JSON summary, and agreement between CSV rows and SDF
records. A shortfall is reported before H2; never duplicate molecules or relax filters.

### 5. Handoff to Glide

Freeze the unique table and library paths. Downstream Glide receives only the declared
clean receptor/grid and frozen ligand set; it must not rerun Prudent or select from an
unvalidated intermediate directory. Store exact command argv and H1 report under the
task root.

## Concrete Operation Procedure

Resolve Prudent and evaluator executables from the registry, then verify the strict input
contract:

```bash
masld-agent platform-health
masld-agent platform-catalog --id dd.cfg.prudent --json
DD_PYTHON="$(masld-agent platform-resolve --id dd.env --field python)"
DD_EVAL="$(masld-agent platform-resolve --id dd.script.eval)"
DD_EXTRACT="$(masld-agent platform-resolve --id dd.script.extract)"
"$DD_PYTHON" -u "$DD_EVAL" --help
"$DD_PYTHON" -u "$DD_EXTRACT" --help
test "${CLEAN_RECEPTOR_PDB##*.}" = pdb
test "${NATIVE_LIGAND_SDF##*.}" = sdf
```

Get the H1B target from the planner:

```bash
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" > "$CAMPAIGN_ROOT/00_funnel_plan.json"
H1B_TARGET="$(jq -r '.stage_targets.H1B' "$CAMPAIGN_ROOT/00_funnel_plan.json")"
```

Run the existing resumable adapter; it reads the manifest template and target-sized
configuration, so the manifest is parameter storage rather than the procedure:

```bash
masld-agent funnel prudent-generate --manifest "$MANIFEST"
masld-agent funnel prudent-generate --manifest "$MANIFEST" --execute --confirm
masld-agent funnel validate --manifest "$MANIFEST" --stage H1B
```

For the analysis handoff, keep Vina explicitly disabled:

```bash
masld-agent diffdynamic-extract --pt "$PT_FILE" --vina-modes none \
  --output "$CAMPAIGN_ROOT/01_h1b_physchem" --dry-run
masld-agent diffdynamic-extract --pt "$PT_FILE" --vina-modes none \
  --output "$CAMPAIGN_ROOT/01_h1b_physchem"
masld-agent funnel prudent-physchem --manifest "$MANIFEST" --execute --confirm
```

Search the log for `dock`, `score_only`, or `minimize`; any new invocation invalidates
the no-Vina result. Freeze the unique CSV/SDF only after parse, canonical deduplication,
record-count agreement, and lineage validation. H2 receives those frozen files, never a
PT glob or an unvalidated intermediate directory.

## Standalone Command-Line Procedure

The native scripts can be launched without a manifest and without the project adapter.
Use a clean receptor PDB and same-frame native ligand SDF. The Prudent runner obtains its
generation policy from `CONFIG_YAML`; it does not take a molecule count flag, so the
requested count must be encoded in that configuration and checked against observed output.

```bash
DD_ROOT="${DD_ROOT:-}"
DD_PYTHON="${DD_PYTHON:-}"
if [ -z "${DD_ROOT}" ] && command -v masld-agent >/dev/null 2>&1; then
  DD_ROOT="$(masld-agent platform-resolve --id dd.env)"
fi
if [ -z "${DD_PYTHON}" ] && command -v masld-agent >/dev/null 2>&1; then
  DD_PYTHON="$(masld-agent platform-resolve --id dd.env --field python)"
fi
DD_ROOT="${DD_ROOT:?set DD_ROOT or make dd.env resolvable}"
DD_PYTHON="${DD_PYTHON:-python}"
DD_PRUDENT="${DD_PRUDENT:-$DD_ROOT/run_prudent_generations.py}"
DD_EVAL="${DD_EVAL:-$DD_ROOT/evaluate_pt_with_correct_reconstruct.py}"
DD_EXTRACT="${DD_EXTRACT:-$DD_ROOT/extract_pt_to_sdf_excel.py}"
CONFIG_YAML="$(realpath CONFIG.yml)"
RECEPTOR_PDB="$(realpath inputs/receptor_clean.pdb)"
LIGAND_SDF="$(realpath inputs/native_ligand.sdf)"
OUT_DIR="$(realpath -m outputs/01_h1b)"
mkdir -p "$OUT_DIR"
"$DD_PYTHON" -u "$DD_PRUDENT" --help
"$DD_PYTHON" -u "$DD_PRUDENT" \
  --protein_path "$RECEPTOR_PDB" --ligand_path "$LIGAND_SDF" \
  --config "$CONFIG_YAML" --gpu "${GPU_ID:-0}" \
  --timeout "${PRUDENT_TIMEOUT_SECONDS:-7200}" --output_dir "$OUT_DIR"
PT_FILE="$(find "$OUT_DIR" -type f -name '*.pt' -print -quit)"
test -n "$PT_FILE" && test -s "$PT_FILE"
"$DD_PYTHON" -u "$DD_EVAL" "$PT_FILE" \
  --protein_root "$(dirname "$RECEPTOR_PDB")" \
  --receptor_pdb "$RECEPTOR_PDB" --reference_ligand "$LIGAND_SDF" \
  --output_dir "$OUT_DIR/physchem" --save_sdf --vina-modes none
```

`extract_pt_to_sdf_excel.py` is a convenience wrapper around the same evaluator. If
used, put `--vina-modes none` after the `--` separator so it is forwarded explicitly:

```bash
"$DD_PYTHON" -u "$DD_EXTRACT" "$PT_FILE" \
  --protein_root "$(dirname "$RECEPTOR_PDB")" \
  --output_dir "$OUT_DIR/extract" -- \
  --receptor_pdb "$RECEPTOR_PDB" --reference_ligand "$LIGAND_SDF" \
  --vina-modes none
```

Search the evaluator log for `dock`, `score_only`, and `minimize`; no new Vina call is
allowed in this branch. Keep every PT, SDF, CSV, rejection table, and command log under
the numbered output directory, and report shortfalls instead of duplicating molecules.
