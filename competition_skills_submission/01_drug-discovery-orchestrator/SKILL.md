---
name: drug-discovery-orchestrator
description: Orchestrates the evidence-gated H0-H10 drug-discovery workflow. Use when a task needs target setup, generation, screening, ADMET, MD, monitoring, and one final report.
---

# Drug Discovery Orchestrator

## Concrete Operation Procedure

When the user supplies a target and final count, run the registry, planner, readiness,
and one-shot worker in this order:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
FINAL_COUNT=10
mkdir -p "tasks/${TARGET_ID}"
masld-agent platform-catalog --json > "tasks/${TARGET_ID}/00_registry.json"
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full --target-id "$TARGET_ID"
masld-agent funnel autopilot --final-count "$FINAL_COUNT" --profile full --target-id "$TARGET_ID"
masld-agent funnel autopilot --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" --execute --confirm --background
```

After launch call only `funnel_autopilot_status`. At every stage transition validate the
declared artifacts, call `funnel_report_update`, and record tools, observed counts,
interpretation, and next gate. `--profile test` requires an explicit test/smoke request.

This is the default entrypoint for an end-to-end E-Drug Lab task. Load this main skill
first, then load only the child skill required for the current stage.

Human-readable reports default to Chinese for the project audience. Every report-capable
tool and CLI accepts `language=en` or `--language en` for an English artifact; JSON schemas,
CSV column names, registry IDs, and validation flags remain stable.

## Child skills

- `e-drug-lab-scientist`: scientist behavior and evidence rules
- `funnel-orchestrator`: deterministic H0-H10 planning and execution
- `scientist-in-e-drug-lab`: compatibility entrypoint
- `funnel-campaign-memory`: persistent task state
- `time-scheduler`: adaptive wake-ups and local recovery
- `reporting`: one cumulative Markdown/DOCX/PDF report
- `edrug-capability-check`: platform and license gates

## Routing

1. Read the task memory, manifest, and current status.
2. For a new target, run `target-discovery` E0-E3 before H0.
3. Route H1 to `dd-generation`, H2/H5-H7 to `virtual-docking`, H3 to
   `featurehit-finding`, H4 to `admet`, H8-H9 to `molecular-dynamics`, and H10 to
   `all-analysis`.
4. After every validated stage, update `reporting` and flush `funnel-campaign-memory`.
5. For a background task, use `time-scheduler` and never launch a duplicate worker.

## Gates

- Use the project autopilot for count planning, resources, resume, and artifact reuse.
- Stop at the first failed or gated stage; report the exact blocker and path.
- Never turn planned counts into claimed results or invent scientific evidence.
- Keep all outputs under the resolved task root and use relative report provenance.

## Handoff

Every stage handoff includes stage ID, status, tools, inputs, observed count, warnings,
validated artifact paths, analysis, and the next allowed stage.

## Universal Manifest Invocation

This orchestrator is target-, disease-, library-, and backend-neutral. The task
caller supplies `task_id`, `skill`, `stage`, `campaign_root`, `inputs`, `outputs`,
`resources`, `validation`, `reporting`, and an explicit argv `command` or ordered
`steps`; no target or test profile is inferred from a small final count.

Use the shared runner for a read-only plan, hard output validation, and persisted
status:

```bash
bash scripts/run_skill.sh --skill drug-discovery-orchestrator --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill drug-discovery-orchestrator --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill drug-discovery-orchestrator --manifest MANIFEST --status
```

After checking the resolved argv and resource declaration, authorize execution:

```bash
bash scripts/run_skill.sh --skill drug-discovery-orchestrator --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill drug-discovery-orchestrator --manifest MANIFEST --resume --execute --confirm
```

Keep stage handoffs and reports inside `campaign_root`, use relative artifact
references, and stop on failed validation. The existing H0-H10 `funnel autopilot`
remains a separate full-profile planner; `--profile test` is explicit only.

## Universal Planning and Handoff

At task start, convert the requested final count into a declared stage plan before any
compute call. The plan records target or phenotype scope, input library hash, profile,
stage counts, expected retention ranges, resource allocation, monitoring interval,
report path, and stop conditions. Planned counts are never copied into observed counts.

For each stage use the same handoff fields: `stage`, `status`, `command_or_backend`,
`inputs`, `outputs`, `planned_count`, `observed_count`, `validation`, `resource_use`,
`warnings`, `analysis`, `report_section`, and `next_allowed_stage`. The receiving skill
must validate the referenced files and lineage IDs before it starts. A missing output,
wrong coordinate frame, incompatible format, unavailable tool, timeout, or failed
scientific gate yields `blocked` or `failed`, not an automatic retry with guessed options.

For long runs, the scheduler stores a durable heartbeat and exact process or job ID,
checks only the declared task at the manifest interval, and resumes from valid artifacts.
The reporting skill appends one section to the aggregate report after each validated
stage; it includes observed results, interpretation, limitations, and relative paths.

## Standalone Command-Line Procedure

The shared skill also has a manifest-free project entry. It derives stage quantities from
the requested final count and keeps the generated task state under the configured root:

```bash
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
FINAL_COUNT="${FINAL_COUNT:?requested final molecule count}"
PROFILE="${PROFILE:-full}"
masld-agent funnel plan --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" --profile "$PROFILE"
masld-agent funnel autopilot --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" \
  --profile "$PROFILE" --execute --confirm --background
masld-agent funnel autopilot-status --target-id "$TARGET_ID"
```

The entry is generic and does not select a target-specific path or fixed counts. Each
stage then follows its native command section (DiffDynamic, Glide, Shape/Phase, QikProp,
Desmond, and report export). Keep the printed task root, job IDs, stage counts, hashes,
and report path as the handoff to the next stage.
