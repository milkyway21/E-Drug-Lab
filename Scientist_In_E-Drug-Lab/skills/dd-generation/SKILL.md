---
name: dd-generation
description: Runs the validated DiffDynamic generation and Prudent optimization handoff. Use for H1 de novo generation after target and pocket gates pass.
---

# DD Generation

This main skill routes H1a/H1b while preserving the strict protein/ligand handoff and
validated molecule lineage.

## Child skills

- `funnel-diffdynamic-denovo` for H1a pocket-conditioned generation
- `funnel-diffdynamic-prudent` for H1b Prudent generation and post-processing

## Contract

- Input receptor is the cleaned `.pdb` from target preparation.
- Input reference ligand is the same-frame `.sdf`.
- Prudent post-processing uses `--vina-modes none`; compute physicochemical properties,
  canonical deduplication, and validation before H2.
- Reuse a valid existing attempt instead of creating a new attempt directory.

## Gate

Validate generated counts, parseable structures, lineage, and report artifacts before
loading `virtual-docking`. A generation failure stops the funnel.

## Universal Manifest Invocation

This skill is reusable for any target, disease, library, and validated backend. The
caller must provide a generic manifest with task identity, stage, inputs, outputs,
resources, validation, reporting, and an explicit argv `command` or ordered `steps`.
Do not infer a target, path, molecule count, or backend from the skill name.

Preview and validate before external computation:

```bash
bash scripts/run_skill.sh --skill dd-generation --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill dd-generation --manifest MANIFEST --validate
```

After reviewing the preview, execution requires an explicit confirmation:

```bash
bash scripts/run_skill.sh --skill dd-generation --manifest MANIFEST --execute --confirm
```

Use `--status` for the persisted result and `--resume --execute --confirm` to
reuse valid outputs or continue an incomplete attempt. Keep paths relative to
`campaign_root`, preserve molecule lineage, and stop when declared validation fails.

## Generic H1 Method

### Inputs and preflight

The H1 manifest declares `inputs.receptor_pdb`, `inputs.reference_ligand_sdf`, the
generation backend, requested count, GPU allocation, and output contract. The receptor
PDB is the coordinate-cleaned protein from structure preparation; the ligand SDF is the
same-frame deposited or reference ligand. Reject CIF/mmCIF, ligand PDB, MOL2, MAE, and
MAEGZ at this boundary. Before a long call, run project health and capability probes and
record the selected DiffDynamic Python, sampler, weights, template, device, seed, batch
size, and working directory.

### H1a/H1b sequence

1. Validate the structure handoff and pocket center before generation.
2. Generate with the existing DiffDynamic runner using an explicit manifest command.
3. Preserve the raw PT and log; do not convert or filter it in place.
4. Reconstruct PT to SDF and compute Prudent physicochemical properties only when H1b is
   enabled. In the no-Vina path use `--vina-modes none`; this means no new Vina docking,
   scoring, or minimization during analysis.
5. Canonicalize and deduplicate with RDKit, retaining invalid records and duplicate counts.
6. Write an H1 summary containing generated PT count, reconstructed SDF count, valid
   structures, unique structures, physchem statistics, Vina mode, failures, and H2 handoff.

### Resume and monitoring

Use one numbered attempt per execution. Monitor the exact process or scheduler job, latest
log timestamp, PT file growth, GPU ownership, and free disk. A stale wrapper does not
justify killing a live worker. When the PT passes validation, `--resume` reuses it; when
reconstruction or deduplication failed, resume only that downstream unit. Never top up a
frozen set without an explicit plan change.

### Hard completion gate

H1 is complete only when the declared PT or SDF, summary, lineage table, and count
validation are readable and non-empty. A requested count is not an observed count. If
valid unique molecules are fewer than requested, report the shortfall and reason; do not
duplicate structures or silently relax filters.

## Concrete Operation Procedure

Resolve the generator from the platform registry before allocating a GPU:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
FINAL_COUNT=10
TASK_ROOT="tasks/${TARGET_ID}"
mkdir -p "$TASK_ROOT/00_plan" "$TASK_ROOT/01_h1a" "$TASK_ROOT/01_h1b"
masld-agent platform-health
masld-agent platform-catalog --system dd > "$TASK_ROOT/00_plan/dd_registry.json"
DD_ROOT="$(masld-agent platform-resolve --id dd.env)"
DD_PYTHON="$(masld-agent platform-resolve --id dd.env --field python)"
DD_SAMPLE="$(masld-agent platform-resolve --id dd.script.sample)"
DD_BATCH="$(masld-agent platform-resolve --id dd.script.batch)"
test -d "$DD_ROOT" && test -x "$DD_PYTHON" && test -f "$DD_SAMPLE" && test -f "$DD_BATCH"
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" > "$TASK_ROOT/00_plan/funnel_plan.json"
jq '.stage_targets | {H1A,H1B,H2}' "$TASK_ROOT/00_plan/funnel_plan.json"
```

Use `H1A` and `H1B` from the plan as targets. For a large target, divide the planned
count across GPUs returned by the registered `dd.gpu.policy` entry, use distinct seeds
and numbered attempt directories, and merge only after PT/structure validation. The
handoff is H1A generation -> H1B Prudent -> no-Vina physchem -> canonical dedup -> H2.
Record planned, generated, readable, invalid, and unique counts at every arrow.

## Standalone Command-Line Procedure

The manifest is the default agent interface, but it is not required for a manual or
non-Hermes run. Set task-local variables and call the installed DiffDynamic scripts
directly. The registry block is optional; without it, provide `DD_ROOT`, `DD_PYTHON`,
and the script variables yourself.

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
CAMPAIGN_ROOT="$(pwd)/tasks/${TARGET_ID}"
CONFIG_YAML="$(realpath CONFIG.yml)"
CLEAN_RECEPTOR_PDB="$(realpath inputs/receptor_clean.pdb)"
NATIVE_LIGAND_SDF="$(realpath inputs/native_ligand.sdf)"
GENERATE_COUNT="${GENERATE_COUNT:?requested molecule count encoded in CONFIG_YAML}"
SAMPLING_BATCH_SIZE="${SAMPLING_BATCH_SIZE:-1}"
DD_ROOT="${DD_ROOT:-}"
DD_PYTHON="${DD_PYTHON:-}"
if [ -z "${DD_ROOT}" ] && command -v masld-agent >/dev/null 2>&1; then
  DD_ROOT="$(masld-agent platform-resolve --id dd.env)"
fi
if [ -z "${DD_ROOT}" ]; then
  printf '%s\n' 'Set DD_ROOT to the DiffDynamic installation root.' >&2
  exit 2
fi
if [ -z "${DD_PYTHON}" ] && command -v masld-agent >/dev/null 2>&1; then
  DD_PYTHON="$(masld-agent platform-resolve --id dd.env --field python)"
fi
DD_PYTHON="${DD_PYTHON:-python}"
DD_SAMPLE="${DD_SAMPLE:-$DD_ROOT/scripts/sample_diffusion.py}"
DD_PRUDENT="${DD_PRUDENT:-$DD_ROOT/run_prudent_generations.py}"
DD_EVAL="${DD_EVAL:-$DD_ROOT/evaluate_pt_with_correct_reconstruct.py}"
test -f "$DD_SAMPLE" && test -f "$DD_PRUDENT" && test -f "$DD_EVAL"
mkdir -p "$CAMPAIGN_ROOT/01_h1a" "$CAMPAIGN_ROOT/01_h1b" "$CAMPAIGN_ROOT/logs"
"$DD_PYTHON" -u "$DD_SAMPLE" "$CONFIG_YAML" \
  --protein_path "$CLEAN_RECEPTOR_PDB" \
  --protein_root "$(dirname "$CLEAN_RECEPTOR_PDB")" \
  --ligand_path "$NATIVE_LIGAND_SDF" \
  --device "cuda:${GPU_ID:-0}" --batch_size "$SAMPLING_BATCH_SIZE" \
  --result_path "$CAMPAIGN_ROOT/01_h1a" --mode dynamic \
  2>&1 | tee "$CAMPAIGN_ROOT/logs/h1a.log"
```

Use a task-local copy of the YAML to set `sample.num_samples` for baseline mode, or the
dynamic/Prudent count controls (`dynamic.large_step.batch_size`, `n_repeat`, refinement
sampling, and Prudent pool policy) for those modes. `--batch_size` is only the per-step
GPU batch and must not be used as the requested final count. The observed PT/SDF count,
parse failures, and canonical unique count must be written before the next stage. For
reconstruction-only analysis, pass the explicit receptor and
native ligand and add `--vina-modes none`; this is the no-Vina physchem route, not a
claim that the generator itself has no internal Prudent scoring.
