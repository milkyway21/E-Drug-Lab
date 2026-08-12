---
name: qualify-binding-pocket
description: Use after structure ranking to decide whether a binding pocket and structure-based docking are biologically applicable, evidence-supported, and reproducible.
---

# Qualify Binding Pocket

Call `pocket_qualify` before any Glide stage. For a ligand-supported experimental pocket,
first require `prepare-native-protein-ligand` to produce a valid
`structure_preparation_manifest.json`.

A pocket qualifies only when all applicable conditions hold:

- the mechanism is target-based rather than purely phenotypic
- the selected structure has verified target identity and usable coordinates
- a co-crystal ligand, substrate, cofactor, functional residue set, or literature supports the site
- the selected assembly and construct do not invalidate the proposed site
- the native ligand and cleaned receptor remain in one coordinate frame, with no ligand
  translation, rotation, or minimization during extraction

Write `pocket_manifest.json` with `applicable`, `qualified`, evidence basis, rejection
reasons, and `docking_recommendation`. If qualification fails, continue the nomination as
a phenotype or annotation branch and mark docking `not_applicable`; do not invent a grid center.

## Universal Manifest Invocation

Provide the evidence dossier, structure-preparation manifest, ligand centroid or declared
site evidence, and an explicit qualification command or ordered steps. This skill never
chooses a pocket center from a target name.

```bash
bash scripts/run_skill.sh --skill qualify-binding-pocket --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill qualify-binding-pocket --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill qualify-binding-pocket --manifest MANIFEST --execute --confirm
```

Validate assembly, chains, ligand instance, frame equality, contacts, cofactor state,
missing residues, and site-supporting sources. The output contains a machine-readable
`qualified` decision, evidence IDs, center definition, excluded residues, warnings, and
the exact downstream skill allowed next. `not_applicable` is a valid result.
## Concrete Operation Procedure

Load the target evidence, selected structure, and preparation manifest, then call the registered `pocket_qualify` tool with a structured payload containing target gene, selected structure, key residues, evidence IDs, ligand instance, cofactor state, mechanism policy, frame check, and pocket-center source.

The tool must write `pocket_manifest.json` with `applicable`, `qualified`, `docking_recommendation`, center definition, evidence basis, warnings, and rejection reasons. Accept `docking_recommendation=dock` only when the native ligand/site evidence and same-frame checks pass. For `not_applicable`, preserve the reason and route to ligand/evidence nomination.

## Standalone Command-Line Procedure

Qualify a pocket from explicit structure-preparation and evidence files without a manifest:

```bash
PREP_MANIFEST="${PREP_MANIFEST:?structure preparation manifest JSON}"
EVIDENCE="${EVIDENCE:?target/pocket evidence JSON}"
OUT="${OUT:-pocket}"
mkdir -p "$OUT"
jq -e '.receptor_pdb and .native_ligand_sdf and .coordinate_delta_angstrom != null' \
  "$PREP_MANIFEST" > /dev/null
jq -e '.target_id and (.sources | length > 0)' "$EVIDENCE" > /dev/null
printf '%s\n' 'Inspect contacts, ligand instance, assembly, cofactors, missing residues, and frame equality with a structure viewer or validated structural parser.'
```

Write `pocket_manifest.json` with selected receptor/ligand hashes, ligand chain and
residue, contact residues, center source, evidence IDs, coordinate delta, exclusions,
warnings, and `qualified`/`not_applicable`. Compute a grid center only from the native
ligand or an explicitly cited site. If frame, identity, or site evidence fails, stop the
docking branch and preserve the rejection reason.
