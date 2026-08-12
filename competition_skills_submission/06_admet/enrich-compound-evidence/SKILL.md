---
name: enrich-compound-evidence
description: Use after candidate generation or library screening to normalize official-library identities and enrich compounds with properties, assays, targets, pathways, literature, and provenance without merging incompatible evidence.
---

# Enrich Compound Evidence

Use `compound_evidence_enrich` for local identity normalization or
`nominate_compounds` for the complete E0-E6 workflow.

Identity rules:

- preserve the official library ID and source
- standardize to a parent structure and parent InChIKey
- retain stereochemistry in canonical SMILES
- collapse salts or duplicates only by parent identity and keep provenance
- quarantine invalid structures instead of silently dropping them

Evidence rules:

- preserve ChEMBL assay ID, target, organism, endpoint, relation, value, units, and document
- use PubChem only after exact identity matching
- never compare incompatible endpoint types or units as one potency series
- distinguish direct target activity, cellular phenotype, literature annotation, and prediction

Write `compound_evidence.jsonl`. Unknown fields stay unknown and contribute to uncertainty.

## Universal Manifest Invocation

Use this skill for any target, disease, or official compound library. The manifest
declares identity/evidence inputs, normalized and enriched outputs, resources,
validation, reporting, and an explicit argv `command` or ordered `steps`.

```bash
bash scripts/run_skill.sh --skill enrich-compound-evidence --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill enrich-compound-evidence --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill enrich-compound-evidence --manifest MANIFEST --status
bash scripts/run_skill.sh --skill enrich-compound-evidence --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill enrich-compound-evidence --manifest MANIFEST --resume --execute --confirm
```

Never infer identity or merge incompatible assays; preserve relative provenance and
keep unknown fields visible in the declared report outputs.

## Concrete Operation Procedure

Use the registered Hermes tool on the frozen current-task library. The call shape is:

```text
compound_evidence_enrich({
  "library": "{campaign_root}/03_h3/exact_n_library.sdf",
  "output": "{campaign_root}/04_admet/compound_evidence.jsonl",
  "library_source": "official_sdf_library"
})
```

Before the call, verify the SDF is readable and official library IDs are present. After
the call, count JSONL records and check parent InChIKeys, PubChem/ChEMBL IDs, assay
context, source IDs, and explicit unknowns. The next toxicity skill consumes this JSONL;
it must not reconstruct identity from raw SMILES or silently merge salts/states.

## Standalone Command-Line Procedure

For a shared skill installation, run the evidence stages without a manifest. Use the
project CLI only as an optional adapter; the inputs and outputs below are the portable
contract:

```bash
INPUT_SDF="${INPUT_SDF:?candidate SDF with stable library IDs}"
OUT_DIR="${OUT_DIR:-evidence}"
mkdir -p "$OUT_DIR"
masld-agent evidence nominate --library "$INPUT_SDF" --output "$OUT_DIR" \
  --final-count "${FINAL_COUNT:-10}" --target-gene "${TARGET_ID:-}" \
  --disease "${DISEASE:-target disease}" --online
```

If the project adapter is unavailable, query official identifiers with the source APIs
used by the library owner, then write one JSONL row per input record. Retain the original
library ID, canonical parent InChIKey, canonical SMILES, source database/record ID,
assay endpoint/value/unit/context, target/pathway, citation ID, query timestamp, and an
explicit `unknown` value for every field that was not found. Validate record count and
stable-ID uniqueness before passing `compound_evidence.jsonl` to toxicity triage; never
replace an unavailable evidence service with a guessed annotation.
