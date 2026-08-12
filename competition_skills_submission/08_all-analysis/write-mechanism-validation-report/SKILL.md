---
name: write-mechanism-validation-report
description: Use after compound ranking or H10 analysis to write an auditable nomination report with causal mechanisms, alternatives, falsifiers, dual-readout experiments, citations, uncertainty, and reproducibility artifacts.
---

# Write Mechanism Validation Report

Call `build_validation_report` after nomination and after any later H10 evidence update.

For each candidate, write:

1. compound intervention and direct action
2. target or pathway and expected direction
3. expected lipid phenotype
4. evidence references and evidence level
5. competing mechanism and a result that would falsify the preferred mechanism
6. concentration-response HepG2-FFA lipid and matched viability readouts
7. mechanism-specific target engagement, expression, phosphorylation, or flux readouts

Discuss SREBP-1c/ACC/FASN/SCD1, PPARα/AMPK/CPT1, uptake or efflux, and autophagy only
when candidate evidence supports the branch. Do not convert computational ranking into an
experimental claim.

Human-readable reports default to Chinese. Pass `language=en` to the validation-report tool
or `--language en` to the CLI for English output; preserve stable molecule IDs, CSV columns,
JSON keys, citations, and relative paths in either language.

Validate official-library identity, score decomposition, citations, toxicity rationale,
mechanism direction, uncertainty, and reproducibility files before declaring submission-ready.

When called inside H10/E6, provide the evidence-grounded mechanism text to `reporting` so it
becomes part of the H10 section in the single cumulative DOCX/PDF report.

## Universal Manifest Invocation

Use this skill with any target, disease, and candidate set by declaring evidence
inputs, report outputs, resources, validation, reporting location, and an explicit
argv `command` or ordered `steps`. Mechanism claims must remain evidence-linked.

```bash
bash scripts/run_skill.sh --skill write-mechanism-validation-report --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill write-mechanism-validation-report --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill write-mechanism-validation-report --manifest MANIFEST --status
bash scripts/run_skill.sh --skill write-mechanism-validation-report --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill write-mechanism-validation-report --manifest MANIFEST --resume --execute --confirm
```

Write one cumulative, relative-path report and retain falsifiers, uncertainty,
validation readouts, and reproducibility artifacts.

## Concrete Operation Procedure

Build the report after nomination or H10 updates, then validate the submission directory:

```bash
masld-agent hepg2-plan --run-dir "$CAMPAIGN_ROOT"
masld-agent validate-submission --run-dir "$CAMPAIGN_ROOT"
```

Call the registered `build_validation_report` tool with `run_dir` and use its returned
report path. For each
candidate include intervention, target/pathway direction, expected lipid phenotype,
evidence IDs, competing mechanism, falsifier, concentration-response lipid readout,
matched viability readout, target-engagement readout, uncertainty, and limitations. Keep
the output inside the cumulative report; do not create a disconnected per-stage report.

## Standalone Command-Line Procedure

Create the report from an explicit task root when no manifest or agent tool is available:

```bash
RUN_ROOT="${RUN_ROOT:?current task output root}"
REPORT_MD="${REPORT_MD:-$RUN_ROOT/report/AUTOPILOT_REPORT.md}"
mkdir -p "$(dirname "$REPORT_MD")"
printf '\n## Mechanism Validation\n\n' >> "$REPORT_MD"
printf '%s\n' '- Candidate mechanism, evidence IDs, expected phenotype, falsifier, matched lipid/viability readouts, uncertainty, and limitations must be written from validated inputs.' >> "$REPORT_MD"
if command -v pandoc >/dev/null 2>&1; then
  pandoc "$REPORT_MD" -o "${REPORT_MD%.md}.docx"
  pandoc "$REPORT_MD" -o "${REPORT_MD%.md}.pdf"
fi
```

Replace the placeholder paragraph with evidence-backed rows from the nomination,
pharmacology, toxicity, docking, and MD tables. Keep observed results, predictions,
unknowns, alternative mechanisms, and falsifiers as separate fields. Do not turn a
plausible mechanism into a causal claim, and do not create a second per-stage report.
