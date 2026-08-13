---
name: target-discovery
description: Use to build a target, structure, and pocket dossier.
---

# Target Discovery

Use this main skill before H0 whenever the task starts from a biological target or a
compound-nomination question. It owns evidence envelope E0-E3 and decides whether a
structure-based branch is scientifically applicable.

## When to Use

Use when a task starts from a gene, protein, disease, phenotype, pathway, or an unknown
choice of receptor/pocket. Skip only when validated target, structure, ligand, and pocket
artifacts are already supplied and their provenance is acceptable.

## Prerequisites

Obtain organism, disease or phenotype, desired intervention direction if known, modality,
official compound library, requested final count, and online/offline policy. Preserve
review dates because public databases change.

## How to Run

Prefer registered evidence and structure tools. Any agent may instead call official REST,
GraphQL, or download endpoints and use a structural parser. Preserve raw responses, query
payloads, endpoint versions, access dates, normalized tables, and citations.

## Quick Reference

Use UniProt for protein identity, Open Targets for target-disease evidence and tractability,
Europe PMC/PubMed for literature, ChEMBL/BindingDB for activities, RCSB Search/Data APIs
for structures, and CCD/ModelServer for ligand chemistry and coordinate subsets.

## Procedure

1. Lock scope and identifiers.
2. Build supporting, opposing, contextual, and unresolved biology evidence.
3. Assess pharmacology and choose structure-, ligand-, hybrid-, or evidence-only route.
4. Search and rank experimental structures before computed models.
5. Extract a native ligand and clean receptor without changing their coordinate frame.
6. Qualify the site and hand off explicit clean PDB/SDF or stop the SBDD branch.

## Child skills

`scope-molecular-nomination`, `research-target-biology`, `search-biomedical-evidence`,
`assess-target-pharmacology`, `rank-protein-structures`,
`assess-computational-pharmacology`, `prepare-native-protein-ligand`, and
`qualify-binding-pocket`.

## Order

1. Define disease, target, desired phenotype, compound-library scope, and final count.
2. Search biology, literature, pharmacology, genetics, expression, and pathway evidence.
3. Rank PDB/UniProt structures and record resolution, construct, ligands, and limitations.
4. Decide the computational route; do not force docking when evidence is insufficient.
5. Prepare a coordinate-cleaned receptor and same-frame native ligand when docking applies.
6. Qualify the pocket and emit `docking_recommendation=dock` or `not_applicable`.

## Gate

Do not begin DiffDynamic or Glide until the structure-preparation manifest passes. Unknown
evidence remains `unknown`; computational predictions are not experimental confirmation.

## Universal Manifest Invocation

This skill accepts any target or disease through a manifest and never fills in a
gene, UniProt record, PDB, ligand, or pocket from memory. Declare the task identity,
stage, relative inputs, expected outputs, resources, validation rules, reporting
location, and an explicit argv `command` or ordered `steps`.

```bash
bash scripts/run_skill.sh --skill target-discovery --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill target-discovery --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill target-discovery --manifest MANIFEST --status
```

Only after reviewing source IDs, coordinate-frame requirements, and command paths:

```bash
bash scripts/run_skill.sh --skill target-discovery --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill target-discovery --manifest MANIFEST --resume --execute --confirm
```

Write evidence and structure provenance below `campaign_root`; preserve unknowns,
failed searches, and rejection reasons. The runner is portable, while this skill's
existing biology and structure gates remain mandatory.

## Universal Target-to-Pocket Protocol

Use this order for any target, disease, phenotype, or modality. The model must not start
molecule generation before it has established the biological question and whether a
structure-based route is applicable.

### E0: lock the question

Record normalized target or phenotype, organism, isoform, tissue or cell context,
intervention direction, library identifier, requested final count, online-search policy,
and compute authorization. Hash the official library. If the request names only a
phenotype, keep `target_id` unresolved until evidence identifies a defensible target;
never select a protein from a familiar benchmark. Write unresolved fields explicitly.

### E1: build the evidence envelope

Resolve a reviewed gene/protein identifier, then search identity, disease genetics,
expression and tissue context, pathway or perturbation evidence, pharmacology, clinical
precedent, and opposing or adverse evidence as separate tracks. Each claim retains source
ID, model system, intervention direction, endpoint, effect direction, access date, and
confidence. A citation list without claim-level context is not a target dossier.

### E2: choose and prepare a structure

Rank experimental structures before predicted models. Prefer a relevant holo structure
with the correct target, construct, assembly, state, and bound ligand. Download deposited
coordinates and ligand definition, select an explicit ligand instance, and write a
same-frame cleaned receptor PDB plus native ligand SDF. The receptor excludes extracted
ligand and solvent; the SDF preserves deposited coordinates and bond topology. Record
chains, retained cofactors or metals, atom counts, coordinate delta, mutations, missing
residues, and source IDs.

### E3: qualify the pocket and route

Use the native-ligand heavy-atom centroid only when the selected ligand is in the same
coordinate frame. A literature-supported site, substrate/cofactor site, or validated
functional residue set may support qualification, but an apo or predicted structure by
itself does not. Emit one of `structure_based`, `ligand_based`, `hybrid`, or
`evidence_only`, with applicability limits and validation criteria. Emit
`docking_recommendation=dock` only when cleaned artifacts and pocket evidence pass.

### Handoff record

The target handoff contains `target_evidence.json`, `target_pharmacology.json`,
`structure_candidates.csv`, `selected_structure.json`,
`structure_preparation_manifest.json`, and `pocket_manifest.json` when applicable.
Every record uses paths relative to `campaign_root` and includes `status`, `source_ids`,
`warnings`, `rejection_reasons`, and `next_skill`. Downstream skills consume these files;
they must not reconstruct the dossier from chat text.

### Generic command contract

For a multi-stage dossier, prefer manifest `steps` so each evidence or structure operation
has its own log and output gate. A step identifies its script or tool, working directory,
timeout, and declared outputs. The generic launcher does not select RCSB, UniProt, PubMed,
a PDB entry, or a pocket center automatically. If a source is unavailable, preserve the
failed query and mark the route `blocked` or `evidence_only` rather than using cached data
from another target.
## Concrete Operation Procedure

Start every target task with the registry and evidence commands below. These commands use only task-relative paths; the registry resolves machine-specific backends.

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
DISEASE="DISEASE_OR_PHENOTYPE"
FINAL_COUNT=10
TASK_ROOT="tasks/${TARGET_ID}"
mkdir -p "$TASK_ROOT/01_target" "$TASK_ROOT/02_structures" "$TASK_ROOT/03_prepared"
masld-agent platform-catalog --id ed.skill-tree --json > "$TASK_ROOT/00_skill_tree.json"
masld-agent evidence target --gene "$TARGET_ID" --disease "$DISEASE" --online \
  --output "$TASK_ROOT/01_target/target_evidence.json"
masld-agent evidence structures --gene "$TARGET_ID" --limit 25 \
  > "$TASK_ROOT/02_structures/structure_candidates.json"
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" > "$TASK_ROOT/00_funnel_plan.json"
```

Read the ranked structure records before choosing a PDB ID, ligand CCD ID, model, chains, and ligand instance. Then run `masld-agent evidence prepare-structure` with those values. Find the generated clean receptor and native ligand with `find`, read `structure_preparation_manifest.json`, and require `diffdynamic_input.compatible=true`, exact `.pdb`/`.sdf` suffixes, same-frame coordinates, and no extracted ligand or solvent in the receptor.

Call `pocket_qualify` only after the preparation manifest and biological evidence are available. `qualified=false` or `not_applicable` is a valid stop: route to ligand/evidence nomination and record why docking is not applicable. Do not invent a pocket center, convert a file ad hoc, or start H1 before this gate.

## Standalone Command-Line Procedure

Without the agent, follow the same evidence order with ordinary HTTP and native tools:

```bash
TARGET_ID="TARGET_GENE_OR_PROTEIN"
DISEASE="DISEASE_OR_PHENOTYPE"
ROOT="$(realpath -m outputs/${TARGET_ID})"
mkdir -p "$ROOT/01_target" "$ROOT/02_structures" "$ROOT/03_prepared"
curl --fail --silent --show-error --location \
  --get 'https://rest.uniprot.org/uniprotkb/search' \
  --data-urlencode "query=gene_exact:${TARGET_ID} AND organism_id:9606" \
  --data 'format=json' --data 'size=10' -o "$ROOT/01_target/uniprot.json"
curl --fail --silent --show-error --location \
  --get 'https://www.ebi.ac.uk/europepmc/webservices/rest/search' \
  --data-urlencode "query=${TARGET_ID} AND ${DISEASE}" \
  --data 'format=json' --data 'pageSize=100' -o "$ROOT/01_target/europepmc.json"
```

Rank structures, download the chosen RCSB entry and CCD, extract the exact native ligand
instance without moving coordinates, qualify the pocket from native contacts/literature,
and only then launch generation. If any gate is unresolved, record `evidence_only` or
`not_applicable` rather than inventing a pocket or docking input.

## Pitfalls

Do not resolve a family member as the requested target, mix isoforms or species, choose a
structure by resolution alone, infer a pocket from a ligand name, or move the ligand during
extraction. Do not treat association scores as causal direction.

## Verification

Require stable target identifiers, query manifests, evidence grading, structure ranking,
selected/rejected reasons, coordinate-clean receptor, native ligand, pocket manifest,
hashes, and an explicit computational-route decision.
