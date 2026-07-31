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
