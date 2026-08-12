---
name: drug-discovery-orchestrator
description: Orchestrates the evidence-gated H0-H10 drug-discovery workflow. Use when a task needs target setup, generation, screening, ADMET, MD, monitoring, and one final report.
---

# Drug Discovery Orchestrator

This is the default entrypoint for an end-to-end E-Drug Lab task. Load this main skill
first, then load only the child skill required for the current stage.

## Child skills

- `e-drug-lab-scientist`: scientist behavior and evidence rules
- `funnel-orchestrator`: deterministic H0-H10 planning and execution
- `scientist-in-e-drug-lab`: compatibility entrypoint
- `funnel-campaign-memory`: persistent task state
- `time-scheduler`: adaptive wake-ups and local recovery
- `reporting`: one cumulative Markdown/DOCX/PDF report
- `edrug-capability-check`: platform and license gates

## Routing

1. Read the task memory, manifest, and current status.
2. For a new target, run `target-discovery` E0-E3 before H0.
3. Route H1 to `dd-generation`, H2/H5-H7 to `virtual-docking`, H3 to
   `featurehit-finding`, H4 to `admet`, H8-H9 to `molecular-dynamics`, and H10 to
   `all-analysis`.
4. After every validated stage, update `reporting` and flush `funnel-campaign-memory`.
5. For a background task, use `time-scheduler` and never launch a duplicate worker.

## Gates

- Use the project autopilot for count planning, resources, resume, and artifact reuse.
- Stop at the first failed or gated stage; report the exact blocker and path.
- Never turn planned counts into claimed results or invent scientific evidence.
- Keep all outputs under the resolved task root and use relative report provenance.

## Handoff

Every stage handoff includes stage ID, status, tools, inputs, observed count, warnings,
validated artifact paths, analysis, and the next allowed stage.
