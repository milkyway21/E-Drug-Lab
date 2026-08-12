---
name: featurehit-finding
description: Expands validated poses through pharmacophore, topology, and shape-library screening. Use for H3 feature-hit finding and compound-library expansion.
---

# FeatureHit Finding

This main skill coordinates H3 without replacing the exact-N validators or plot recipes.

## Child skills

- `funnel-featurehit` for topology/pharmacophore feature generation
- `funnel-shape-screen` for pose-based Shape screening
- `pose-library-screening` for library comparison and exact-N selection
- `rdkit` for structure parsing, descriptors, deduplication, and fingerprints

## Gate

Keep generated-parent, pose, library, and selected-hit IDs linked. Report observed counts,
similarity/feature criteria, excluded structures, and all figures before moving to ADMET.
Use only current-task library outputs and preserve relative provenance.
