---
name: research-target-biology
description: Use before structure or pocket selection to orchestrate target identity resolution, reproducible biomedical evidence search, pharmacology assessment, computational-route assessment, and an auditable supporting, opposing, and unresolved target dossier.
---

# Research Target Biology

Call `target_biology_search` first for target-based work, then route through the specialized
skills rather than treating its initial card as complete.

Workflow:

1. Resolve a reviewed human UniProt record and retain UniProt and Ensembl identifiers.
2. Invoke `search-biomedical-evidence` for multi-source biology, tissue, genetics, pathways,
   literature, negative evidence, and a reproducible query manifest.
3. Invoke `assess-target-pharmacology` for known ligands, quantitative activity, intervention
   direction, selectivity, clinical precedent, and safety.
4. Call `structure_search_rank`, then invoke `assess-computational-pharmacology` to choose a
   structure-based, ligand-based, hybrid, or evidence-only route.
5. Separate supporting evidence, opposing evidence, context, and unresolved questions.
6. State intervention direction and falsifiers. Do not treat association, expression, docking,
   or target prediction as proof of therapeutic direction.

For lipid phenotypes, inspect relevant evidence for de novo lipogenesis,
SREBP-1c/ACC/FASN/SCD1, PPARα/AMPK/CPT1, lipid uptake or efflux, autophagy, and
lipotoxic stress. These are hypothesis branches, not mandatory conclusions.

Write `target_evidence.json` plus the required artifacts from all three specialist skills.
Missing online evidence remains missing; never manufacture a pathway, citation, expression
pattern, ligand action, potency, clinical status, or safety conclusion.

For the adapted open-source workflow basis, read
[`references/open-source-foundations.md`](references/open-source-foundations.md).

## Universal Manifest Invocation

Declare target or phenotype, organism, tissue context, source policy, and output locations.
Use ordered steps when the dossier requires several source families; each step preserves
its query and source IDs.

```bash
bash scripts/run_skill.sh --skill research-target-biology --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill research-target-biology --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill research-target-biology --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill research-target-biology --manifest MANIFEST --resume --execute --confirm
```

The handoff is complete only when identity, support, opposition, unresolved questions,
pharmacology, structure route, and falsifiers are present. A failed source is an evidence
record with a retry or exclusion reason, not a reason to fill the gap from model memory.
Keep biological evidence separate from docking, ADMET, and MD predictions.
## Concrete Operation Procedure

Use the registered project tools in this order and retain every JSON response as evidence:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
DISEASE="DISEASE_OR_PHENOTYPE"
TASK_ROOT="tasks/${TARGET_ID}/01_target"
mkdir -p "$TASK_ROOT"
masld-agent platform-catalog --id ed.skill-tree --json > "$TASK_ROOT/registry.json"
masld-agent evidence target --gene "$TARGET_ID" --disease "$DISEASE" --online \
  --output "$TASK_ROOT/target_evidence.json"
masld-agent evidence structures --gene "$TARGET_ID" --limit 25 \
  > "$TASK_ROOT/structure_candidates.json"
```

After the seed card, call `search-biomedical-evidence`, `assess-target-pharmacology`, and `assess-computational-pharmacology` as registered tools with the previous artifact paths. Each tool must return its source IDs, query or activity fields, supporting/opposing evidence, unresolved fields, route decision, and next skill. Do not pass a target name alone and do not synthesize missing facts from memory.

## Standalone Command-Line Procedure

Collect a reusable evidence dossier with public APIs before structure work:

```bash
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
DISEASE="${DISEASE:?disease or phenotype}"
OUT_DIR="${OUT_DIR:-target_evidence}"
mkdir -p "$OUT_DIR"
curl --fail --silent --show-error --location --get \
  'https://rest.uniprot.org/uniprotkb/search' \
  --data-urlencode "query=gene_exact:${TARGET_ID} AND organism_id:9606" \
  --data 'format=json' --data 'size=10' -o "$OUT_DIR/uniprot.json"
curl --fail --silent --show-error --location --get \
  'https://www.ebi.ac.uk/europepmc/webservices/rest/search' \
  --data-urlencode "query=${TARGET_ID} AND ${DISEASE}" \
  --data 'format=json' --data 'pageSize=100' -o "$OUT_DIR/europepmc.json"
```

Normalize each result into identity, support, opposition, unresolved question, source ID,
query, access date, and citation fields. Separate target biology from computational
predictions. Write a decision record for the intervention direction and falsifiers; a
failed or contradictory source is retained as evidence, not silently omitted.
