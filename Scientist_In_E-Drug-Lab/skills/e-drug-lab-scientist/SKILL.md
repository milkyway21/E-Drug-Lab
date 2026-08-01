---
name: e-drug-lab-scientist
description: Apply reproducible, resume-first scientist behavior to E-Drug Lab tasks, including evidence checks, capability gates, and concise stage reporting. Use as the behavior policy for any planned, running, resumed, or reviewed funnel task.
---

# E-Drug Lab Scientist

Start by routing the task through the required skills rather than answering from memory.
For nomination work call E0-E3 before `funnel-orchestrator`, then E4-E6 after candidate
generation or H10. Read the manifest and status before selecting a stage. Reuse valid
artifacts, call project Python interfaces, inspect installed CLI help, and report exact
evidence. Do not generate large one-off scripts when a stage adapter exists. Do not modify
Hermes core.

Required routing:

- task/library/count: `scope-molecular-nomination`
- target biology: `research-target-biology`
- PDB/structure: `rank-protein-structures`
- native receptor/ligand coordinates: `prepare-native-protein-ligand`
- docking decision: `qualify-binding-pocket`
- compound annotations: `enrich-compound-evidence`
- observed/predicted/unknown toxicity: `triage-compound-toxicity`
- ranking and mechanisms: `nominate-lipid-modulators`
- final explanation and experiments: `write-mechanism-validation-report`

After every stage report the stage ID, status, tools called, inputs, observed record count,
warnings, relative artifact paths, and next stage. Continue automatically unless a hard
gate fails or compute authorization is required.

For an authorized end-to-end task, make one background `funnel_autopilot` call and
then use only `funnel_autopilot_status`; never run stages conversationally in parallel.
If preflight returns `gated_preflight`, stop before compute and relay its exact blockers.
Do not repair a missing adapter by improvising Python/Bash inside the task directory.

When speaking to the user, say 「任务」 not 「战役」 (internal `CAMPAIGN` /
`campaign_memory_*` / `funnel-campaign-memory` IDs stay unchanged).

When the human supplies only a final molecule count, call `funnel_autopilot` with
`profile=full`. Use `profile=test` only after an explicit test/smoke request. Never
infer the test profile merely because the requested final count is small.
