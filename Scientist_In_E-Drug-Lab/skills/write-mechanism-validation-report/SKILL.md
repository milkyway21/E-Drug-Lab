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

Validate official-library identity, score decomposition, citations, toxicity rationale,
mechanism direction, uncertainty, and reproducibility files before declaring submission-ready.
