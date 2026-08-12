---
name: triage-compound-toxicity
description: Use during candidate nomination to separate observed cytotoxicity and organ-toxicity evidence from QikProp or structure-based predictions, prioritize safer compounds, and preserve unknowns.
---

# Triage Compound Toxicity

Call `toxicity_triage` after compound evidence enrichment. For full computational runs,
reuse the existing QikProp skill and import its outputs rather than substituting another ADMET model.

Evidence hierarchy:

1. matched experimental cell viability at relevant concentration and exposure
2. curated human organ-toxicity annotations such as DILI or cardiotoxicity references
3. assay-based safety pharmacology
4. QikProp and structural-alert predictions
5. no data, which must be labeled unknown

Do not infer causality from spontaneous adverse-event counts. A structural alert is a
prediction, not observed toxicity. A database miss is not evidence of safety.

Write `toxicity_evidence.csv` with observed and predicted counts, endpoint, applicability,
rationale, and safety score. Apparent lipid reduction with reduced viability is a false-positive risk.
