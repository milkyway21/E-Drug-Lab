---
name: qualify-binding-pocket
description: Use after structure ranking to decide whether a binding pocket and structure-based docking are biologically applicable, evidence-supported, and reproducible.
---

# Qualify Binding Pocket

Call `pocket_qualify` before any Glide stage. For a ligand-supported experimental pocket,
first require `prepare-native-protein-ligand` to produce a valid
`structure_preparation_manifest.json`.

A pocket qualifies only when all applicable conditions hold:

- the mechanism is target-based rather than purely phenotypic
- the selected structure has verified target identity and usable coordinates
- a co-crystal ligand, substrate, cofactor, functional residue set, or literature supports the site
- the selected assembly and construct do not invalidate the proposed site
- the native ligand and cleaned receptor remain in one coordinate frame, with no ligand
  translation, rotation, or minimization during extraction

Write `pocket_manifest.json` with `applicable`, `qualified`, evidence basis, rejection
reasons, and `docking_recommendation`. If qualification fails, continue the nomination as
a phenotype or annotation branch and mark docking `not_applicable`; do not invent a grid center.
