---
name: prepare-native-protein-ligand
description: Use to prepare same-frame protein and ligand files.
---

# Prepare Native Protein Ligand

Produce coordinate-consistent receptor PDB and native-ligand SDF artifacts from a selected
deposited complex while preserving provenance and the original coordinate frame.

## When to Use

Use after structure ranking and before pocket qualification, DiffDynamic generation, receptor
preparation, grid generation, redocking, or any pose-dependent analysis.

## Prerequisites

- Selected PDB ID, model, protein chains, ligand CCD ID, and exact ligand instance.
- Explicit cofactors, metals, waters, modified residues, and covalent-link policy.
- A structure-aware parser that reads mmCIF and CCD bond topology.

## How to Run

Prefer the registered coordinate-preserving preparation command. A standalone workflow may
download RCSB mmCIF and CCD files, but it must use a structural parser rather than text filters.

## Quick Reference

| Consumer | Protein input | Ligand input |
| --- | --- | --- |
| DiffDynamic | Clean receptor `.pdb` | Deposited-pose `.sdf` |
| Pocket qualification | Receptor plus manifest | Native ligand plus manifest |
| Glide | Separately prepared `.maegz` | LigPrep-ready ligand library |

## Procedure

1. Download and hash deposited mmCIF plus CCD topology.
2. Select the exact model, target chains, ligand instance, and retained cofactors.
3. Extract receptor and ligand without translation, rotation, or minimization.
4. Build SDF bonds from CCD topology while retaining deposited coordinates.
5. Validate atom counts, exclusions, coordinate delta, paths, and handoff formats.

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

## Universal Manifest Invocation

The manifest must name deposited coordinate source, selected model and chains, ligand
component and instance, output receptor PDB, output ligand SDF, and an explicit preparation
command or ordered steps. Never infer the component from the most common ligand name.

```bash
bash scripts/run_skill.sh --skill prepare-native-protein-ligand --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill prepare-native-protein-ligand --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill prepare-native-protein-ligand --manifest MANIFEST --execute --confirm
```

This is coordinate-preserving extraction and cleaning, not a replacement for protonation,
tautomer, bond-order, missing-residue, or force-field preparation. Validate frame equality,
deposited ligand coordinates, receptor exclusion of solvent and extracted ligand, and exact
`.pdb`/`.sdf` suffixes before the DiffDynamic handoff.
## Concrete Operation Procedure

Run the coordinate-preserving preparation command with the selected PDB, CCD, model, chains, and explicit ligand instance:

```bash
TASK_ROOT="tasks/TARGET_ID/03_prepared"
mkdir -p "$TASK_ROOT"
masld-agent evidence prepare-structure --pdb-id "$PDB_ID" --ligand-id "$CCD_ID" \
  --output "$TASK_ROOT" --chains "$CHAIN_LIST" --model "$MODEL_NUMBER" \
  --ligand-chain "$LIGAND_CHAIN" --ligand-resseq "$LIGAND_RESSEQ" \
  --keep-hetero "$COFACTOR_IDS"
CLEAN_PDB="$(find "$TASK_ROOT" -type f -name '*_receptor_clean.pdb' -print -quit)"
NATIVE_SDF="$(find "$TASK_ROOT" -type f -name '*_native.sdf' -print -quit)"
test -s "$CLEAN_PDB" && test -s "$NATIVE_SDF"
masld-agent funnel inspect-sdf --input "$NATIVE_SDF"
```

Read `structure_preparation_manifest.json`; check selected instance, atom counts, water exclusion, coordinate delta, and `diffdynamic_input.compatible`. Only those two discovered files enter DiffDynamic. If the manifest fails, return to structure selection instead of converting a complex or ligand file manually.

## Standalone Command-Line Procedure

The public download route uses RCSB deposited coordinates and CCD topology. Download
both before extraction; do not build a ligand SDF by grepping `HETATM`, and do not use
ideal CCD coordinates as the pose.

```bash
PDB_ID="${PDB_ID:?four-character RCSB entry}"
CCD_ID="${CCD_ID:?ligand CCD component ID}"
OUT="$(realpath -m outputs/03_prepared/${PDB_ID}_${CCD_ID})"
mkdir -p "$OUT/source"
curl --fail --silent --show-error --location \
  "https://files.rcsb.org/download/${PDB_ID}.cif" \
  -o "$OUT/source/${PDB_ID}.cif"
curl --fail --silent --show-error --location \
  "https://files.rcsb.org/ligands/download/${CCD_ID}.cif" \
  -o "$OUT/source/${CCD_ID}_ccd.cif"
```

Use the installed structure-preparation utility or the existing `prepare_native_structure`
implementation to select `MODEL`, protein `CHAINS`, and the exact ligand `CHAIN`/`RESSEQ`.
It must write a cleaned receptor PDB and a CCD-topology SDF carrying deposited ligand
coordinates plus a manifest with atom counts and coordinate delta. If a shared installation
does not provide that parser, stop at this capability gate; do not substitute a text filter.
Before DiffDynamic, the only accepted inputs are `receptor_clean.pdb` and `*_native.sdf`.

For Schrödinger docking after coordinate validation, prepare a separate copy with the
native binary and keep it out of the DiffDynamic input directory:

```bash
SCHRODINGER="${SCHRODINGER:-}"
PREPWIZARD="${PREPWIZARD:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  PREPWIZARD="${PREPWIZARD:-$(masld-agent platform-resolve --id sz.bin.prepwizard)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
PREPWIZARD="${PREPWIZARD:-$SCHRODINGER/utilities/prepwizard}"
"$PREPWIZARD" "$CLEAN_RECEPTOR_PDB" "$OUT/receptor_prepared.maegz" \
  -epik_pH "${EPIK_PH:-7.0}" -fillsidechains -disulfides \
  -propka_pH "${PROPKA_PH:-7.0}" -captermini -WAIT
```

## Pitfalls

- `grep HETATM` loses chemistry, alternate-location, model, and connectivity semantics.
- Ideal CCD coordinates provide topology but are not the deposited binding pose.
- Protein Preparation Wizard output is a Glide receptor artifact, not a DiffDynamic input.
- Generic preparation must stop for an explicit covalent protein-ligand connection.

## Verification

Require source hashes, selected instance, receptor and ligand atom counts, retained cofactors,
water and ligand exclusion, `same_coordinate_frame=true`, no rigid transformation, coordinate
delta at most 0.001 A, and nonempty `.pdb` plus `.sdf` DiffDynamic inputs.
