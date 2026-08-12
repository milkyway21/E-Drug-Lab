---
name: funnel-drugflow-hepg2
description: Compatibility route for the funnel H4 ADMET stage. Use when an older task names DrugFlow or HepG2; under current test and full profiles, route execution to Schrödinger LigPrep/QikProp and preserve the true backend identity.
---

# H4 ADMET Compatibility Route

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
