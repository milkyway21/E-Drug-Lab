---
name: funnel-diffdynamic-denovo
description: Use to run pocket-conditioned DiffDynamic generation.
---

# H1a DiffDynamic De Novo

Run native DiffDynamic sampling against a validated pocket while preserving exact inputs,
configuration, seed, GPU, raw PT output, and molecule lineage.

## When to Use

Use when the computational route enables pocket-conditioned de novo generation and the
structure-preparation manifest declares compatible PDB/SDF inputs.

## Prerequisites

- Clean receptor `.pdb`, same-frame native ligand `.sdf`, and qualified pocket.
- Task-local sampling YAML with a declared target count and immutable model checkpoint.
- Resolved Python environment, sampler, GPUs, seeds, timeout, disk, and attempt directory.

## How to Run

The agent defaults to a manifest command. Any agent or human can instead set `DD_ROOT` and
invoke `sample_diffusion.py` directly after checking the installed `--help` output.

## Quick Reference

| Parameter | Meaning | Rule |
| --- | --- | --- |
| Config count | Requested sampling amount | Set in task-local YAML |
| `--batch_size` | Per-step GPU memory batch | Do not use as total count |
| `--device` | One worker device | Isolate output and seed per GPU |
| `--result_path` | Attempt output | Never overwrite another seed |

## Procedure

1. Validate PDB/SDF suffixes, coordinate frame, hashes, and pocket gate.
2. Resolve Python, sampler, checkpoint, and config; save their versions and help.
3. Encode the requested count in a task-local config and set a memory-safe batch.
4. Launch one isolated process per GPU/seed and monitor exact PIDs or jobs.
5. Parse every PT and write observed counts, failures, and lineage before handoff.

Use the coordinate-cleaned receptor PDB from E2b, not the untouched complex and not
PrepWizard output. `inputs.receptor_pdb` must end in `.pdb` and
`inputs.reference_ligand_sdf` must end in `.sdf`; resolve both from
`structure_preparation_manifest.json.diffdynamic_input`. CIF/mmCIF, PDB ligand files,
MOL2, MAE, and MAEGZ are hard-gated. Confirm the receptor excludes water and the selected
ligand while retaining explicitly required metals/cofactors.

Configure `stages.H1A.command`
as an argv list pointing to an existing DiffDynamic runner; set `cwd` and environment
in the manifest instead of writing a new launcher.

```bash
masld-agent funnel run --manifest MANIFEST --stage H1A
masld-agent funnel run --manifest MANIFEST --stage H1A --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H1A
```

The expected evidence is a non-empty `result_*.pt` or a manifest-declared output.
Keep every retry under `logs/funnel/H1A/attempt_XX`; never overwrite an older run.

## Detailed Generic Procedure

### 1. Preflight the actual installation

Use existing project probes before allocating a GPU:

```bash
masld-agent platform-health
masld-agent platform-catalog --system dd
```

Record the resolved DiffDynamic environment, Python executable, sampler, weights, GPU
IDs, and free disk. If the catalog or health probe cannot resolve the backend, stop at
`blocked`; do not substitute a different generator.

### 2. Declare the generation command

The stage manifest names the command and working directory. A representative argv
contract is:

```bash
DD_PYTHON="$(masld-agent platform-resolve --id dd.env --field python)"
DD_SAMPLE="$(masld-agent platform-resolve --id dd.script.sample)"
"$DD_PYTHON" -u "$DD_SAMPLE" "$SAMPLING_CONFIG" \
  --protein_path "{campaign_root}/inputs/receptor_clean.pdb" \
  --protein_root "{campaign_root}/inputs" \
  --ligand_path "{campaign_root}/inputs/reference_ligand.sdf" \
  --result_path "{campaign_root}/01_h1a_diffdynamic" \
  --device "cuda:${GPU_ID}" --mode dynamic
```

Use the installed sampler help and project adapter to resolve option names. This is an
argv shape, not a hidden default. Configure batch size, seed, sampling mode, and output
directory in the manifest or existing template and preserve the generated config. Do not
put shell operators, `bash -c`, or inline Python in the manifest.

### 3. Validate the output

Inspect the PT with the existing DiffDynamic reader and require at least one complete
result object, a non-empty log, and a molecule count reconciled with the requested batch.
If the sampler emits multiple PT files, record every file and the deterministic
aggregation rule. Keep invalid reconstructions in a rejection table with PT index and
error; do not report planned count as generated count.

### 4. Handoff

Write `h1a_summary.json`, `generated_lineage.csv`, and a relative output manifest before
calling Prudent or docking. The next skill may run only when `valid=true`, clean PDB/SDF
inputs are unchanged, and declared artifact and lineage checks pass.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-diffdynamic-denovo --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-diffdynamic-denovo --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-diffdynamic-denovo --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-diffdynamic-denovo --manifest MANIFEST --resume --execute --confirm
```

The generic launcher executes only the command declared by the task manifest. It does
not choose a target, target count, GPU, sampler, or output location.

## Concrete Operation Procedure

Resolve the actual executable through the registry and run help before composing a
large command:

```bash
masld-agent platform-health
masld-agent platform-catalog --id dd.env --json
DD_PYTHON="$(masld-agent platform-resolve --id dd.env --field python)"
DD_SAMPLE="$(masld-agent platform-resolve --id dd.script.sample)"
DD_BATCH="$(masld-agent platform-resolve --id dd.script.batch)"
"$DD_PYTHON" -u "$DD_SAMPLE" --help
"$DD_PYTHON" -u "$DD_BATCH" --help
```

Derive the amount from the requested final count instead of typing a benchmark number:

```bash
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" > "$CAMPAIGN_ROOT/00_funnel_plan.json"
H1A_TARGET="$(jq -r '.stage_targets.H1A' "$CAMPAIGN_ROOT/00_funnel_plan.json")"
```

Preview and execute the existing project adapter with the clean PDB and same-frame SDF:

```bash
masld-agent diffdynamic-generate --protein "$CLEAN_RECEPTOR_PDB" \
  --ligand "$NATIVE_LIGAND_SDF" --mode denovo_fast --target-name "$TARGET_ID" \
  --batch-size "$H1A_TARGET" --output "$CAMPAIGN_ROOT/01_h1a_diffdynamic" \
  --gpus "$GPU_IDS" --dry-run
masld-agent diffdynamic-generate --protein "$CLEAN_RECEPTOR_PDB" \
  --ligand "$NATIVE_LIGAND_SDF" --mode denovo_fast --target-name "$TARGET_ID" \
  --batch-size "$H1A_TARGET" --output "$CAMPAIGN_ROOT/01_h1a_diffdynamic" \
  --gpus "$GPU_IDS" --confirm
```

If the project adapter cannot represent the installed sampler, use the registry-resolved
direct command only after the help probe: `"$DD_PYTHON" -u "$DD_SAMPLE" "$CONFIG"`
with `--protein_path "$CLEAN_RECEPTOR_PDB"`, `--ligand_path "$NATIVE_LIGAND_SDF"`,
`--device cuda:${GPU_ID}`, and a numbered `--result_path`. Split a large target by
seed/GPU, never by changing the input structure. Accept H1A only after PT records,
lineage, logs, and observed counts validate; planned count is not completion.

## Standalone Command-Line Procedure

Run the native sampler without a manifest or `masld-agent` wrapper. `DD_ROOT` and
`DD_PYTHON` are portable environment variables; if a registry is available it may
populate them, but the command remains ordinary Python invocation.

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
DD_SAMPLE="${DD_SAMPLE:-$DD_ROOT/scripts/sample_diffusion.py}"
CONFIG_YAML="$(realpath CONFIG.yml)"
RECEPTOR_PDB="$(realpath inputs/receptor_clean.pdb)"
LIGAND_SDF="$(realpath inputs/native_ligand.sdf)"
OUT_DIR="$(realpath -m outputs/01_h1a)"
GENERATE_COUNT="${GENERATE_COUNT:?requested molecule count encoded in CONFIG_YAML}"
SAMPLING_BATCH_SIZE="${SAMPLING_BATCH_SIZE:-1}"
mkdir -p "$OUT_DIR"
"$DD_PYTHON" -u "$DD_SAMPLE" "$CONFIG_YAML" \
  --protein_path "$RECEPTOR_PDB" \
  --protein_root "$(dirname "$RECEPTOR_PDB")" \
  --ligand_path "$LIGAND_SDF" \
  --device "cuda:${GPU_ID:-0}" \
  --batch_size "$SAMPLING_BATCH_SIZE" \
  --result_path "$OUT_DIR" --mode dynamic
```

Before launching, set the requested count in a task-local YAML copy. For baseline mode,
set `sample.num_samples`; for dynamic or Prudent mode, set the dynamic batch/repeat/
refinement or Prudent pool controls. The CLI `--batch_size` above is only a memory batch,
not a molecule count. For multiple GPUs, run one isolated output directory and seed/config per process, then
merge PT files only after each file passes its own parser and lineage check. First run
`"$DD_PYTHON" -u "$DD_SAMPLE" --help`; option spellings differ between DiffDynamic
forks. Reconstruct and validate with the evaluator command in the Prudent child, using
`--vina-modes none` when no Vina analysis is authorized.

## Pitfalls

- DiffDynamic forks differ in script location and option spelling; probe the installed CLI.
- Multiple workers must not write to one PT or output directory.
- Changing the config, checkpoint, or seed during resume creates a new attempt.
- A nonempty PT is not valid until the installed reader parses complete molecule records.

## Verification

Confirm immutable input/config/checkpoint hashes, unique seed and GPU per worker, normal worker
exit, readable PT files, reconciled requested and observed counts, rejection reasons, stable
generated IDs, and a validated summary before invoking Prudent or docking.
