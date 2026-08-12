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
