---
name: scope-molecular-nomination
description: Use when starting a compound nomination task to lock the phenotype, library, requested final count, evidence policy, compute profile, and required reports before any biology or chemistry work.
---

# Scope Molecular Nomination

Create E0 before invoking target, structure, docking, or screening tools.

Required inputs:

- disease or phenotype and intended biological system
- official compound-library path and stable library identifier
- requested final molecule count
- target-based or phenotype-first mechanism policy
- online evidence permission and compute authorization

Write `evidence_task_plan.json`. Record an SHA-256 for the library and state whether
the run is online, cached replay, or offline. Never silently replace the official
library or infer that a small final count means a test profile.

For a complete computational funnel, call `funnel_autopilot` after E3. Preserve H0-H10
stage names. Evidence stages E0-E6 wrap that funnel rather than renumbering it.

Report completion with the locked inputs, unresolved inputs, artifact path, and next skill.

## Universal Manifest Invocation

Use a task manifest for every target or phenotype. It must include the library hash,
requested final count, profile, evidence policy, compute authorization, and an explicit
command or ordered steps; this skill does not infer a test profile from a small count.

```bash
bash scripts/run_skill.sh --skill scope-molecular-nomination --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill scope-molecular-nomination --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill scope-molecular-nomination --manifest MANIFEST --status
bash scripts/run_skill.sh --skill scope-molecular-nomination --manifest MANIFEST --execute --confirm
```

Before handoff, keep requested, planned, and observed counts separate. Derive stage counts
from the declared full or test profile, record CPU, GPU, memory, disk, and wall-time
estimates, and allocate only manifest-approved resources. Write a stop rule for every
stage: missing structure, invalid ligand, unavailable backend, failed validation, and
quota exhaustion produce a gated plan rather than an invented completion.
## Concrete Operation Procedure

Lock the official library and derive all intermediate quantities from the requested final count:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
FINAL_COUNT=10
LIBRARY="inputs/official_library.sdf"
TASK_ROOT="tasks/${TARGET_ID}/00_scope"
mkdir -p "$TASK_ROOT"
sha256sum "$LIBRARY" > "$TASK_ROOT/library.sha256"
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" > "$TASK_ROOT/funnel_plan.json"
jq '.stage_targets' "$TASK_ROOT/funnel_plan.json"
```

Use `--profile test` only when the user explicitly asks for a test. Keep requested, planned, and observed counts separate; record the library hash, evidence policy, compute authorization, GPU/CPU limits, reports, and a stop rule for every gate before handing off to target discovery.

## Standalone Command-Line Procedure

Plan quantities from the requested final count without relying on a task-specific table:

```bash
TARGET_ID="${TARGET_ID:?target identifier}"
FINAL_COUNT="${FINAL_COUNT:?requested final count}"
LIBRARY="${LIBRARY:?official compound library}"
OUT_DIR="${OUT_DIR:-scope}"
mkdir -p "$OUT_DIR"
sha256sum "$LIBRARY" > "$OUT_DIR/library.sha256"
masld-agent funnel plan --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" \
  --profile "${PROFILE:-full}" > "$OUT_DIR/funnel_plan.json"
jq '{target_id,requested_final_count,profile,stage_targets,resources,stop_conditions}' \
  "$OUT_DIR/funnel_plan.json"
```

Record requested, planned, and observed counts separately, plus library identity, evidence
policy, approved CPU/GPU/memory/disk, report location, and one stop condition per gate.
Do not use a test profile unless explicitly requested, and never promote a planned count
to an observed result.
