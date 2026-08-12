---
name: ddfast-06-qikprop-admet
description: Run Schrödinger LigPrep and QikProp ADMET with parent-state lineage, strict numeric validation, and deterministic exact-N selection. Use for the funnel H4 ADMET gate; do not use DrugFlow, mock values, or RDKit descriptors as substitutes.
---

# Schrödinger QikProp ADMET

Use this skill for H4. The backend must be the installed Schrödinger QikProp;
do not substitute DrugFlow, a mock, or RDKit descriptors.

## Supported invocation

Probe both commands once and retain the help output in the stage directory:

```bash
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
QIKPROP="$(masld-agent platform-resolve --id sz.bin.qikprop)"
"$LIGPREP" -h
"$QIKPROP" -h
```

LigPrep accepts structure input through `-isd`/`-imae` and output through
`-osd`/`-omae`. QikProp takes the structure file as its final positional
argument:

```bash
"$LIGPREP" -isd input.sdf -osd prepared.sdf -epik -WAIT
"$QIKPROP" -fast -nosim -LOCAL -WAIT -outname qikprop prepared_beststate.sdf
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

## Universal Manifest Invocation

Use this skill with any target or library by declaring all inputs, parent-state
lineage, outputs, resources, validation, reporting, and an explicit argv `command`
or ordered `steps` in the manifest. Do not infer structures, counts, or backend.

```bash
bash scripts/run_skill.sh --skill ddfast-06-qikprop-admet --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill ddfast-06-qikprop-admet --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill ddfast-06-qikprop-admet --manifest MANIFEST --status
bash scripts/run_skill.sh --skill ddfast-06-qikprop-admet --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill ddfast-06-qikprop-admet --manifest MANIFEST --resume --execute --confirm
```

Preview first, keep relative paths under `campaign_root`, and stop when numeric
validation or exact-N selection fails.

## Concrete Operation Procedure

Resolve the two installed binaries through the registry and save their help output:

```bash
mkdir -p "$CAMPAIGN_ROOT/04_admet"
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
QIKPROP="$(masld-agent platform-resolve --id sz.bin.qikprop)"
"$LIGPREP" -h > "$CAMPAIGN_ROOT/04_admet/ligprep.help.txt"
"$QIKPROP" -h > "$CAMPAIGN_ROOT/04_admet/qikprop.help.txt"
```

Run LigPrep on the frozen H3 SDF, retaining `parent_id` in a separate lineage table,
then run QikProp with the prepared SDF as the final positional argument:

```bash
"$LIGPREP" -isd "$H3_SDF" -osd "$CAMPAIGN_ROOT/04_admet/prepared.sdf" \
  -epik -WAIT
"$QIKPROP" -fast -nosim -LOCAL -WAIT \
  -outname "$CAMPAIGN_ROOT/04_admet/qikprop" \
  "$CAMPAIGN_ROOT/04_admet/prepared_beststate.sdf"
```

If upstream records carry excessive SD fields, create a minimal structure SDF with title
and one lineage field before QikProp, while retaining the full SDF as evidence. Parse and
require numeric `mol_MW`, `QPlogS`, `QPPCaco`, oral absorption, `QPlogHERG`, `#stars`,
`#metab`, `QPlogPo/w`, and `RuleOfFive`. Apply this skill's fixed core filters, select
only passing parents, preserve failures, and run `masld-agent funnel validate --manifest
"$MANIFEST" --stage H4`. Never pass SMILES directly, relabel predictions as HepG2 data,
or loosen filters to fill a shortfall.

## Standalone Command-Line Procedure

Run native LigPrep and QikProp without a manifest. Set `SCHRODINGER` or the individual
binary variables; the final QikProp argument is the prepared structure file.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  LIGPREP="${LIGPREP:-$(masld-agent platform-resolve --id sz.bin.ligprep)}"
  QIKPROP="${QIKPROP:-$(masld-agent platform-resolve --id sz.bin.qikprop)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
LIGPREP="${LIGPREP:-$SCHRODINGER/ligprep}"
QIKPROP="${QIKPROP:-$SCHRODINGER/qikprop}"
INPUT_SDF="$(realpath inputs/h3_frozen.sdf)"
OUT="$(realpath -m outputs/04_admet)"
mkdir -p "$OUT"
"$LIGPREP" -isd "$INPUT_SDF" -osd "$OUT/prepared.sdf" -epik -WAIT
"$QIKPROP" -fast -nosim -LOCAL -WAIT -outname "$OUT/qikprop" \
  "$OUT/prepared.sdf"
```

If the installed LigPrep writes a different final-state filename, locate it from the
completed log rather than guessing. Export the QikProp table with the native output
format, join rows to the parent-state table, and apply the fixed filters in this skill.
`qikprop -inp` and a QikProp `-osd` output flag are not part of the tested interface;
probe `-h` before adapting to another release.
