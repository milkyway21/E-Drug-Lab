---
name: nominate-lipid-modulators
description: Use to rank official-library compounds for lipid-lowering or related phenotypes with configurable evidence weights, uncertainty penalties, safety prioritization, diversity, and testable mechanism hypotheses.
---

# Nominate Lipid Modulators

Call `nominate_compounds` after E0 inputs are locked. The tool executes E0-E6 and writes a
report after every stage. Do not reproduce the score manually in conversation.

Default score:

- lipid phenotype evidence: 30%
- mechanism and pathway consistency: 20%
- direct activity and assay quality: 15%
- safety: 20%
- structure and developability: 10%
- chemical diversity: 5%
- missing or conflicting evidence penalty: up to 20 points

Docking is conditional evidence. A candidate is not penalized merely because docking is
biologically inapplicable. Invalid identity and non-library provenance cannot enter the final list.

For every nominee, state the ranking basis, toxicity basis, mechanism chain, alternatives,
falsifiers, evidence level, uncertainty, and dual lipid/viability validation readouts.

Required outputs are `nomination_scorecard.csv`, `top10_nomination.csv`,
`mechanism_validation.md`, `hepg2_validation_plan.md`, `nomination_contract.json`, and
`evidence_provenance.json`. Human-readable files default to Chinese; pass `language=en` or
`--language en` for English text without changing CSV field names or JSON keys.

## Competition submission gate

Do not call a nomination submission-ready until the Top10 rows contain the official
library ID, canonical SMILES, parent InChIKey, library SHA-256, library source, ranking basis,
serialized score components, evidence references, toxicity status (`observed`,
`predicted_only`, or `unknown`), mechanism hypothesis, and linked validation readouts.
The validation plan must specify the HepG2-FFA model, FFA induction, concentration-response,
controls, independent replicates, lipid and viability readouts, a provisional viability
threshold, the cytotoxic false-positive rule, and mechanism follow-up.

## Universal Manifest Invocation

Use this skill for any target or phenotype when the manifest locks the official
library, evidence inputs, candidate outputs, resources, validation, and report
location. Supply an explicit argv `command` or ordered `steps`; never infer a
small-molecule set from the requested final count.

```bash
bash scripts/run_skill.sh --skill nominate-lipid-modulators --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill nominate-lipid-modulators --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill nominate-lipid-modulators --manifest MANIFEST --status
bash scripts/run_skill.sh --skill nominate-lipid-modulators --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill nominate-lipid-modulators --manifest MANIFEST --resume --execute --confirm
```

Preserve library IDs, parent identity, evidence provenance, uncertainty, and
dual lipid/viability reasoning in the declared outputs.

## Concrete Operation Procedure

Run the registered evidence nomination tool on the official library after locking E0:

```bash
masld-agent evidence nominate --library "$OFFICIAL_LIBRARY" \
  --output "$CAMPAIGN_ROOT/evidence" --final-count "$FINAL_COUNT" \
  --disease "$DISEASE" --target-gene "$TARGET_ID" --online
```

Inspect `nomination_scorecard.csv`, `top10_nomination.csv`,
`mechanism_validation.md`, and `evidence_provenance.json`. For every nominee explain
rank basis, observed/predicted/unknown toxicity, pathway direction, evidence IDs,
uncertainty, alternative mechanism, falsifier, and matched lipid/viability readouts.
The score is a deterministic nomination aid, not experimental efficacy.

## Standalone Command-Line Procedure

This child can be run directly with explicit library and evidence paths; no manifest is
required:

```bash
LIBRARY="${LIBRARY:?official compound-library SDF}"
OUT_DIR="${OUT_DIR:-nomination}"
mkdir -p "$OUT_DIR"
masld-agent evidence nominate --library "$LIBRARY" --output "$OUT_DIR" \
  --final-count "${FINAL_COUNT:-10}" --target-gene "${TARGET_ID:-}" \
  --disease "${DISEASE:-target disease}" --online
```

If no project CLI is available, reproduce the same operation with RDKit descriptors,
source-database identity joins, and a versioned ranking script. Keep rank components
separate: structure/property fit, direct or pathway evidence, literature support,
observed/predicted/unknown toxicity, and uncertainty. Export the complete scorecard and
the top-N table, and include a falsifier plus matched lipid and viability readouts for
every nominee.
