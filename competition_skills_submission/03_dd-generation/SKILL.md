---
name: dd-generation
description: Runs the validated DiffDynamic generation and Prudent optimization handoff. Use for H1 de novo generation after target and pocket gates pass.
---

# DD Generation

This main skill routes H1a/H1b while preserving the strict protein/ligand handoff and
validated molecule lineage.

## Child skills

- `funnel-diffdynamic-denovo` for H1a pocket-conditioned generation
- `funnel-diffdynamic-prudent` for H1b Prudent generation and post-processing

## Contract

- Input receptor is the cleaned `.pdb` from target preparation.
- Input reference ligand is the same-frame `.sdf`.
- Prudent post-processing uses `--vina-modes none`; compute physicochemical properties,
  canonical deduplication, and validation before H2.
- Reuse a valid existing attempt instead of creating a new attempt directory.

## Gate

Validate generated counts, parseable structures, lineage, and report artifacts before
loading `virtual-docking`. A generation failure stops the funnel.
