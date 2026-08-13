---
name: assess-computational-pharmacology
description: Use to choose a defensible computational discovery route.
---

# Assess Computational Pharmacology

Choose a computational route from target, structure, ligand, and validation evidence rather
than forcing every target through docking.

## When to Use

Use after target pharmacology assessment and before receptor preparation, docking, QSAR,
generation, or library expansion.

## Prerequisites

- Target biology and pharmacology evidence cards.
- Ranked structure candidates and identity-resolved known ligands when available.
- Explicit validation controls, leakage policy, uncertainty, and failure thresholds.

## How to Run

Run the manifest path for an orchestrated campaign or build the same route-decision bundle
from explicit files. This skill decides applicability; it does not launch downstream models.

## Quick Reference

| Route | Minimum support | Required validation |
| --- | --- | --- |
| Structure-based | Qualified pocket and usable receptor | Redocking or pose recovery |
| Ligand-based | Consistent target-specific series | Scaffold-aware held-out split |
| Hybrid | Both independent evidence types | Separate validation for each branch |
| Evidence-only | No defensible model domain | Document blockers and stop |

## Procedure

1. Verify target construct, state, sequence, and ligand identity.
2. Inventory usable structural and ligand evidence.
3. Select exactly one declared route with a written evidence basis.
4. Lock controls, leakage prevention, uncertainty, and stop criteria.
5. Emit the next allowed skill and blockers before any expensive computation.

Run after `assess-target-pharmacology`. When structure-based work is possible, consume the
`structure_search_rank` result before calling `structure_prepare_native` or `pocket_qualify`.

Workflow:

1. Verify target sequence, domain, isoform, oligomeric state, cofactors, catalytic state, and
   disease-relevant construct. Do not mix structures or ligands from incompatible family members.
2. Inventory experimental holo and apo structures, predicted structures, resolved residues,
   mutations, bound ligands, biological assemblies, and supported pockets.
3. Inventory identity-resolved target ligands with activity quality, chemical diversity, and
   inactive or counter-screen examples.
4. Select one route using the decision matrix:
   - structure-based: qualified experimental pocket and native ligand pose
   - ligand-based: adequate consistent target-specific actives but no qualified structure
   - hybrid: both evidence types are usable and independently validated
   - evidence-only: neither route has a defensible applicability domain
5. Define validation before prediction: redocking or pose recovery, decoys and known actives,
   scaffold-aware splits, target-family counter-screens, uncertainty, and failure thresholds.
6. Record what each method can support. Docking ranks poses; QSAR interpolates within its data
   domain; target prediction and generative models produce hypotheses, not measured pharmacology.

Write `computational_pharmacology.json` with `recommended_route`, evidence basis, input IDs,
available structures and ligands, applicability domain, validation plan, blockers, and next call.

For a structure route, continue in order:

1. `structure_prepare_native`
2. `pocket_qualify`
3. docking only when `docking_recommendation=dock`

Hard gates:

- An AlphaFold or apo structure alone does not establish a ligand pocket.
- Do not train or report ligand-based performance without scaffold-aware held-out evaluation.
- Do not mix biochemical binding, functional, and phenotypic labels as one target endpoint.
- Do not use test-set molecules, cognate poses, or close analogues during model fitting.
- If the route is unsupported, report `evidence-only`; do not force docking or QSAR.

Read [`references/route-decision.md`](references/route-decision.md) before selecting the route.

## Universal Manifest Invocation

Declare target evidence files, structure and ligand candidates, route alternatives,
validation design, and an explicit command or ordered steps. This skill decides
applicability; it does not silently launch docking or model fitting.

```bash
bash scripts/run_skill.sh --skill assess-computational-pharmacology --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill assess-computational-pharmacology --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill assess-computational-pharmacology --manifest MANIFEST --execute --confirm
```

For each route state data domain, leakage controls, positive and negative controls,
held-out split, uncertainty, and failure threshold. A qualified experimental holo pocket
can support a structure route; it does not validate ligand-based generalization. If
evidence is insufficient, write `evidence_only` and stop the structure branch cleanly.
## Concrete Operation Procedure

Run route assessment before any docking or model fitting:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
TASK_ROOT="tasks/${TARGET_ID}/01_target"
mkdir -p "$TASK_ROOT"
masld-agent evidence structures --gene "$TARGET_ID" --limit 25 \
  > "$TASK_ROOT/structure_candidates.json"
```

Call `assess-computational-pharmacology` with target evidence, pharmacology evidence, ranked structures, known-ligand table, target/phenotype policy, and validation design. Accept only a declared `structure_based`, `ligand_based`, `hybrid`, or `evidence_only` route. A structure route must hand off to native preparation and pocket qualification; an evidence-only route must stop docking cleanly.

## Standalone Command-Line Procedure

Create an explicit route-decision input bundle before launching any model or docking tool:

```bash
TARGET_ID="${TARGET_ID:?target identifier}"
OUT_DIR="${OUT_DIR:-computational_route}"
mkdir -p "$OUT_DIR"
for input in target_evidence.json pharmacology_evidence.json structure_candidates.json known_ligands.csv; do
  test -s "${INPUT_DIR:-.}/$input" || printf '%s\n' "missing:$input" >> "$OUT_DIR/missing_inputs.txt"
done
jq -n --arg target "$TARGET_ID" --arg route "${ROUTE:-evidence_only}" \
  '{target_id:$target,route:$route,leakage_controls:[],controls:[],held_out_split:null,uncertainty:null,failure_threshold:null}' \
  > "$OUT_DIR/route_decision.json"
```

Replace the empty fields from the actual evidence and validation design. Accept
`structure_based`, `ligand_based`, `hybrid`, or `evidence_only` only with a written basis,
positive/negative controls, leakage policy, held-out design, uncertainty, and failure
threshold. A missing qualified pocket is a clean gate; it is not permission to start
docking from a guessed center.

## Pitfalls

- AlphaFold confidence does not establish a druggable or ligand-supported pocket.
- Random train/test splits can leak close analogues and inflate ligand-model performance.
- A docking score is not target activity, selectivity, or disease efficacy.

## Verification

Require one of `structure_based`, `ligand_based`, `hybrid`, or `evidence_only`, with input
IDs, applicability domain, controls, held-out design, uncertainty, failure threshold,
blockers, and one unambiguous next action.
