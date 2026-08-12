---
name: all-analysis
description: Curates evidence, mechanisms, final rankings, and the complete cumulative report. Use for H10, final nomination, or submission-ready analysis.
---

# All Analysis

This main skill turns validated stage outputs into an auditable scientific conclusion. It
does not create new scores or claim experimental proof.

## Child skills

- `funnel-comprehensive-analysis` for H10 cross-stage curation
- `nominate-lipid-modulators` for efficacy/toxicity/mechanism ranking
- `write-mechanism-validation-report` for testable mechanism and experiment proposals

## Deliverables

1. Reconcile molecule, parent, pose, ADMET, MMGBSA, and MD lineage.
2. Explain ranking evidence, uncertainty, exclusions, and limitations.
3. Append one H10/E6 section to the existing cumulative `reporting` document.
4. Verify Markdown, DOCX, PDF, figures, relative paths, and machine-readable evidence.

Final candidates are computational nominations, not confirmed drug activity.

Human-readable nomination and validation reports default to Chinese. Select English with
`language=en` in a tool call or `--language en` on the CLI; machine-readable evidence and
CSV field names remain stable.

## Universal Manifest Invocation

This analysis skill accepts any target, disease, library, and upstream result set.
Declare evidence inputs, candidate and report outputs, resources, validation rules,
reporting location, and an explicit argv `command` or ordered `steps`; do not infer
candidate identity, mechanism, or experimental efficacy.

```bash
bash scripts/run_skill.sh --skill all-analysis --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill all-analysis --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill all-analysis --manifest MANIFEST --status
```

After checking provenance, uncertainty, dual-readout evidence, and figure paths:

```bash
bash scripts/run_skill.sh --skill all-analysis --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill all-analysis --manifest MANIFEST --resume --execute --confirm
```

Write the consolidated report and machine-readable evidence below `campaign_root`,
retain unresolved claims, and keep relative references suitable for export.

## Concrete Operation Procedure

Run final analysis only after every enabled upstream stage validates:

```bash
masld-agent funnel status --manifest "$MANIFEST"
masld-agent funnel validate --manifest "$MANIFEST" --stage H10
masld-agent evidence nominate --library "$OFFICIAL_LIBRARY" \
  --output "$CAMPAIGN_ROOT/evidence" --final-count "$FINAL_COUNT" \
  --disease "$DISEASE" --target-gene "$TARGET_ID" --online
masld-agent funnel report-update --manifest "$MANIFEST" --stage H10 \
  --profile full --analysis "Evidence-grounded final ranking and limitations."
```

Join by stable molecule/library/parent IDs, then verify candidate count, lineage, ADMET,
docking, MMGBSA, MD, figures, and relative paths. A missing upstream row remains missing;
do not create a final score or mechanism from a filename.

## Standalone Command-Line Procedure

Without a manifest, treat the stage tables and report directory as explicit arguments and
perform a deterministic file-level audit before writing conclusions:

```bash
RUN_ROOT="${RUN_ROOT:?current task output root}"
REPORT_DIR="${REPORT_DIR:-$RUN_ROOT/report}"
mkdir -p "$REPORT_DIR"
find "$RUN_ROOT" -type f -print0 | sort -z | xargs -0 sha256sum > "$REPORT_DIR/artifact.sha256"
jq -s 'map(select(.status == "valid" or .status == "completed"))' \
  "$RUN_ROOT"/stages/*.json > "$REPORT_DIR/validated_stages.json" 2>/dev/null || true
```

Join tables on declared IDs, not row order. For each final molecule record the exact
generation parent, docking pose, feature or library hit, ADMET row, MMGBSA row, MD
validation class, evidence source IDs, and missing-data flags. Write one Markdown
section per stage plus a final ranking table; export the same Markdown to DOCX/PDF with
the installed converter and keep figure paths relative to `REPORT_DIR`. A computational
rank is a nomination, never experimental efficacy.
