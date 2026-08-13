---
name: e-drug-lab-scientist
description: Use to apply reproducible scientist behavior to a task.
---

# E-Drug Lab Scientist

Apply conservative scientific operator behavior to any discovery task. Separate plans,
submitted jobs, predictions, validated computational results, and experimental evidence.

## When to Use

Use this skill as the behavior policy whenever an agent plans, runs, resumes, reviews, or
reports a discovery campaign. It is target-independent and does not replace the operation
skill for the current stage.

## Prerequisites

Obtain the task scope, current state, allowed tools, resource boundary, and artifact root.
Read existing state and validators before issuing a command. If the task was already
started, prefer reuse and recovery over recomputation.

## How to Run

Use the project's registered tools when present, or execute the matching child skill's
standalone command through a terminal. Before every execution print or record the resolved
binary, version, exact argv, working directory, input hashes, resource assignment, and
expected outputs.

## Quick Reference

- `planned`: parameters and targets exist; no computation is claimed.
- `submitted`: a scheduler or JobDJ accepted the job; outputs are not yet validated.
- `completed`: the process ended; scientific outputs still require validation.
- `validated`: required artifacts, counts, properties, and lineage pass the stage gate.
- `blocked`: an input, tool, license, resource, or scientific prerequisite is missing.

## Procedure

1. Restate the scientific objective and success criteria in task state.
2. Inspect current artifacts and decide `reuse`, `resume`, `rerun`, or `block` with reasons.
3. Run a capability and resource preflight before expensive work.
4. Execute the smallest validating probe before scaling a fragile backend.
5. Monitor by exact job or process ID and preserve every attempt.
6. Validate outputs and write a concise stage report with interpretation and limitations.
7. Advance only when the next skill's input contract is satisfied.

## Concrete Operation Procedure

For a fresh task, complete E0-E3 and then call the deterministic worker:

```bash
masld-agent evidence target --gene "$TARGET_ID" --disease "$DISEASE" --online \
  --output "$CAMPAIGN_ROOT/01_target/target_evidence.json"
masld-agent evidence structures --gene "$TARGET_ID" --limit 25 \
  > "$CAMPAIGN_ROOT/01_target/structure_candidates.json"
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full --target-id "$TARGET_ID"
masld-agent funnel autopilot --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" --execute --confirm --background
masld-agent funnel autopilot-status --target-id "$TARGET_ID"
```

Before H1 verify that the preparation manifest points to clean PDB plus native SDF. After
each validated stage report observed counts and relative artifacts; never use chat text or
a submitted job as completion evidence.

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

Use the user-facing term "task" rather than the legacy term "campaign" in Chinese output;
internal `CAMPAIGN`, `campaign_memory_*`, and `funnel-campaign-memory` IDs stay unchanged.

Human-readable task artifacts default to Chinese. Pass `language=en` in a tool call or
`--language en` on a CLI command when an English report is required; machine-readable JSON
keys and registry IDs remain stable.

When the human supplies only a final molecule count, call `funnel_autopilot` with
`profile=full`. Use `profile=test` only after an explicit test/smoke request. Never
infer the test profile merely because the requested final count is small.

## Universal Manifest Invocation

Use this agent skill for any target or disease by passing a manifest that declares
the task, stage, inputs, outputs, resources, validation, reporting, and explicit
argv `command` or ordered `steps`. It must not infer a target or backend.

```bash
bash scripts/run_skill.sh --skill e-drug-lab-scientist --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill e-drug-lab-scientist --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill e-drug-lab-scientist --manifest MANIFEST --status
bash scripts/run_skill.sh --skill e-drug-lab-scientist --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill e-drug-lab-scientist --manifest MANIFEST --resume --execute --confirm
```

Keep the full task record and validated artifacts below `campaign_root`; `full`
remains the funnel planner default and `test` is explicit only.

## Standalone Command-Line Procedure

When the human provides only a target and final count, the reusable non-manifest route is
the following. Resources and intermediate quantities are calculated by the planner:

```bash
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
FINAL_COUNT="${FINAL_COUNT:?requested final molecule count}"
masld-agent funnel plan --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" --profile full
masld-agent funnel autopilot --target-id "$TARGET_ID" --final-count "$FINAL_COUNT" \
  --profile full --execute --confirm --background
while :; do
  masld-agent funnel autopilot-status --target-id "$TARGET_ID" || true
  sleep "${MONITOR_SECONDS:-900}"
done
```

The loop is a terminal supervisor, not model memory. Stop it when status is `completed`
or `failed`; preserve the task root, logs, and cumulative report. If a capability is
unavailable, keep the stage gated and do not substitute a guessed backend.

## Pitfalls

Never invent missing measurements, silently change the target/library, use a test profile
as production, or report predicted efficacy as observed biology. Do not launch a duplicate
job because a status request timed out.

## Verification

For every stage require observed counts, input/output hashes, backend and version, exact
command, resources, job ID, validator outcome, rejected records, interpretation, caveats,
and next gate. Default human-facing prose to Chinese while preserving machine keys.
