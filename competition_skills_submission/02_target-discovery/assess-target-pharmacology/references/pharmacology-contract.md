# Pharmacology Contract

## Source routing

| Need | Preferred source | Secondary source |
|---|---|---|
| Curated target class, ligand action, nomenclature | IUPHAR/BPS Guide to Pharmacology | UniProt |
| Bioactivity and assay records | ChEMBL | BindingDB |
| Binding affinities by UniProt or PDB target | BindingDB | ChEMBL |
| Compound identity and cross-references | PubChem, UniChem | ChEMBL molecule record |
| Drug mechanism and target-disease precedent | Open Targets drug records | primary literature |
| Clinical development | ClinicalTrials.gov API v2 | peer-reviewed trial report |
| Approved-label safety | authoritative regulator or product label | pharmacovigilance literature |

Do not use restricted DrugBank data unless credentials and reuse rights are explicitly available.

## Quantitative activity fields

For every activity retain:

- target accession, target ChEMBL or GtoPdb ID, target type, organism, construct or mutation
- parent compound identity, stereochemistry, salt handling, ChEMBL/PubChem identifiers
- assay ID, assay type, description, format, cell line, substrate and cofactors when reported
- standard type, relation, value, units, `pChEMBL` when supplied, and data validity comments
- direct binding versus functional versus cellular phenotype
- action type and direction; document when absent rather than guessing
- PMID/DOI or source record, access date, and database release when available

Aggregate only measurements with compatible target form, assay meaning, units, and endpoint.
Report ranges and heterogeneity instead of selecting the most favorable value.

## Decision labels

- `validated_direction`: direct perturbation and pharmacology agree with the disease hypothesis
- `pharmacology_available_direction_uncertain`: ligands exist but therapeutic action is unresolved
- `tool_compounds_only`: useful experimental ligands without adequate clinical or selectivity data
- `clinical_precedent`: human interventional program exists; efficacy still requires results
- `no_usable_pharmacology`: no identity-resolved, context-complete direct evidence found

## Official API references

- IUPHAR/BPS Guide to Pharmacology web services:
  <https://www.guidetopharmacology.org/webServices.jsp>
- ChEMBL REST API: <https://www.ebi.ac.uk/chembl/api/data/docs>
- BindingDB web services: <https://w.bindingdb.org/rwd/bind/BindingDBRESTfulAPI.jsp>
- ClinicalTrials.gov API v2: <https://clinicaltrials.gov/data-api/api>
