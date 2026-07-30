---
name: funnel-featurehit
description: H3 topology or pharmacophore library expansion with explicit backend provenance.
---

# FeatureHit

Set `stages.H3.backend` to `rdkit_morgan`, `schrodinger_phase`, or
`shape_only`. Do not call Morgan a pharmacophore result. For Morgan use radius 2,
2048 bits, deterministic Tanimoto sorting, and write query ID, library ID, score,
canonical SMILES, and backend to the output manifest.

Phase is allowed only after probing the installed 2023-3 CLI and verifying the
database and query formats. Failed Phase attempts must remain isolated and must not
be merged with valid hits.
