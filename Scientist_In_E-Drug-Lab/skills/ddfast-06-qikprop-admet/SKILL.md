---
name: ddfast-06-qikprop-admet
description: Schrödinger 2023-3 LigPrep/QikProp ADMET with parent lineage, strict data validation, and deterministic exact-N selection.
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

Write the full descriptor table, exact-N manifest, exact-N SDF, parent-state map,
command log, and validation report to the manifest-declared stage directory.
Run existing file-based Python utilities with their documented CLI; if a useful
script has hard-coded paths, copy it into the current stage and adapt only path
constants and requested N rather than creating a new pipeline.
