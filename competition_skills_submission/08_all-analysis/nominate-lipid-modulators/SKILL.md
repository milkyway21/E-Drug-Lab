---
name: nominate-lipid-modulators
description: Use to rank official-library compounds for lipid-lowering or related phenotypes with configurable evidence weights, uncertainty penalties, safety prioritization, diversity, and testable mechanism hypotheses.
---

# Nominate Lipid Modulators

Call `nominate_compounds` after E0 inputs are locked. The tool executes E0-E6 and writes a
report after every stage. Do not reproduce the score manually in conversation.

Default score:

- lipid phenotype evidence: 30%
- mechanism and pathway consistency: 20%
- direct activity and assay quality: 15%
- safety: 20%
- structure and developability: 10%
- chemical diversity: 5%
- missing or conflicting evidence penalty: up to 20 points

Docking is conditional evidence. A candidate is not penalized merely because docking is
biologically inapplicable. Invalid identity and non-library provenance cannot enter the final list.

For every nominee, state the ranking basis, toxicity basis, mechanism chain, alternatives,
falsifiers, evidence level, uncertainty, and dual lipid/viability validation readouts.

Required outputs are `nomination_scorecard.csv`, `top10_nomination.csv`,
`mechanism_validation.md`, and `evidence_provenance.json`.
