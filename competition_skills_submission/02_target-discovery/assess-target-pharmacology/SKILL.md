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

## Universal Manifest Invocation

The manifest must declare target identity, source policy, activity output schema, and an
explicit command or ordered steps. It must not assume a familiar target or merge all
potency measurements into one score.

```bash
bash scripts/run_skill.sh --skill assess-target-pharmacology --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill assess-target-pharmacology --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill assess-target-pharmacology --manifest MANIFEST --execute --confirm
```

Normalize activities only within compatible assay contexts. Preserve raw relation, value,
unit, activity type, assay, construct, species, and target form. Mark selectivity, safety,
and clinical status as `unknown` when the relevant panel or source is missing. Explain the
intervention direction and list contradictions that could invalidate docking or nomination.
## Concrete Operation Procedure

Prepare the identity and structure inputs before the registered pharmacology call:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
DISEASE="DISEASE_OR_PHENOTYPE"
TASK_ROOT="tasks/${TARGET_ID}/01_target"
mkdir -p "$TASK_ROOT"
masld-agent evidence target --gene "$TARGET_ID" --disease "$DISEASE" --online \
  --output "$TASK_ROOT/target_evidence.json"
masld-agent evidence structures --gene "$TARGET_ID" --limit 25 \
  > "$TASK_ROOT/structure_candidates.json"
```

Call `assess-target-pharmacology` with the evidence-card path, target identifiers, known ligand IDs, potency records, assay context, selectivity panel, clinical status, and safety sources. Keep `Ki`, `Kd`, `IC50`, `EC50`, percent inhibition, and cellular endpoints as distinct records. The handoff is complete only when intervention direction, contradictions, unknowns, and `target_ligand_evidence.csv` are written.

## Standalone Command-Line Procedure

When no agent adapter is present, download public activity evidence and preserve raw assay
context before normalization:

```bash
TARGET_ID="${TARGET_ID:?target identifier}"
OUT_DIR="${OUT_DIR:-target_pharmacology}"
mkdir -p "$OUT_DIR"
curl --fail --silent --show-error --location --get \
  'https://www.ebi.ac.uk/chembl/api/data/activity.json' \
  --data-urlencode "target_synonym__icontains=${TARGET_ID}" \
  --data 'limit=1000' -o "$OUT_DIR/chembl_activity.json"
jq --arg target "$TARGET_ID" \
  '{target:$target,records:(.activities // []) | length}' \
  "$OUT_DIR/chembl_activity.json" > "$OUT_DIR/activity_summary.json"
```

Use a chemistry/database client or versioned script to write `target_ligand_evidence.csv`
with raw relation, value, unit, activity type, assay ID, construct, species, target form,
selectivity, clinical status, safety source, and source document. Never combine assay types
or units into one potency score; keep contradictions and missing panels explicit.
