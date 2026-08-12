# Biomedical Source Routing

## Source matrix

| Question | Primary sources | Cross-check | Required context |
|---|---|---|---|
| Human target identity and function | UniProt reviewed human record, NCBI Gene | Ensembl, HGNC | accession, gene symbol, organism, isoform |
| Target-disease evidence | Open Targets evidence, GWAS Catalog | PubMed, ClinVar when relevant | disease ontology ID, evidence type, direction |
| Tissue and cell relevance | GTEx, Human Protein Atlas | disease tissue studies | tissue, normal/disease state, assay |
| Pathways and processes | Reactome, Gene Ontology | KEGG or WikiPathways | stable pathway/term ID, species |
| Functional partners | curated pathway records | STRING as network support | evidence channel; prediction versus experiment |
| Biomedical literature | PubMed, Europe PMC | CrossRef, related-article search | exact query, PMID/DOI, publication type |
| Recent unpublished work | bioRxiv or medRxiv | later peer-reviewed version | preprint status and version date |

Use Open Targets scores for prioritization, not as causal probabilities. Use STRING and pathway
co-membership as context rather than direct target validation.

## Query tracks

Build separate query families instead of one broad query:

1. `target AND disease-synonyms`
2. `target AND (loss-of-function OR gain-of-function OR knockout OR knockdown) AND phenotype`
3. `target AND tissue-or-cell-type AND (expression OR function OR perturbation)`
4. `target AND (inhibitor OR agonist OR degrader OR ligand) AND phenotype`
5. `target AND (toxicity OR adverse OR null OR paradoxical OR resistance)`

Expand target aliases only after identity resolution. Use MeSH terms where they improve recall,
but retain title and abstract synonyms because newly indexed records may lack complete MeSH.

## Evidence table fields

Record at minimum:

- `claim_id`, `claim`, `evidence_role` (`supporting|opposing|context|unresolved`)
- `source`, `source_record_id`, `pmid`, `doi`, `url`, `accessed_at`
- `species`, `tissue_or_cell`, `disease_context`, `intervention`, `direction`
- `endpoint`, `effect`, `evidence_level`, `verified`, `limitations`
- `search_query_id` linking back to `literature_search_manifest.json`

Do not merge records that differ in intervention direction, model system, assay endpoint, or
target identity.

## Official API references

- NCBI E-utilities: <https://www.ncbi.nlm.nih.gov/home/develop/api/>
- Open Targets GraphQL: <https://platform-docs.opentargets.org/data-access/graphql-api>
- GTEx Portal API: <https://gtexportal.org/api/v2/docs>
- Reactome Content Service: <https://reactome.org/dev/content-service/>
