---
name: funnel-featurehit
description: Expand H3 hits from validated seed molecules using an explicitly named Morgan, Phase, or shape backend with deterministic lineage. Use after primary Glide SP selection; do not label topology similarity as pharmacophore evidence.
---

# FeatureHit

Set `stages.H3.backend` to `rdkit_morgan`, `schrodinger_phase`, or
`shape_only`. Do not call Morgan a pharmacophore result. For Morgan use radius 2,
2048 bits, deterministic Tanimoto sorting, and write query ID, library ID, score,
canonical SMILES, and backend to the output manifest.

Phase is allowed only after probing the installed 2023-3 CLI and verifying the
database and query formats. Failed Phase attempts must remain isolated and must not
be merged with valid hits.
