---
name: reporting
description: Use when an E-Drug Lab task needs one evidence-linked H0-H10 funnel report with a section per stage, grounded analysis, reused scientific figures, incremental DOCX/PDF export, and relative-path provenance.
---

# Reporting

## Concrete Operation Procedure

After every validated stage append factual interpretation to the same report set:

```bash
masld-agent funnel report-update --manifest "$MANIFEST" --stage "$STAGE" \
  --profile "$PROFILE" \
  --analysis "Observed count, validated outputs, interpretation, limitations, and next gate."
```

Check `AUTOPILOT_REPORT.md`, `.docx`, `.pdf`, stage JSON, and copied figures under the
manifest report directory. Use source-relative paths and hashes; if no valid figure exists,
say so. At finalization verify one section per enabled stage and label predictions as
predictions rather than experimental confirmation.

Use this as the cross-stage reporting umbrella. Compose `funnel-comprehensive-analysis`,
`write-mechanism-validation-report`, `desmond-md-campaign`, `pose-library-screening`, and
`funnel-campaign-memory`; do not replace their validators or duplicate their plot recipes.

## One report

Maintain exactly one incrementally updated report set under the manifest report directory:

- `AUTOPILOT_REPORT.md`
- `AUTOPILOT_REPORT.docx`
- `AUTOPILOT_REPORT.pdf`

Each H0-H10 stage is one chapter in that same report. Existing stage JSON/Markdown files
remain machine-readable evidence and are not replaced by the human report.

After a stage completes:

1. Read the stage JSON, validation evidence, artifact counts, logs, and relevant backend
   outputs.
2. Explain what was actually observed, what it means scientifically, limitations, and why
   the next stage is or is not allowed.
3. Call `funnel_report_update` with the evidence-grounded analysis.
4. Continue only after the stage validator passes or the report explicitly records a gate.

Computational scores are evidence, not experimental confirmation. Never invent counts,
ADMET values, docking scores, MD stability, or mechanism evidence.

## Figures and provenance

Prefer real figures already produced by the current task, including Schrödinger plots,
Glide/Shape summaries, QikProp/ADMET charts, SEA outputs, and Desmond RMSD/contact plates.
Copy them into the report's `figures/<stage>/` directory and record source-relative path and
SHA256. If no valid figure exists, a factual count/progress chart may be generated from
validated counts; otherwise state that no figure was available.

The DOCX and PDF must use the same stage data and figure list. Use relative paths in report
text and provenance tables; never expose an unrelated prior task's path.

Human-readable reports default to Chinese. Set `reporting.language` to `en` in a manifest,
pass `language=en` to a tool, or use `--language en` on a CLI command for English output.
Machine-readable stage keys, artifact names, and validation flags remain unchanged.

## Interface

```bash
masld-agent funnel report-update --manifest MANIFEST --stage H2 --profile full \
  --analysis "Evidence-grounded stage interpretation."
```

At final completion, verify the single report set, all stage sections, figure provenance,
and export status before calling the task submission-ready.

## Universal Manifest Invocation

Use this reporting skill for any target, disease, and multi-stage task. The manifest
declares source artifacts, cumulative report outputs, resources, validation,
reporting location, and an explicit argv `command` or ordered `steps`.

```bash
bash scripts/run_skill.sh --skill reporting --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill reporting --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill reporting --manifest MANIFEST --status
bash scripts/run_skill.sh --skill reporting --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill reporting --manifest MANIFEST --resume --execute --confirm
```

Append one cumulative report under `campaign_root`, use relative figure/source
links, and validate DOCX/PDF plus machine-readable evidence before submission.

## Standalone Command-Line Procedure

The report contract is usable without a manifest. Set the task root explicitly, append
one section after each validated stage, and export the same Markdown source:

```bash
RUN_ROOT="${RUN_ROOT:?current task output root}"
REPORT_DIR="${REPORT_DIR:-$RUN_ROOT/report}"
REPORT_MD="$REPORT_DIR/AUTOPILOT_REPORT.md"
mkdir -p "$REPORT_DIR/figures"
cat >> "$REPORT_MD" <<EOF

## ${STAGE:-H0} — ${STAGE_TITLE:-Stage}

- Status: ${STAGE_STATUS:-unknown}
- Observed outputs: ${OBSERVED_OUTPUTS:-not supplied}
- Interpretation: ${STAGE_ANALYSIS:-not supplied}
- Limitations and next gate: ${NEXT_GATE:-not supplied}
EOF
if command -v pandoc >/dev/null 2>&1; then
  pandoc "$REPORT_MD" -o "$REPORT_DIR/AUTOPILOT_REPORT.docx"
  pandoc "$REPORT_MD" -o "$REPORT_DIR/AUTOPILOT_REPORT.pdf"
fi
sha256sum "$REPORT_MD" "$REPORT_DIR"/AUTOPILOT_REPORT.{docx,pdf} 2>/dev/null \
  > "$REPORT_DIR/report.sha256" || true
```

Replace every placeholder with values from validated stage outputs, copy only current-task
figures into `figures/<stage>/`, and reference them relatively. Markdown, DOCX, PDF,
tables, and figure hashes must describe the same data.
