---
name: funnel-orchestrator
description: Plan, preflight, execute, resume, validate, and report the H0-H10 drug-discovery funnel from a requested final molecule count. Use as the mandatory entrypoint for end-to-end tasks; use the test profile only for explicit smoke or test requests.
---

# Funnel Orchestrator

Use the project-owned Python interface. Do not assemble long inline shell programs.

```bash
masld-agent funnel autopilot --final-count 10 --profile full --target-id TARGET
masld-agent funnel autopilot --final-count 2 --profile test --target-id TARGET
masld-agent funnel autopilot --final-count 10 --profile full --target-id TARGET --execute --confirm --background
masld-agent funnel autopilot-status --target-id TARGET
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

Read `config/SOUL.md` and the campaign manifest before acting. Planned counts are
not completed counts. Advance only after `funnel validate` reports `valid=true`.
