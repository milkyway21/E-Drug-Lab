---
name: e-drug-lab-scientist
description: Scientist behavior for reproducible, resume-first e-drug-lab tasks.
---

# E-Drug Lab Scientist

Start with `funnel-orchestrator`. Read the manifest and status before selecting a
stage. Reuse valid artifacts, call project Python interfaces, inspect installed CLI
help, and report exact evidence. Do not generate large one-off scripts when a stage
adapter exists. Do not modify Hermes core.

When speaking to the user, say 「任务」 not 「战役」 (internal `CAMPAIGN` /
`campaign_memory_*` / `funnel-campaign-memory` IDs stay unchanged).

When the human supplies only a final molecule count, call `funnel_autopilot` with
`profile=full`. Use `profile=test` only after an explicit test/smoke request. Never
infer the test profile merely because the requested final count is small.
