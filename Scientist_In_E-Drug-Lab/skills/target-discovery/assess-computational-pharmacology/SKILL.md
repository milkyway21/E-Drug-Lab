---
name: assess-computational-pharmacology
description: Use after biological and pharmacological target assessment, together with structure reconnaissance when available, to choose and justify a structure-based, ligand-based, hybrid, or evidence-only computational drug-discovery route and define its applicability limits.
---

# Assess Computational Pharmacology

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
