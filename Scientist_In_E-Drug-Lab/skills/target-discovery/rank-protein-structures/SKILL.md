---
name: rank-protein-structures
description: Use to search and rank target protein structures.
---

# Rank Protein Structures

Search public structure records, verify target identity, and rank experimentally relevant
entries before coordinate preparation.

## When to Use

Use after target identity is resolved and whenever a workflow needs a receptor, native
ligand, supported pocket, or structure-based applicability decision.

## Prerequisites

- Gene symbol plus UniProt accession or sequence identity criteria.
- Species, isoform, domain, state, cofactor, and construct requirements.
- Internet access to RCSB Search and Data APIs, or an equivalent local mirror.

## How to Run

Use the registered evidence command in an agent campaign, or call RCSB Search by POST and
then resolve metadata for every returned PDB entry before ranking.

## Quick Reference

| Field | Prefer | Reject or penalize |
| --- | --- | --- |
| Identity | Correct target and species | Family member or wrong domain |
| Evidence | Experimental holo structure | Unsupported predicted pocket |
| Construct | Relevant state and assembly | Disruptive mutation or truncation |
| Coordinates | Good coverage and resolution | Missing pocket residues |

## Procedure

1. Resolve candidate PDB IDs by target identity, not target-name text alone.
2. Retrieve entry, entity, instance, assembly, ligand, and experimental metadata.
3. Compare chain coverage, mutations, state, ligand context, and missing residues.
4. Rank candidates and preserve rejection reasons.
5. Freeze one selected structure before downloading and preparing coordinates.

Call `structure_search_rank` with the resolved gene or UniProt accession.

Use RCSB Search API for identifiers and RCSB Data API for metadata. Search output alone
is insufficient because it does not establish construct quality or ligand context.

Ranking priority:

1. correct human target identity and relevant domain coverage
2. experimental structure before a computed model
3. relevant bound ligand, substrate, cofactor, or known functional state
4. fewer disruptive mutations or construct artifacts
5. suitable biological assembly and better experimental resolution

Write `structure_candidates.csv` and `selected_structure.json`. Then call
`assess-computational-pharmacology` with the biology, pharmacology, structure, and known-ligand
evidence to choose a defensible route. For a selected ligand-bound entry on the structure route,
call `structure_prepare_native` through `prepare-native-protein-ligand` before pocket
qualification. Metadata ranking alone is not a downloaded or docking-ready structure.

If no experimental candidate is qualified, record that result. A predicted structure may
support a cautious hypothesis but must not be presented as equivalent to a ligand-supported
experimental pocket.

## Universal Manifest Invocation

Declare the resolved target identifier, search terms, downloaded metadata outputs, ranking
policy, and explicit command or ordered steps. The ranker must not substitute a family
member or cached structure because the target has no obvious entry.

```bash
bash scripts/run_skill.sh --skill rank-protein-structures --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill rank-protein-structures --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill rank-protein-structures --manifest MANIFEST --execute --confirm
```

Record candidate identity, sequence coverage, construct, mutations, assembly, ligand
component and instance, method, resolution, missing residues, and source accession. A
ranking table is reconnaissance only; downstream preparation must download and validate
the selected coordinates before it can be called docking-ready.
## Concrete Operation Procedure

Use the existing RCSB-backed command and freeze the selection before downloading coordinates:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
TASK_ROOT="tasks/${TARGET_ID}/02_structures"
mkdir -p "$TASK_ROOT"
masld-agent platform-catalog --id ed.skill-tree --json > "$TASK_ROOT/registry.json"
masld-agent evidence structures --gene "$TARGET_ID" --limit 50 \
  > "$TASK_ROOT/structure_candidates.json"
```

For each candidate record target identity, organism, domain/chain coverage, construct mutations, assembly, method, resolution, ligand component and instance, cofactor state, and missing residues. Select one entry only after comparing those fields; write `selected_structure.json` with rejection reasons for the others. Metadata ranking is not a docking-ready structure.

## Standalone Command-Line Procedure

Use the public RCSB search API with a POST JSON request when no agent is available:

```bash
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
OUT="${OUT:-structures}"
mkdir -p "$OUT"
jq -n --arg target "$TARGET_ID" \
  '{query:{type:"terminal",service:"full_text",parameters:{value:$target}},return_type:"entry",request_options:{paginate:{start:0,rows:50}}}' |
  curl --fail --silent --show-error --location -X POST \
    -H 'Content-Type: application/json' --data-binary @- \
    'https://search.rcsb.org/rcsbsearch/v2/query' -o "$OUT/rcsb_search.json"
```

For each returned ID, query `https://data.rcsb.org/rest/v1/core/entry/<PDB_ID>` and the
polymer/entity and non-polymer component endpoints. Rank target identity, organism,
domain/chain coverage, mutations, assembly, method/resolution, ligand instance/cofactor,
and missing residues. Write selected and rejected structures with reasons; metadata alone
does not make a docking-ready receptor.

## Pitfalls

- Full-text search can return homologues, partners, antibodies, or unrelated annotations.
- The best numerical resolution may represent the wrong domain or biological state.
- A bound crystallization additive is not automatically a native or drug-like ligand.

## Verification

Check that every candidate has target identity, organism, chain coverage, construct,
assembly, method, resolution, ligand instance, cofactors, and missing-residue fields. The
selected JSON must name one entry and explain why alternatives were rejected.
