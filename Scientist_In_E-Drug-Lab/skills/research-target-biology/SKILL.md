---
name: research-target-biology
description: Use before PDB or pocket selection to normalize a target and assemble disease, tissue, pathway, literature, tractability, safety, supporting, and opposing biological evidence.
---

# Research Target Biology

Call `target_biology_search` before `structure_search_rank` for target-based work.

Workflow:

1. Resolve a reviewed human UniProt record and retain UniProt and Ensembl identifiers.
2. Retrieve target-disease evidence and verified literature with PMID or DOI.
3. Retrieve Reactome pathways and retain pathway stable identifiers.
4. Separate supporting evidence, opposing evidence, and unresolved questions.
5. State intervention direction. Do not treat association as proof of therapeutic direction.

For lipid phenotypes, inspect relevant evidence for de novo lipogenesis,
SREBP-1c/ACC/FASN/SCD1, PPARα/AMPK/CPT1, lipid uptake or efflux, autophagy, and
lipotoxic stress. These are hypothesis branches, not mandatory conclusions.

Write `target_evidence.json`. Missing online evidence remains missing; never manufacture
a pathway, citation, expression pattern, or safety conclusion.
