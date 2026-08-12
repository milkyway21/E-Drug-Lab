---
name: reporting
description: Use when an E-Drug Lab task needs one evidence-linked H0-H10 funnel report with a section per stage, grounded analysis, reused scientific figures, incremental DOCX/PDF export, and relative-path provenance.
---

# Reporting

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

## Interface

```bash
masld-agent funnel report-update --manifest MANIFEST --stage H2 --profile full \
  --analysis "Evidence-grounded stage interpretation."
```

At final completion, verify the single report set, all stage sections, figure provenance,
and export status before calling the task submission-ready.
