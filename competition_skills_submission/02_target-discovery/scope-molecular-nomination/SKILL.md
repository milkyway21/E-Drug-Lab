---
name: scope-molecular-nomination
description: Use to lock nomination scope, resources, and outputs.
---

# Scope Molecular Nomination

Freeze the nomination question before gathering evidence or calculating scores. Keep
target-based and phenotype-first routes explicit because they require different evidence.

## When to Use

Use at the beginning of every new nomination or when the official library, phenotype,
target, final count, resource boundary, or submission contract changes.

## Prerequisites

Require disease/phenotype, organism and biological system, intended molecule modality,
official library path/ID, requested final count, online permission, compute authorization,
deadline, report language, and required experimental readouts.

## How to Run

Prefer the project evidence task planner. Without it, write a versioned JSON/YAML contract
and hash the official library. Never infer a test profile from a small final count.

## Quick Reference

Separate `requested_final_count`, `planned_stage_count`, `observed_count`, and
`validated_count`. Record inclusion/exclusion rules, acceptable evidence, stop conditions,
resource ceilings, and one canonical report location.

## Procedure

1. Normalize target, disease/phenotype, organism, cell context, and modality.
2. Freeze library identity, file hash, stable compound-ID field, and allowed transformations.
3. State target-based, phenotype-first, or hybrid mechanism policy.
4. Define final fields: ranking basis, toxicity, mechanism, uncertainty, validation plan.
5. Allocate resource ceilings and choose full/test profile explicitly.
6. Write the task plan before any downstream operation.

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

## Pitfalls

Do not silently replace the official library, normalize away a required compound identity,
assume docking is applicable, or omit negative and unknown evidence from the contract.

## Verification

Validate all required fields, library readability/hash, stable-ID uniqueness, final count,
resource limits, language, deliverables, and stop conditions before E1 or H0 begins.
