---
name: search-biomedical-evidence
description: Use during target identification and validation to run a reproducible, multi-source biomedical literature and database search covering target identity, human genetics, disease biology, tissue context, pathways, perturbation direction, safety, and contradictory evidence.
---

# Search Biomedical Evidence

Run after the initial `target_biology_search` result and before pharmacology or structure
selection. Treat that tool result as a seed dossier, not a complete literature review.

Required inputs:

- normalized gene symbol plus UniProt and Ensembl identifiers when available
- disease or phenotype with synonyms and ontology identifiers when available
- organism and relevant tissue or cell context
- intervention question: inhibit, activate, degrade, replace, or still unresolved

Workflow:

1. Lock target identity. Reject aliases that resolve to another human gene, isoform, or family
   member.
2. Search four tracks separately: disease association and human genetics; tissue and cell
   context; pathway and perturbation biology; null, paradoxical, adverse, and opposing evidence.
3. Use PubMed or Europe PMC for biomedical papers. Add CrossRef for DOI verification and
   bioRxiv/medRxiv only for recent preprints. Prefer official database APIs for structured facts.
4. Record the exact query, source, filters, access date, result count, identifiers, and local
   inclusion or exclusion decisions.
5. Extract evidence into claim-sized records. Keep model species, tissue, perturbation,
   intervention direction, endpoint, effect direction, and PMID/DOI together.
6. Separate supporting, opposing, and unresolved evidence. Association, expression, and
   pathway membership do not establish the therapeutic direction.
7. Deduplicate by PMID, then DOI, then normalized title and year. Verify every citation before
   it enters a final report.

When registered, prefer `pubmed_search_articles`, `pubmed_fetch_articles`,
`pubmed_find_related`, `pubmed_lookup_mesh`, `search_crossref`, `search_biorxiv`, and
`search_medrxiv`. Otherwise use the existing `target_biology_search` result plus official APIs
or bounded web retrieval. Do not install a new package, invent an unavailable MCP tool, or
replace missing evidence with model memory.

Write:

- `literature_search_manifest.json` with reproducible queries and result accounting
- `biomedical_evidence.json` with identity, evidence tracks, support, opposition, and gaps
- `biomedical_evidence_table.csv` with one row per claim-source-context record

Hard gates:

- Preprints and computational studies cannot independently establish target validity.
- Animal or cell evidence must not be relabeled as human evidence.
- Expression enrichment is context evidence, not causal validation.
- Every mechanistic direction must cite perturbational or pharmacological evidence.
- Report zero-result and failed-source searches explicitly.

Read [`references/source-routing.md`](references/source-routing.md) before selecting databases
or constructing the evidence table.

## Universal Manifest Invocation

The manifest supplies normalized identity, query plan, source allowlist, cache policy, and
output paths. Use one ordered step per source family or query phase so a partial search can
resume without repeating successful requests.

```bash
bash scripts/run_skill.sh --skill search-biomedical-evidence --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill search-biomedical-evidence --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill search-biomedical-evidence --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill search-biomedical-evidence --manifest MANIFEST --resume --execute --confirm
```

Persist normalized query text, source, filters, access timestamp, result count, included
IDs, excluded IDs, and failure reason. Retry only the failed query or source; do not rerun
the complete search because a later report step failed. Deduplicate by stable identifiers
before synthesis and keep animal, cell, human, computational, and clinical evidence apart.
## Concrete Operation Procedure

Create the seed card once, then run one registered search step per source family:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
DISEASE="DISEASE_OR_PHENOTYPE"
TASK_ROOT="tasks/${TARGET_ID}/01_target"
mkdir -p "$TASK_ROOT"
masld-agent evidence target --gene "$TARGET_ID" --disease "$DISEASE" --online \
  --output "$TASK_ROOT/target_evidence.json"
```

Call the search skill with target identifiers, synonyms, organism, tissue/cell context, intervention question, source allowlist, and output directory. Save normalized query, source, access date, result count, included IDs, excluded IDs, and failure reason. A zero-result query is retained as an evidence gap; retry only the failed source step.

## Standalone Command-Line Procedure

The generic evidence route uses official HTTP APIs and writes raw responses before
interpretation. Use a URL-encoded query and preserve the returned identifiers.

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
DISEASE="DISEASE_OR_PHENOTYPE"
OUT="$(realpath -m outputs/01_evidence)"
mkdir -p "$OUT/raw"
QUERY="${TARGET_ID} AND ${DISEASE}"
curl --fail --silent --show-error --location \
  --get 'https://www.ebi.ac.uk/europepmc/webservices/rest/search' \
  --data-urlencode "query=${QUERY}" --data 'format=json' --data 'pageSize=100' \
  -o "$OUT/raw/europepmc.json"
curl --fail --silent --show-error --location \
  --get 'https://api.crossref.org/works' \
  --data-urlencode "query=${QUERY}" --data 'rows=20' \
  -o "$OUT/raw/crossref.json"
```

For NCBI, use E-utilities with the approved API key/rate policy. Normalize each claim
with source ID, model system, intervention direction, endpoint, effect direction, and
access time; keep contradictory and zero-result responses rather than filling them from
memory. Raw JSON is evidence provenance, not a final biological conclusion.
