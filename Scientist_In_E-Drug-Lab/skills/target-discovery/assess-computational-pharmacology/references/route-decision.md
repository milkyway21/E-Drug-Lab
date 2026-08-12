# Computational Route Decision

| Evidence state | Route | Minimum validation |
|---|---|---|
| Experimental holo structure, native ligand, qualified pocket | Structure-based | coordinate manifest, pocket gate, redocking or pose recovery, known-actives/decoys |
| Consistent target-specific actives and inactives, no qualified structure | Ligand-based | identity cleanup, endpoint harmonization, scaffold split, applicability domain |
| Qualified pocket plus adequate ligand series | Hybrid | independent structure and ligand validation before score fusion |
| Apo or predicted structure without pocket evidence and sparse ligands | Evidence-only | resolve biology, pharmacology, structure, or assay gaps first |

## Structure assessment

Record PDB ID, UniProt mapping, chains, domain and residue coverage, mutations, assembly,
resolution, ligand and cofactor IDs, pocket support, missing atoms or residues, and structure
state. Prefer a disease-relevant holo experimental structure over nominally higher resolution
with an irrelevant construct.

## Ligand-data assessment

Record exact parent identity, stereochemistry policy, target form, endpoint, assay type, units,
relation, activity quality, duplicate handling, scaffold counts, inactive definition, and
counter-target coverage. A large heterogeneous table is not automatically model-ready.

## Model claims

- Docking: pose and relative-ranking hypothesis within the qualified pocket.
- Shape or pharmacophore: similarity to the reference feature hypothesis.
- QSAR or graph model: interpolation within the measured endpoint and chemical domain.
- Target prediction: prioritization hypothesis requiring direct assay confirmation.
- Molecular dynamics: stability or interaction hypothesis for the simulated setup, not efficacy.

Always pair predictions with uncertainty, applicability limits, and an experimental falsifier.
