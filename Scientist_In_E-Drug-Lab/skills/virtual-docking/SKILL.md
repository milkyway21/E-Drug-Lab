---
name: virtual-docking
description: Routes Glide SP, Glide XP, and MMGBSA refinement with lineage and validation. Use for H2 primary docking or H5-H7 refinement of validated compounds.
---

# Virtual Docking

This main skill owns structure-based ranking after generation or ADMET filtering.

## Child skills

- `funnel-glide-sp` for primary and refinement Glide SP
- `ddfast-07-glide-sp` only for legacy manifests
- `funnel-glide-xp` for H6 XP refinement
- `funnel-mmgbsa` for H7 MMGBSA

## Order

1. Run H2 Glide SP on validated H1 output and preserve parent IDs.
2. Validate poses, scores, counts, and receptor/grid compatibility.
3. Run H5 SP refinement, H6 XP, and H7 MMGBSA only on the frozen parent set.
4. Pass validated complexes and scores to `molecular-dynamics` or `all-analysis`.

Never use a legacy alias for new work, never mix receptor frames, and never call a score
an experimental binding measurement.
