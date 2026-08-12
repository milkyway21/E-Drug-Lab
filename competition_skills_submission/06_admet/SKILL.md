---
name: admet
description: Applies evidence enrichment, toxicity triage, and validated ADMET prediction. Use for H4 ADMET or compound nomination safety review.
---

# ADMET

This main skill owns H4 and the evidence-side E4/E5 review. It does not substitute a
Schrodinger or DrugFlow result with an LLM estimate.

## Child skills

- `funnel-drugflow-hepg2` for the configured ADMET route
- `ddfast-06-qikprop-admet` for Schrödinger QikProp compatibility
- `enrich-compound-evidence` for compound annotations and literature evidence
- `triage-compound-toxicity` for observed/predicted/unknown toxicity tiers

## Gate

Record backend, version, input count, observed output count, missing fields, filters, and
artifact validation. Unknown toxicity is not low toxicity. Only validated survivors proceed
to the next docking refinement stage.
