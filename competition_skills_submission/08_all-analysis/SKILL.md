---
name: all-analysis
description: Use to rank candidates and write the cumulative report.
---

# All Analysis

Consolidate validated computational and biological evidence into a reproducible ranking,
mechanism rationale, experimental plan, and one cumulative report.

## When to Use

Use after the enabled funnel stages finish or when an interim decision requires a joined,
lineage-aware analysis across generation, screening, ADMET, docking, MMGBSA, and MD.

## Prerequisites

- Validated stage outputs with stable molecule, parent, pose, and library identifiers.
- Stage summaries, exclusions, uncertainty, figures, and artifact hashes.
- Reporting root, final candidate count, and output language (`zh` default, `en` optional).

## How to Run

Use the manifest for an orchestrated task. Without a manifest, pass explicit validated tables
and report paths, perform deterministic joins, and keep all missing evidence visible.

## Quick Reference

| Child skill | Purpose | Main output |
| --- | --- | --- |
| `funnel-comprehensive-analysis` | Join cross-stage evidence | Ranked machine table |
| `nominate-lipid-modulators` | Score efficacy, toxicity, mechanism | Nomination scorecard |
| `write-mechanism-validation-report` | Design falsifiable validation | Cumulative report section |

## Procedure

1. Validate all enabled upstream stages and lineage keys.
2. Join evidence without imputing absent rows or silently changing identifiers.
3. Rank with a transparent score decomposition and uncertainty penalties.
4. Write mechanism hypotheses, alternatives, falsifiers, and matched assay readouts.
5. Export one cumulative report plus machine-readable evidence and relative figures.

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

## Pitfalls

- Row order, raw SMILES, or filenames are not reliable cross-stage join keys.
- A favorable docking, MMGBSA, or MD value cannot erase contrary toxicity or biology.
- Computational nomination must not be written as observed efficacy or causal mechanism.

## Verification

Confirm final count, stable lineage, source evidence, exclusions, uncertainty, toxicity class,
mechanism direction, validation readouts, artifact hashes, relative figure paths, and consistent
Markdown/DOCX/PDF content.
