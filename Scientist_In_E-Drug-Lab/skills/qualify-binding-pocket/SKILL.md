---
name: qualify-binding-pocket
description: Use after structure ranking to decide whether a binding pocket and structure-based docking are biologically applicable, evidence-supported, and reproducible.
---

# Qualify Binding Pocket

Call `pocket_qualify` before any Glide stage.

A pocket qualifies only when all applicable conditions hold:

- the mechanism is target-based rather than purely phenotypic
- the selected structure has verified target identity and usable coordinates
- a co-crystal ligand, substrate, cofactor, functional residue set, or literature supports the site
- the selected assembly and construct do not invalidate the proposed site

Write `pocket_manifest.json` with `applicable`, `qualified`, evidence basis, rejection
reasons, and `docking_recommendation`. If qualification fails, continue the nomination as
a phenotype or annotation branch and mark docking `not_applicable`; do not invent a grid center.
