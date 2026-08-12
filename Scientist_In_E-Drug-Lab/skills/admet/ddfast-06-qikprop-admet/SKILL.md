---
name: ddfast-06-qikprop-admet
description: Run Schrödinger LigPrep and QikProp ADMET with parent-state lineage, strict numeric validation, and deterministic exact-N selection. Use for the funnel H4 ADMET gate; do not use DrugFlow, mock values, or RDKit descriptors as substitutes.
---

# Schrödinger QikProp ADMET

Use this skill for H4. The backend must be the installed Schrödinger QikProp;
do not substitute DrugFlow, a mock, or RDKit descriptors.

## Supported 2023-3 invocation

Probe both commands once and retain the help output in the stage directory:

```bash
"$SCHRODINGER/ligprep" -h
"$SCHRODINGER/qikprop" -h
```

LigPrep accepts structure input through `-isd`/`-imae` and output through
`-osd`/`-omae`. QikProp takes the structure file as its final positional
argument:

```bash
"$SCHRODINGER/ligprep" -isd input.sdf -osd prepared.sdf -epik -WAIT
"$SCHRODINGER/qikprop" -fast -nosim -LOCAL -WAIT -outname qikprop prepared_beststate.sdf
```

Never pass SMILES directly to QikProp. Under 2023-3, `qikprop -inp ...` and a
QikProp `-osd` argument are invalid. If LigPrep creates multiple states, preserve
the parent ID and deterministically select one state per parent before QikProp.

QikProp 2023-3 can reject an otherwise valid SDF when upstream records carry hundreds
of SD data fields. Before QikProp, write a minimal structure SDF that retains only the
title and one lineage field (`parent_id`); keep the full original SDF and a separate
lineage CSV as evidence. This is mandatory preprocessing, not an after-failure patch.

## Data gate

Require one QikProp row per input parent and numeric values for `mol_MW`,
`QPlogS`, `QPPCaco`, `PercentHumanOralAbsorption`, `QPlogHERG`, `#stars`,
`#metab`, `QPlogPo/w`, and `RuleOfFive`. Isolate empty or failed attempts; never
merge them into a valid table.

Apply these fixed core rules without relaxation:

- `RuleOfFive <= 1`
- `QPlogS > -6`
- `QPPCaco > 50`
- `PercentHumanOralAbsorption > 30`
- `QPlogHERG >= -5` (less negative predicts lower hERG blockade risk)
- `#stars < 8`
- `#metab < 10`

Report `mol_MW <= 650` and `QPlogPo/w <= 6` as supplementary rules. Select the
requested exact N only from core-pass molecules, sorting by supplementary fail
count, then a documented deterministic ADMET score, then molecule ID. If fewer
than N pass, stop at the gate rather than loosening thresholds.

Treat a molecule that produces no numeric QikProp row as explicitly incompatible and
record it in the validation report. Do not require failed molecules to appear in the
numeric descriptor table, but require enough valid core-pass rows to select exact N.

Write the full descriptor table, exact-N manifest, exact-N SDF, parent-state map,
command log, and validation report to the manifest-declared stage directory.
Also export a stable-ID table suitable for E5 with `parent_id`, parent InChIKey,
`QPlogHERG`, `#stars`, `#metab`, `QPlogS`, `QPPCaco`, oral absorption, and rule failures.
Label every QikProp field as a prediction; it cannot replace observed cell viability or
curated organ-toxicity evidence.
Run project-owned file-based utilities through their documented CLI. If an
existing utility has hard-coded paths or counts, fix the reusable utility and
add a regression test; do not copy it into a task directory or create a
one-off pipeline. If no validated adapter exists, stop at a capability gate
instead of improvising scientific results.
