---
name: scientist-in-e-drug-lab
description: Compatibility entrypoint for the generic E-Drug Lab H0-H10 discovery funnel. Use when a user asks the Scientist_In_E-Drug-Lab agent to plan, execute, resume, monitor, or report an end-to-end task; route to e-drug-lab-scientist and funnel-orchestrator.
---

# Scientist In E-Drug-Lab

## Concrete Operation Procedure

Use this compatibility entrypoint only as a router; still run registered checks and the
deterministic worker:

```bash
masld-agent platform-catalog --json
masld-agent platform-health
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full --target-id "$TARGET_ID"
masld-agent funnel autopilot --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" --execute --confirm --background
masld-agent funnel autopilot-status --target-id "$TARGET_ID"
```

Read the current master and child operation procedure before each stage, then report the
real tool call and observed output count. Do not bypass master routing or assume a backend.

Treat this skill as a compatibility alias. Apply `drug-discovery-orchestrator` and
`e-drug-lab-scientist` behavior, then use `funnel-orchestrator` for deterministic execution.
The cross-stage helpers are `time-scheduler` and `reporting`; keep one cumulative report
rather than one document per stage.

## Deterministic Entry

When the user provides a final molecule count, call one autopilot operation:

```bash
masld-agent funnel autopilot --final-count N --profile full --target-id TARGET
```

Use `--profile test` only when the user explicitly requests a test, smoke, or pilot.
Add `--execute --confirm --background` only after explicit compute authorization.
After launch, use only:

```bash
masld-agent funnel autopilot-status --target-id TARGET
```

## Required Behavior

1. Read `config/SOUL.md`, the resolved manifest, and current funnel status.
2. Require `ready_for_one_shot_execution=true` before production starts.
3. If preflight returns `gated_preflight`, report its exact `blocking_stages` and
   report path; do not start H1 or improvise task-local Python/Bash adapters.
4. Reuse hard-validated artifacts and preserve molecule, parent, pose, and trajectory
   lineage.
5. Trust stage JSON/Markdown reports and artifact validation, not chat claims or
   `.done` markers.
6. Use the Chinese user-facing term for "task" rather than the legacy term "campaign".
7. Human-readable reports default to Chinese; use `language=en` or `--language en` for an
   English artifact while retaining stable machine-readable keys and IDs.

## Capability Checks

Run these project interfaces instead of guessing installed backends:

```bash
masld-agent platform-health
masld-agent platform-catalog
masld-agent diffdynamic-status
masld-agent schrodinger-status
```

Do not modify Hermes core. Do not claim computational ranking as experimental proof.

## Universal Manifest Invocation

Use this scientist skill for any target or disease with a manifest defining task
identity, current stage, inputs, outputs, resources, validation, reporting, and
explicit argv `command` or ordered `steps`. No target or backend is assumed.

```bash
bash scripts/run_skill.sh --skill scientist-in-e-drug-lab --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill scientist-in-e-drug-lab --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill scientist-in-e-drug-lab --manifest MANIFEST --status
bash scripts/run_skill.sh --skill scientist-in-e-drug-lab --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill scientist-in-e-drug-lab --manifest MANIFEST --resume --execute --confirm
```

Keep evidence, tool calls, state, and reports below `campaign_root`; adapt through
skills and project plugins without changing Hermes core.

## Standalone Command-Line Procedure

Probe the shared installation and then launch the generic funnel without a manifest:

```bash
masld-agent platform-health
masld-agent platform-catalog --json > "${PLATFORM_REPORT:-platform_catalog.json}"
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
FINAL_COUNT="${FINAL_COUNT:?requested final molecule count}"
masld-agent funnel autopilot --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" \
  --profile "${PROFILE:-full}" --execute --confirm --background
```

Use the returned registry IDs and stage outputs to select native binaries. The scientist
must record tool/version probes, exact argv, input/output hashes, validation status, and
the cumulative report; it must not claim success from a planned or unavailable job.
