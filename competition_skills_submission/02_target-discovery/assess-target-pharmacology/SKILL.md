---
name: assess-target-pharmacology
description: Use after target biology research to evaluate target class, endogenous and synthetic ligands, intervention direction, quantitative potency, selectivity, assay context, clinical precedent, pharmacological safety, and contradictory drug evidence.
---

# Assess Target Pharmacology

Run after `search-biomedical-evidence` and before choosing a computational discovery route.

Workflow:

1. Classify the target and feasible modalities: enzyme inhibitor, receptor agonist or antagonist,
   degrader, biologic, substrate mimic, cofactor-site modulator, or currently unsupported.
2. Resolve known ligands through stable compound and target identifiers. Prefer curated
   IUPHAR/BPS Guide to Pharmacology records, ChEMBL, and BindingDB; use PubChem for identity,
   not as proof of target activity.
3. Preserve every quantitative activity with relation, value, unit, activity type, assay ID,
   target form, species, construct, and assay description. Do not collapse `Ki`, `Kd`, `IC50`,
   `EC50`, percent inhibition, and cellular phenotypes into one potency scale.
4. Determine action direction from direct evidence. Distinguish binding from functional
   agonism, antagonism, inhibition, degradation, and downstream phenotype.
5. Assess selectivity against close family members, isoforms, known off-targets, and assay
   interference. Missing selectivity remains unknown.
6. Search ClinicalTrials.gov and authoritative regulatory or label sources for clinical
   precedent, discontinuation, warnings, and target-related adverse effects.
7. Reconcile pharmacology with the biological direction. Flag compounds whose measured action
   conflicts with the proposed therapeutic mechanism.

Write `target_pharmacology.json` and `target_ligand_evidence.csv`. Include target class,
recommended intervention direction, modality options, known ligands, quantitative activities,
clinical precedent, safety liabilities, contradictions, and unresolved fields.

Hard gates:

- Never infer activity from chemical similarity, docking, target prediction, or database
  co-occurrence.
- Never compare potency values without assay context and units.
- Never call a molecule selective when the tested counter-target panel is missing.
- Clinical trial registration is precedent, not proof of efficacy; capture status and results.
- Separate target-mediated toxicity from compound-specific or off-target toxicity.

Read [`references/pharmacology-contract.md`](references/pharmacology-contract.md) for source
routing and the required activity schema.
