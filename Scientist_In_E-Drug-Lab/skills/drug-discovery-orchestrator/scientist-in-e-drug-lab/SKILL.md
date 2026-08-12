---
name: scientist-in-e-drug-lab
description: Compatibility entrypoint for the generic E-Drug Lab H0-H10 discovery funnel. Use when a user asks the Scientist_In_E-Drug-Lab agent to plan, execute, resume, monitor, or report an end-to-end task; route to e-drug-lab-scientist and funnel-orchestrator.
---

# Scientist In E-Drug-Lab

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
6. Say 「任务」 rather than 「战役」 in user-facing Chinese.

## Capability Checks

Run these project interfaces instead of guessing installed backends:

```bash
masld-agent platform-health
masld-agent platform-catalog
masld-agent diffdynamic-status
masld-agent schrodinger-status
```

Do not modify Hermes core. Do not claim computational ranking as experimental proof.
