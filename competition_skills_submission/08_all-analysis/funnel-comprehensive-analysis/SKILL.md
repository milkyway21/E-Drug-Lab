---
name: funnel-comprehensive-analysis
description: Curate H10 docking, ADMET, and hard-validated MD evidence into an auditable final ranking and human report. Use only after enabled upstream stages pass validation; do not present computational nominations as experimental confirmation.
---

# H10 Comprehensive Analysis

Join on molecule ID, library ID, or parent InChIKey; never raw SMILES alone when a
stable ID exists. Preserve backend identity, missing values, source pose, CMS,
trajectory, SEA path, and validation class. Corrected-pose validated MD evidence takes
precedence over a favorable numeric docking score.

Write a machine table and human report. State that computational nomination is not
experimental confirmation. `funnel validate --stage H10` must verify both outputs and
their candidate counts.

Then hand the joined candidates to E4-E6. Preserve official library ID, parent InChIKey,
assay context, evidence level, observed versus predicted toxicity, score decomposition,
uncertainty penalty, target/pathway direction, alternatives, falsifiers, and validation
readouts. Do not allow a favorable docking or MD value to erase contrary biological or
toxicity evidence.

Use the `reporting` umbrella to append this H10 analysis to the single cumulative report and
reuse validated upstream figures. Do not emit a separate per-stage DOCX/PDF.

## Universal Manifest Invocation

Use this skill with any upstream funnel by declaring evidence inputs, analysis and
report outputs, resources, validation, reporting location, and an explicit argv
`command` or ordered `steps`. Do not infer a target or candidate set.

```bash
bash scripts/run_skill.sh --skill funnel-comprehensive-analysis --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-comprehensive-analysis --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-comprehensive-analysis --manifest MANIFEST --status
bash scripts/run_skill.sh --skill funnel-comprehensive-analysis --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-comprehensive-analysis --manifest MANIFEST --resume --execute --confirm
```

Keep one cumulative report, relative figure references, and unresolved evidence
visible under `campaign_root`.

## Concrete Operation Procedure

Validate every enabled stage and then run the H10 join from declared current-task tables:

```bash
masld-agent funnel status --manifest "$MANIFEST"
masld-agent funnel validate --manifest "$MANIFEST" --stage H8
masld-agent funnel validate --manifest "$MANIFEST" --stage H9
masld-agent funnel validate --manifest "$MANIFEST" --stage H10
masld-agent funnel report-update --manifest "$MANIFEST" --stage H10 \
  --profile full --analysis "Joined validated evidence; computational nomination only."
```

Before accepting a candidate, require stable ID joins for parent/pose/ADMET/MMGBSA/MD,
validated trajectory class, toxicity evidence class, and source-relative artifacts. Export
one machine table and one cumulative report section; never emit an unsupported score.

## Standalone Command-Line Procedure

Use the same analysis contract without a manifest by naming each validated input table:

```bash
RUN_ROOT="${RUN_ROOT:?current task output root}"
REPORT_DIR="${REPORT_DIR:-$RUN_ROOT/report}"
mkdir -p "$REPORT_DIR"
printf '%s\n' "stage,artifact,sha256" > "$REPORT_DIR/artifact_index.csv"
find "$RUN_ROOT" -type f \( -name '*.json' -o -name '*.csv' -o -name '*.sdf' -o -name '*.mae*' \) -print0 |
  while IFS= read -r -d '' file; do
    printf '%s,%s,%s\n' "${file#"$RUN_ROOT"/}" "$(basename "$file")" "$(sha256sum "$file" | cut -d' ' -f1)"
  done >> "$REPORT_DIR/artifact_index.csv"
```

Use `jq`, `csvkit`, pandas, or R to inner-join only on stable parent/molecule/pose IDs;
emit unmatched IDs in a separate exclusions table. Read each stage's validator output,
then write observed counts, interpretation, uncertainty, and next-gate rationale into
one cumulative Markdown report. Convert that report and its verified figures to DOCX/PDF
with a local Markdown converter, using relative paths and retaining the machine tables.
