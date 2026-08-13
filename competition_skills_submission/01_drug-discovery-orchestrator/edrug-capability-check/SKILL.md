---
name: "edrug-capability-check"
description: "Use to verify tools, services, resources, and licenses."
---

# E-Drug Capability Check

Inventory what the current machine and agent can actually execute. This skill diagnoses
capability; it never substitutes for a scientific stage validator.

## When to Use

Use before a new task, after changing models/providers, after software upgrades, or when a
stage fails because a tool, service, license, or resource may be unavailable.

## Prerequisites

Know the requested stages and required backends. Do not require optional tools unrelated
to the task. Avoid printing credential values; report only presence and source class.

## How to Run

Check registry first, then environment variables, `PATH`, executable help/version, service
health, license checkout, GPU visibility, CPU, RAM, disk, network, and output writability.
For a non-project agent, run the same checks directly with the terminal.

## Quick Reference

Return one row per capability with `ready`, `degraded`, `blocked`, or `not_applicable`,
plus resolved executable/service, version, license, resource need, probe result, and fix.

## Procedure

1. Map enabled stages to required and optional capabilities.
2. Resolve each binary or service without hard-coded installation paths.
3. Run read-only help/health probes and a license check where supported.
4. Inventory approved GPU IDs, CPU cores, RAM, free disk, and expected wall time.
5. Validate task directory access and network endpoints.
6. Write a capability matrix and block only affected stages.

## Concrete Operation Procedure

Run the capability harness before a new task or backend change:

```bash
masld-agent platform-health
masld-agent platform-catalog --system dd
masld-agent platform-catalog --system ed
masld-agent platform-catalog --system sz
PROJECT_ROOT="${PROJECT_ROOT:?checkout root containing scripts/}"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$PROJECT_ROOT/scripts/capability_harness.py" \
  --api-base "${EDRUG_API_BASE:-http://127.0.0.1:8001}" \
  --cases "$PROJECT_ROOT/scripts/capability_cases/core.yaml" "$PROJECT_ROOT/scripts/capability_cases/tool_matrix_templates.yaml"
```

Save the report and classify each capability PASS/PARTIAL/GATE/FAIL. Resolve only the
registered executable IDs named by a failed stage. A GATE means missing path, license,
input, GPU, or confirmation; it is not permission to invent a result.

Verify the Web API, agent plugin, and UI bus against their declared contracts.

## Outputs and evaluation

Write `memory/TOOL_CAPABILITY.md` and `reports/capability_harness_<timestamp>.md`; optionally
append a non-destructive entry to `memory/GLOBAL_HISTORY.md`. Classify each case as
`PASS`, `PARTIAL`, `GATE`, or `FAIL`.

- A Desmond `stub` or false `completed` response is **FAIL**.
- `unavailable`, `gated`, or not-yet-run templates are **GATE**.
- `dry_prep` completed with `engine=schrodinger_desmond` is **PASS** for preparation only,
  not production execution.
- A `GATE` means that a path, license, input, GPU, or confirmation is missing; list the
  human action required and never fabricate a scientific result.

## Harness coverage

| Covered | Not covered |
|---|---|
| HTTP `POST/GET /api/v1/affinity/md` dry-prep | A real Hermes chat or LLM session |
| Python `schrodinger_md_submit` and Hermes handler dry-prep | Production `funnel-desmond-*` or `dd-md-desmond` execution |
| Hermes `register()` tool registration | Production smoke/short runs requiring confirmation and GPU/license |
| Skill files plus conda/`SCHRODINGER` probes | `conda activate` or `conda create` for Desmond |

## Environment: Desmond versus conda

- Desmond / `schrodinger_md_*`: resolve the registered `sz.bin.run` and
  `sz.bin.multisim` entries first. Do not create a conda environment for MD or hard-code
  an installation path.
- conda **`diffdynamic`** is for DiffDynamic only and is unrelated to Desmond multisim.

## Related interfaces

- Agent tools: `schrodinger_md_submit`, `schrodinger_md_status` in `hermes_plugin`
- Playbook: `memory/MAIN_PLAYBOOK.md`, capability-check section
- Skills: `funnel-desmond-short-md`, `funnel-desmond-long-md`, `dd-md-desmond`, `funnel-campaign-memory`

## Universal Manifest Invocation

Use this preflight skill for any target and local environment. Declare capability
inputs, probe/status outputs, resource policy, validation, reporting, and an
explicit argv `command` or ordered `steps`; no machine or target is assumed.

```bash
bash scripts/run_skill.sh --skill edrug-capability-check --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill edrug-capability-check --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill edrug-capability-check --manifest MANIFEST --status
bash scripts/run_skill.sh --skill edrug-capability-check --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill edrug-capability-check --manifest MANIFEST --resume --execute --confirm
```

Treat unavailable tools as a capability gate, preserve probe logs, and do not
report planned resources as completed computation.

## Standalone Command-Line Procedure

Run the capability harness directly from the project root, with no manifest. Set the
project root and API endpoint explicitly so the command is portable:

```bash
PROJECT_ROOT="${PROJECT_ROOT:?checkout root containing scripts/}"
PYTHON="${PYTHON:-python3}"
API_BASE="${EDRUG_API_BASE:-http://127.0.0.1:8001}"
"$PYTHON" "$PROJECT_ROOT/scripts/capability_harness.py" \
  --api-base "$API_BASE" --report-dir "${REPORT_DIR:-$PROJECT_ROOT/reports}"
```

Record the selected case file, backend versions, environment probes, exact API responses,
and `PASS/PARTIAL/GATE/FAIL` result. A disabled or unavailable case is a capability gate,
not evidence that a scientific stage completed. Re-run only the failed or gated case
after the external capability changes.

## Pitfalls

Do not expose secrets, create replacement environments automatically, assume a visible GPU
is free, or mark a backend ready because its directory exists.

## Verification

Require successful executable help or API health, version capture, license status where
applicable, writable output, sufficient free resources, and no secret values in the report.
