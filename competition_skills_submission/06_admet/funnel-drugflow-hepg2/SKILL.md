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
