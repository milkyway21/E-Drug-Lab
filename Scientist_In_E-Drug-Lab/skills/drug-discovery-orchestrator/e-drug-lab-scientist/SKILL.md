---
name: e-drug-lab-scientist
description: Apply reproducible, resume-first scientist behavior to E-Drug Lab tasks, including evidence checks, capability gates, and concise stage reporting. Use as the behavior policy for any planned, running, resumed, or reviewed funnel task.
---

# E-Drug Lab Scientist

Start by loading the `drug-discovery-orchestrator` master skill and route through its eight
master categories rather than answering from memory. Load only the current master category
and required child skill; use `time-scheduler` for long-task wake/recovery and `reporting`
for the single cumulative DOCX/PDF report. Reuse backend-specific skills rather than
duplicating them.
For nomination work call E0-E3 before `funnel-orchestrator`, then E4-E6 after candidate
generation or H10. Read the manifest and status before selecting a stage. Reuse valid
artifacts, call project Python interfaces, inspect installed CLI help, and report exact
evidence. Do not generate large one-off scripts when a stage adapter exists. Do not modify
Hermes core.

Required routing:

- default entry: `drug-discovery-orchestrator`
- target and structure gate: `target-discovery`
- H1: `dd-generation`
- H2/H5-H7: `virtual-docking`
- H3: `featurehit-finding`
- H4/E4-E5: `admet`
- H8-H9: `molecular-dynamics`
- H10/E6: `all-analysis`

- task/library/count: `scope-molecular-nomination`
- target biology: `research-target-biology`
- reproducible biology and literature evidence: `search-biomedical-evidence`
- ligands, action direction, potency, and clinical safety: `assess-target-pharmacology`
- PDB/structure: `rank-protein-structures`
- computational route and applicability: `assess-computational-pharmacology`
- native receptor/ligand coordinates: `prepare-native-protein-ligand`
- docking decision: `qualify-binding-pocket`
- compound annotations: `enrich-compound-evidence`
- observed/predicted/unknown toxicity: `triage-compound-toxicity`
- ranking and mechanisms: `nominate-lipid-modulators`
- final explanation and experiments: `write-mechanism-validation-report`

Before any DiffDynamic call, read the structure-preparation manifest and select only
`diffdynamic_input.protein_pdb` plus `diffdynamic_input.ligand_sdf`. Verify the resolved
suffixes are exactly `.pdb` and `.sdf`, the receptor is coordinate-cleaned, and compatibility
is true. Never pass source/complex CIF/mmCIF, ligand PDB/MOL2, or MAE/MAEGZ. Report the hard
gate and return to E2b instead of guessing or converting when this contract is not met.

After every stage report the stage ID, status, tools called, inputs, observed record count,
warnings, relative artifact paths, and next stage. Continue automatically unless a hard
gate fails or compute authorization is required.

For an authorized end-to-end task, make one background `funnel_autopilot` call and
then create the adaptive `time-scheduler` tick. On each tick use `funnel_autopilot_status`,
call `funnel_report_update` after stage transitions, and never run stages conversationally
in parallel.
If preflight returns `gated_preflight`, stop before compute and relay its exact blockers.
Do not repair a missing adapter by improvising Python/Bash inside the task directory.

When speaking to the user, say 「任务」 not 「战役」 (internal `CAMPAIGN` /
`campaign_memory_*` / `funnel-campaign-memory` IDs stay unchanged).

When the human supplies only a final molecule count, call `funnel_autopilot` with
`profile=full`. Use `profile=test` only after an explicit test/smoke request. Never
infer the test profile merely because the requested final count is small.
