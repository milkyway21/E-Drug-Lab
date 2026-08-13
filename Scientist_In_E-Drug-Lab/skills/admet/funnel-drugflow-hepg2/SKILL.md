---
name: funnel-drugflow-hepg2
description: Use to resume legacy-named H4 ADMET stages.
---

# H4 ADMET Compatibility Route

Preserve historical stage names while executing only the explicitly selected real ADMET backend
and reporting that backend's actual semantics.

## When to Use

Use only when an existing task names this compatibility route; new workflows select the real
backend skill directly.

## Prerequisites

- Existing manifest with frozen H3 input, backend identity, lineage, outputs, and validators.
- Installed and licensed backend or a validated project-owned adapter.

## How to Run

Validate the legacy manifest and delegate to the current backend. For the QikProp route, use the
native LigPrep/QikProp command sequence documented here and in its child skill.

## Quick Reference

| Legacy text | Actual handling |
| --- | --- |
| DrugFlow stage name | Record the real selected backend |
| HepG2 label | Never fabricate a cell assay |
| QikProp route | Label `schrodinger_qikprop` prediction |

## Procedure

1. Read and validate the existing backend declaration.
2. Resolve the real executable/adapter and record its version.
3. Execute the backend's current general skill and preserve all failures.
4. Report predictions and observations under separate names.

This skill name is retained for compatibility. It does not authorize DrugFlow,
mock HepG2 values, or backend substitution.

For the current test and full workflow profiles, invoke
`ddfast-06-qikprop-admet` and run the installed Schrödinger LigPrep/QikProp
backend. Record the backend as `schrodinger_qikprop`, including product version,
commands, input structures, and output tables.

Do not label QikProp predictions as experimental HepG2 viability. If a future
manifest explicitly selects another validated backend, preserve that backend's
real name and semantics and require a matching project-owned adapter. Otherwise
stop at the capability gate.

Completion requires parent-state lineage, complete numeric rows, frozen filters,
an exact-N selection manifest when requested, and a validation report. Route all
QikProp command and filtering details to `ddfast-06-qikprop-admet` rather than
duplicating them here.

## Universal Manifest Invocation

Use this compatibility skill only when the manifest explicitly names the selected
ADMET backend, input library, lineage fields, outputs, resources, validation, and
reporting location. It is target-neutral and never invents a fallback backend.

```bash
bash scripts/run_skill.sh --skill funnel-drugflow-hepg2 --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-drugflow-hepg2 --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-drugflow-hepg2 --manifest MANIFEST --status
bash scripts/run_skill.sh --skill funnel-drugflow-hepg2 --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-drugflow-hepg2 --manifest MANIFEST --resume --execute --confirm
```

Preview the external command, keep all artifacts under `campaign_root`, and stop
if parent-state, numeric, or exact-N validation is incomplete.

## Concrete Operation Procedure

This compatibility name routes to the current registered QikProp backend:

```bash
masld-agent platform-catalog --id sz.qikprop --json
masld-agent platform-resolve --id sz.bin.ligprep
masld-agent platform-resolve --id sz.bin.qikprop
masld-agent funnel validate --manifest "$MANIFEST" --stage H3
```

Then execute the exact commands in `ddfast-06-qikprop-admet` and record
`backend=schrodinger_qikprop`. If a task explicitly selects another validated backend,
resolve its registry entry and preserve its real name; if no adapter exists, stop at a
capability gate. Never fabricate HepG2 values or relabel QikProp predictions as cell data.

## Standalone Command-Line Procedure

This compatibility name does not imply a DrugFlow executable. For the current validated
route, use the native QikProp commands in `ddfast-06-qikprop-admet`:

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
OUT="$(realpath -m outputs/04_admet)"
mkdir -p "$OUT"
"${LIGPREP:-$SCHRODINGER/ligprep}" -isd "$H3_SDF" -osd "$OUT/prepared.sdf" -epik -WAIT
"${QIKPROP:-$SCHRODINGER/qikprop}" -fast -nosim -LOCAL -WAIT \
  -outname "$OUT/qikprop" "$OUT/prepared.sdf"
```

Label the backend `schrodinger_qikprop`, preserve failed/unknown rows, and route any
actual experimental HepG2 request to a validated cell assay workflow rather than making
predictions look like observations.

## Pitfalls

- A compatibility name is not authorization to call an unavailable external service.
- Do not label QikProp properties as HepG2 cytotoxicity or viability.
- Do not hide a backend substitution behind the historical stage name.

## Verification

Require explicit real backend identity/version, unchanged frozen input, parent-state lineage,
numeric and failed rows, prediction labels, exact-N validation when requested, and no fabricated
experimental endpoints.
