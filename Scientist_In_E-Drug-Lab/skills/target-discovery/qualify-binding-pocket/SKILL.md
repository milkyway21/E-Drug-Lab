---
name: qualify-binding-pocket
description: Use to qualify a binding pocket for structure-based work.
---

# Qualify Binding Pocket

Turn structural and mechanistic evidence into an explicit dock, hold, or not-applicable
decision with a reproducible pocket definition.

## When to Use

Use after coordinate-preserving native-complex preparation and before receptor grid
generation, docking, pocket-conditioned generation, or pose interpretation.

## Prerequisites

- Target and mechanism evidence with source IDs.
- Selected structure and validated preparation manifest.
- Native ligand or independently supported functional-site residues.

## How to Run

Use the registered qualifier in a manifest campaign or inspect explicit preparation and
evidence files with a validated structural parser. Never infer a center from a gene name.

## Quick Reference

| Evidence state | Decision | Next action |
| --- | --- | --- |
| Same-frame native ligand and valid site | `dock` | Build and validate a grid |
| Site supported but structural defects remain | `hold` | Repair or select another entry |
| Phenotypic target or unsupported site | `not_applicable` | Use evidence/ligand route |

## Procedure

1. Verify target, assembly, chains, construct, ligand instance, and coordinate frame.
2. Inspect contacts, missing residues, cofactors, metals, waters, and covalent links.
3. Define center from the native ligand or explicitly cited site evidence.
4. Record exclusions, warnings, and a machine-readable qualification decision.
5. Allow grid generation only when the decision is `dock`.

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

## Pitfalls

- A geometric cavity without target or mechanism support is not a qualified binding site.
- A native ligand from another chain or model cannot define the receptor pocket.
- Missing catalytic or contact residues can invalidate an otherwise attractive structure.

## Verification

Confirm receptor and ligand hashes, target chains, ligand instance, contact residues, center
source, cofactors, exclusions, coordinate-frame check, evidence IDs, warnings, and one explicit
`docking_recommendation`. Only `dock` permits grid generation.
