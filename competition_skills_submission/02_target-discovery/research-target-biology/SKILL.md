---
name: research-target-biology
description: Use before structure or pocket selection to orchestrate target identity resolution, reproducible biomedical evidence search, pharmacology assessment, computational-route assessment, and an auditable supporting, opposing, and unresolved target dossier.
---

# Research Target Biology

Call `target_biology_search` first for target-based work, then route through the specialized
skills rather than treating its initial card as complete.

Workflow:

1. Resolve a reviewed human UniProt record and retain UniProt and Ensembl identifiers.
2. Invoke `search-biomedical-evidence` for multi-source biology, tissue, genetics, pathways,
   literature, negative evidence, and a reproducible query manifest.
3. Invoke `assess-target-pharmacology` for known ligands, quantitative activity, intervention
   direction, selectivity, clinical precedent, and safety.
4. Call `structure_search_rank`, then invoke `assess-computational-pharmacology` to choose a
   structure-based, ligand-based, hybrid, or evidence-only route.
5. Separate supporting evidence, opposing evidence, context, and unresolved questions.
6. State intervention direction and falsifiers. Do not treat association, expression, docking,
   or target prediction as proof of therapeutic direction.

For lipid phenotypes, inspect relevant evidence for de novo lipogenesis,
SREBP-1c/ACC/FASN/SCD1, PPARα/AMPK/CPT1, lipid uptake or efflux, autophagy, and
lipotoxic stress. These are hypothesis branches, not mandatory conclusions.

Write `target_evidence.json` plus the required artifacts from all three specialist skills.
Missing online evidence remains missing; never manufacture a pathway, citation, expression
pattern, ligand action, potency, clinical status, or safety conclusion.

For the adapted open-source workflow basis, read
[`references/open-source-foundations.md`](references/open-source-foundations.md).
