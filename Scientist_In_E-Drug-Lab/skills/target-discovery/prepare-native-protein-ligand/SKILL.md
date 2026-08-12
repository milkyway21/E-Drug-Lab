---
name: prepare-native-protein-ligand
description: Use after selecting a ligand-bound RCSB structure to download coordinates and CCD topology, clean the target protein, extract the correct native ligand instance without moving it, validate receptor-ligand coordinate consistency, and expose a strict DiffDynamic handoff using clean receptor PDB plus native ligand SDF.
---

# Prepare Native Protein Ligand

Call `structure_prepare_native` after `structure_search_rank` and before `pocket_qualify`.
Do not replace this step with manual `grep HETATM`, ligand centering, or a newly written
task-local parser.

Required inputs:

- selected PDB ID and target protein chain IDs from E2
- selected ligand CCD component ID from the ranked structure metadata
- a new task-local output directory
- ligand chain/residue only when the user or evidence requires a specific copy
- cofactors or metals to retain, explicitly listed in `keep_hetero`

The tool must write and validate:

- untouched downloaded mmCIF (or supplied PDB/mmCIF) complex coordinates and CCD source
- `receptor/*_receptor_clean.cif` with selected protein chains, protein-like modified
  residues, and explicitly retained cofactors; water and the selected ligand removed;
  also write PDB when every identifier and coordinate is representable without loss
- `ligand/*_native.cif` using deposited coordinates; also write PDB only when the ligand
  component ID and records are representable in legacy PDB format
- `ligand/*_native.sdf` using CCD bond topology and the same deposited coordinates
- `ligand_instances.csv`, `pocket_center.json`, and `structure_preparation_manifest.json`

## DiffDynamic handoff

DiffDynamic accepts exactly these two structure artifacts:

- protein: `receptor/*_receptor_clean.pdb`
- ligand: `ligand/*_native.sdf`

Read `structure_preparation_manifest.json.diffdynamic_input` and use its declared paths.
If `compatible=false` or either path is absent, block H1 and return to structure selection or
E2b preparation. Never give DiffDynamic the untouched source/complex, receptor CIF/mmCIF,
ligand PDB/MOL2, or Protein Preparation Wizard MAE/MAEGZ. Do not improvise an ad hoc conversion.

Hard gates:

1. The ligand component exists in the selected coordinate model.
2. If several copies exist, select the explicit instance; otherwise use the copy with the
   most 5 Å contacts to the selected target chains, then shortest distance and atom count.
3. `same_coordinate_frame=true`, `translation_or_rotation_applied=false`, and
   `sdf_max_abs_coordinate_delta_A <= 0.001`.
4. The cleaned receptor contains protein atoms and excludes the selected ligand and water.
5. Explicit covalent ligand-protein connections stop this generic workflow and require a
   dedicated covalent-complex preparation decision.
6. Report that coordinate cleaning does not replace protonation, missing-residue repair, bond
   order review, or a validated Protein Preparation Wizard stage.
7. Before DiffDynamic, require `diffdynamic_input.compatible=true`, protein suffix `.pdb`, and
   ligand suffix `.sdf`; any other format is a hard gate.

Use the extracted native-ligand heavy-atom centroid as the evidence-supported pocket center.
Never use ideal CCD coordinates as the docking pose: CCD supplies topology only; coordinates
must come from the selected PDB ligand instance.

Use deposited mmCIF as the online canonical source. Do not fail merely because the legacy PDB
download is absent or a modern CCD ID is longer than three characters.

After completion report selected instance, protein/ligand atom counts, retained cofactors,
coordinate delta, warnings, relative artifact paths, and the next `pocket_qualify` call.

For the artifact contract and recovery rules, read
[`references/artifact-contract.md`](references/artifact-contract.md).
