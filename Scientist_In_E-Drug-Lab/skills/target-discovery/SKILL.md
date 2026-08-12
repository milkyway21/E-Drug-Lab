---
name: target-discovery
description: Builds an auditable target, biology, structure, ligand, and pocket dossier. Use before docking or when a task asks which target or protein structure to use.
---

# Target Discovery

Use this main skill before H0 whenever the task starts from a biological target or a
compound-nomination question. It owns evidence envelope E0-E3 and decides whether a
structure-based branch is scientifically applicable.

## Child skills

`scope-molecular-nomination`, `research-target-biology`, `search-biomedical-evidence`,
`assess-target-pharmacology`, `rank-protein-structures`,
`assess-computational-pharmacology`, `prepare-native-protein-ligand`, and
`qualify-binding-pocket`.

## Order

1. Define disease, target, desired phenotype, compound-library scope, and final count.
2. Search biology, literature, pharmacology, genetics, expression, and pathway evidence.
3. Rank PDB/UniProt structures and record resolution, construct, ligands, and limitations.
4. Decide the computational route; do not force docking when evidence is insufficient.
5. Prepare a coordinate-cleaned receptor and same-frame native ligand when docking applies.
6. Qualify the pocket and emit `docking_recommendation=dock` or `not_applicable`.

## Gate

Do not begin DiffDynamic or Glide until the structure-preparation manifest passes. Unknown
evidence remains `unknown`; computational predictions are not experimental confirmation.
