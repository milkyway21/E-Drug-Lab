---
name: enrich-compound-evidence
description: Use after candidate generation or library screening to normalize official-library identities and enrich compounds with properties, assays, targets, pathways, literature, and provenance without merging incompatible evidence.
---

# Enrich Compound Evidence

Use `compound_evidence_enrich` for local identity normalization or
`nominate_compounds` for the complete E0-E6 workflow.

Identity rules:

- preserve the official library ID and source
- standardize to a parent structure and parent InChIKey
- retain stereochemistry in canonical SMILES
- collapse salts or duplicates only by parent identity and keep provenance
- quarantine invalid structures instead of silently dropping them

Evidence rules:

- preserve ChEMBL assay ID, target, organism, endpoint, relation, value, units, and document
- use PubChem only after exact identity matching
- never compare incompatible endpoint types or units as one potency series
- distinguish direct target activity, cellular phenotype, literature annotation, and prediction

Write `compound_evidence.jsonl`. Unknown fields stay unknown and contribute to uncertainty.
