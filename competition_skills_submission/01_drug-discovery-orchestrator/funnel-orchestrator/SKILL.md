---
name: funnel-orchestrator
description: Plan, preflight, execute, resume, validate, and report the H0-H10 drug-discovery funnel from a requested final molecule count. Use as the mandatory entrypoint for end-to-end tasks; use the test profile only for explicit smoke or test requests.
---

# Funnel Orchestrator

## Concrete Operation Procedure

Use this operator sequence for any target. It plans from the requested final count and
leaves the manifest as parameter storage for reusable adapters:

```bash
masld-agent platform-health
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full --target-id "$TARGET_ID"
masld-agent funnel autopilot --final-count "$FINAL_COUNT" --profile full --target-id "$TARGET_ID"
masld-agent funnel autopilot --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" --execute --confirm --background
masld-agent funnel autopilot-status --target-id "$TARGET_ID"
```

If a manifest is already resolved, run `funnel preflight`, then `funnel run --stage Hn`
and `funnel validate --stage Hn` one stage at a time. Stop on gated preflight, missing
adapter, wrong format, or failed validation; never write a task-local replacement script.

This child skill is the deterministic execution component of the
`drug-discovery-orchestrator` master. Load the master first, then use this child only for
planning, preflight, execution, resume, and validation.

For a new target-based task, complete the evidence envelope first:

1. `scope-molecular-nomination` (E0)
2. `research-target-biology` (E1)
3. `rank-protein-structures` (E2)
4. `qualify-binding-pocket` (E3)

Only start a structure-based H0-H10 branch when E3 recommends docking. A phenotype-first
branch may continue without docking and must record structure evidence as `not_applicable`.

Load `time-scheduler` and `reporting` through `drug-discovery-orchestrator` as cross-stage
helpers. After a confirmed background
autopilot launch, create an adaptive one-shot Hermes monitor tick from `funnel_monitor_plan`.
After every completed stage, update the one consolidated report through `funnel_report_update`
before advancing. Do not create separate DOCX/PDF files per stage.

For a structure-based branch, H0 must validate the strict DiffDynamic handoff before H1:
`inputs.receptor_pdb` is the E2b coordinate-cleaned `.pdb` and
`inputs.reference_ligand_sdf` is the same-frame native `.sdf`. Resolve these from
`structure_preparation_manifest.json.diffdynamic_input`. Any CIF/mmCIF, ligand PDB/MOL2,
MAE/MAEGZ, untouched complex, or missing compatibility declaration blocks H1 automatically.

Use the project-owned Python interface. Do not assemble long inline shell programs.

```bash
masld-agent funnel autopilot --final-count 10 --profile full --target-id TARGET
masld-agent funnel autopilot --final-count 2 --profile test --target-id TARGET
masld-agent funnel autopilot --final-count 10 --profile full --target-id TARGET --execute --confirm --background
masld-agent funnel autopilot-status --target-id TARGET
masld-agent funnel monitor-plan --manifest MANIFEST
masld-agent funnel report-update --manifest MANIFEST --stage H2 --profile full
masld-agent funnel preflight --manifest MANIFEST
masld-agent funnel status --manifest MANIFEST
masld-agent funnel run --manifest MANIFEST --stage H3
masld-agent funnel validate --manifest MANIFEST --stage H3
```

If the human supplies only a desired final count, `autopilot` is the mandatory first
choice with `profile=full`. Use `profile=test` only after an explicit smoke/test request.
It derives all stage counts, detects local resources, writes a plan, processes
stages in order, and writes a report after every stage. Do not ask the model to reproduce
this logic conversationally.

Production execution performs a whole-pipeline readiness check before starting H1.
Every enabled downstream stage must already have a valid artifact or an available
argv adapter. If the result is `gated_preflight`, report `blocking_stages` and the
`PREFLIGHT_EXECUTION.json` path exactly. Do not write a task-local replacement script,
do not start H1 manually, and do not retry autopilot until the project adapter or input
is fixed. This prevents a long generation job from reaching a predictable H2/H3 gate.

`run` is preview-only unless `--execute` is present. Compute stages also require
`--confirm`. A valid existing artifact always wins over recomputation and returns
`reused_existing=true`.

Scale truth tables: `config/funnel_profiles/full.yaml` and `test.yaml`. Stage map:
H0 gate; H1a/H1b DiffDynamic; H2 primary SP; H3 FeatureHit/Shape;
H4 explicit ADMET backend; H5 refined SP; H6 XP; H7 MMGBSA; H8 short MD;
H9 long MD; H10 evidence curation.

After H10, call `enrich-compound-evidence` (E4), `triage-compound-toxicity` (E5),
`nominate-lipid-modulators`, and `write-mechanism-validation-report` (E6). These evidence
stages do not change H0-H10 count contracts. Each E stage and H stage must produce its own
JSON/Markdown status report before automatic continuation.

Read `config/SOUL.md` and the campaign manifest before acting. Planned counts are
not completed counts. Advance only after `funnel validate` reports `valid=true`.

## Universal Manifest Invocation

Use this orchestrator for any target and requested final count with a manifest that
declares all stage inputs/outputs, resources, validation, reporting, and explicit
argv `command` or ordered `steps`. Do not infer a target or switch to test mode.

```bash
bash scripts/run_skill.sh --skill funnel-orchestrator --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-orchestrator --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-orchestrator --manifest MANIFEST --status
bash scripts/run_skill.sh --skill funnel-orchestrator --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-orchestrator --manifest MANIFEST --resume --execute --confirm
```

Keep planned versus observed counts separate, report each stage, and stop on
failed validation or missing capability.

## Standalone Command-Line Procedure

Use the orchestrator without supplying a manifest; the planner creates the task state
and stage plan from the target and requested final count:

```bash
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
FINAL_COUNT="${FINAL_COUNT:?requested final molecule count}"
masld-agent funnel autopilot --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" \
  --profile "${PROFILE:-full}" --execute --confirm --background
masld-agent funnel autopilot-status --target-id "$TARGET_ID"
```

Use the stage-specific native sections when an adapter is not available. Do not pass a
test target, fixed local path, or guessed stage count into a general task. Stop and write
a gate when an input format, coordinate frame, backend, resource, or validator fails.
