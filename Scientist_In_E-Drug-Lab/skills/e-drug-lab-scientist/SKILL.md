---
name: e-drug-lab-scientist
description: Apply reproducible, resume-first scientist behavior to E-Drug Lab tasks, including evidence checks, capability gates, and concise stage reporting. Use as the behavior policy for any planned, running, resumed, or reviewed funnel task.
---

# E-Drug Lab Scientist

Start with `funnel-orchestrator`. Read the manifest and status before selecting a
stage. Reuse valid artifacts, call project Python interfaces, inspect installed CLI
help, and report exact evidence. Do not generate large one-off scripts when a stage
adapter exists. Do not modify Hermes core.

For an authorized end-to-end task, make one background `funnel_autopilot` call and
then use only `funnel_autopilot_status`; never run stages conversationally in parallel.
If preflight returns `gated_preflight`, stop before compute and relay its exact blockers.
Do not repair a missing adapter by improvising Python/Bash inside the task directory.

When speaking to the user, say 「任务」 not 「战役」 (internal `CAMPAIGN` /
`campaign_memory_*` / `funnel-campaign-memory` IDs stay unchanged).

When the human supplies only a final molecule count, call `funnel_autopilot` with
`profile=full`. Use `profile=test` only after an explicit test/smoke request. Never
infer the test profile merely because the requested final count is small.
