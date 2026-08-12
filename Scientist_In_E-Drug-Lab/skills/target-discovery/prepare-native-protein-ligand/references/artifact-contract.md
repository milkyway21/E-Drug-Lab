# Artifact Contract

## Required files

| Artifact | Requirement |
|---|---|
| `source/<PDB>.cif` or `.pdb` | Cached RCSB deposited coordinate source or identical supplied fixture |
| `source/<LIG>_ccd.cif` | RCSB CCD atom and bond definitions |
| `complex/<PDB>_complex_original.*` | Untouched complex coordinate copy in source format |
| `receptor/<PDB>_receptor_clean.cif` | Selected protein chains in the source coordinate frame |
| `receptor/<PDB>_receptor_clean.pdb` | Compatibility output when lossless legacy PDB representation is possible |
| `ligand/*_native.cif` | Selected ligand instance in deposited coordinates |
| `ligand/*_native.pdb` | Optional compatibility output when lossless legacy PDB representation is possible |
| `ligand/*_native.sdf` | CCD topology with selected-instance deposited coordinates |
| `ligand_instances.csv` | Every matching ligand copy and deterministic selection metrics |
| `pocket_center.json` | Native ligand heavy-atom centroid in the receptor coordinate frame |
| `structure_preparation_manifest.json` | Selection, cleaning, hashes, counts, warnings, and validation |

## DiffDynamic handoff contract

Only `receptor/<PDB>_receptor_clean.pdb` may be assigned to DiffDynamic's protein input and
only `ligand/*_native.sdf` may be assigned to its ligand input. The manifest field
`diffdynamic_input.compatible` must be true and its two relative paths must exist. Source or
untouched complex files, receptor CIF/mmCIF, ligand PDB/MOL2, and MAE/MAEGZ are forbidden.
Keep those provenance and downstream preparation artifacts outside the compact DiffDynamic
input directory rather than deleting them.

## Recovery rules

- Missing ligand ID: return a hard error; go back to E2 metadata rather than guessing a solvent.
- Multiple copies: provide chain/residue when biology identifies one; otherwise retain the
  deterministic contact-ranked choice and report all copies.
- CCD atom mismatch: stop before docking. Do not write an SDF from guessed atom order.
- Modified residues, cofactors, or metals: keep only protein-like residues and explicitly
  requested components; list every retained component.
- Covalent ligand, alternate biological assembly, or unresolved pocket chain: stop and request
  a dedicated structure-preparation decision. Do not silently change the coordinate source.
- Missing legacy PDB or CCD IDs longer than three characters: use deposited mmCIF as canonical
  input and omit only the incompatible PDB derivative; never truncate component or chain IDs.

## Scientific boundary

The output is coordinate-cleaned, not chemically prepared. Protonation, missing atoms, bond
orders, termini, metal states, restrained minimization, and grid generation remain downstream
validated stages. The extracted ligand is a reference pose and does not prove target activity.
