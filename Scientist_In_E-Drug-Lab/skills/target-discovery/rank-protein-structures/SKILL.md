---
name: rank-protein-structures
description: Use after target biology research to search and rank experimental protein structures by identity, species, construct, coverage, mutation, assembly, ligand state, method, and resolution before pocket selection.
---

# Rank Protein Structures

Call `structure_search_rank` with the resolved gene or UniProt accession.

Use RCSB Search API for identifiers and RCSB Data API for metadata. Search output alone
is insufficient because it does not establish construct quality or ligand context.

Ranking priority:

1. correct human target identity and relevant domain coverage
2. experimental structure before a computed model
3. relevant bound ligand, substrate, cofactor, or known functional state
4. fewer disruptive mutations or construct artifacts
5. suitable biological assembly and better experimental resolution

Write `structure_candidates.csv` and `selected_structure.json`. Then call
`assess-computational-pharmacology` with the biology, pharmacology, structure, and known-ligand
evidence to choose a defensible route. For a selected ligand-bound entry on the structure route,
call `structure_prepare_native` through `prepare-native-protein-ligand` before pocket
qualification. Metadata ranking alone is not a downloaded or docking-ready structure.

If no experimental candidate is qualified, record that result. A predicted structure may
support a cautious hypothesis but must not be presented as equivalent to a ligand-supported
experimental pocket.
