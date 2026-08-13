---
name: scientist-in-e-drug-lab
description: Use to route requests into the generic discovery funnel.
---

# Scientist In E-Drug-Lab

Provide a compatibility name for the general discovery scientist. Route work to the
current master and child skills instead of embedding a target-specific workflow here.

## When to Use

Use when an external client, older prompt, or slash command invokes the historical
Scientist In E-Drug-Lab name.

## Prerequisites

Require the same task scope, capabilities, current state, and resource authorization as
`e-drug-lab-scientist`. Do not use compatibility routing to bypass validation.

## How to Run

Route behavior to `e-drug-lab-scientist`, planning to `funnel-orchestrator`, and each
scientific operation to the corresponding category child. Use the project CLI if present;
otherwise follow the child's standalone procedure.

## Quick Reference

Compatibility affects naming only. It must not change stage order, counts, scientific
methods, output paths, identity lineage, reporting language, or completion criteria.

## Procedure

1. Normalize the request into target/phenotype, library, final count, resources, and output.
2. Read current task state and identify the next eligible child skill.
3. Run capability checks and the orchestrator.
4. Return exact task root, current stage, job ID, observed count, and report path.

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

## Pitfalls

Do not duplicate the whole funnel inside this compatibility skill, select a hidden workflow,
or revive retired flat skill names as separate capabilities.

## Verification

Verify that the request resolves to one canonical master/child path and that no duplicate
Hermes skill name appears. Confirm outputs match the canonical route.
