---
name: triage-compound-toxicity
description: Use to triage observed and predicted toxicity evidence.
---

# Triage Compound Toxicity

Rank safety evidence by relevance and quality while separating matched cytotoxicity,
organ-toxicity evidence, assay alerts, predictions, and unknowns.

## When to Use

Use after compound evidence enrichment and prediction, during candidate nomination and
experimental validation design.

## Prerequisites

- Stable compound IDs and enriched evidence JSONL.
- Prediction rows with backend/applicability and observed records with endpoint/exposure context.
- Assay-specific viability policy, false-positive rule, and uncertainty scoring method.

## How to Run

Use the registered triage operation for an agent task. Standalone mode joins explicit QikProp
and observed-evidence tables by stable parent/library ID under the same hierarchy.

## Quick Reference

| Evidence level | Example | Label |
| --- | --- | --- |
| Matched experiment | Cell viability at relevant exposure | `observed` |
| Curated organ/safety assay | DILI, hERG assay, cardiotoxicity | `observed` |
| Model or alert | QikProp, SMARTS alert | `predicted_only` |
| No usable record | Missing or unmatched | `unknown` |

## Procedure

1. Join exact compound identities and reject ambiguous mappings.
2. Classify each evidence row by observation/prediction and applicability.
3. Preserve endpoint, concentration, exposure, species/system, and citation.
4. Calculate a reproducible safety rationale without converting unknowns to safe.
5. Link lipid efficacy to matched viability and flag cell-loss false positives.

Call `toxicity_triage` after compound evidence enrichment. For full computational runs,
reuse the existing QikProp skill and import its outputs rather than substituting another ADMET model.

Evidence hierarchy:

1. matched experimental cell viability at relevant concentration and exposure
2. curated human organ-toxicity annotations such as DILI or cardiotoxicity references
3. assay-based safety pharmacology
4. QikProp and structural-alert predictions
5. no data, which must be labeled unknown

Do not infer causality from spontaneous adverse-event counts. A structural alert is a
prediction, not observed toxicity. A database miss is not evidence of safety.

Write `toxicity_evidence.csv` with observed and predicted counts, endpoint, applicability,
rationale, and safety score. Apparent lipid reduction with reduced viability is a false-positive risk.

For the HepG2-FFA competition contract, matched experimental viability is stronger than a
QikProp prediction. A candidate is not low toxicity merely because no record was found.
Keep the final decision as lipid effect plus matched viability, and reject lipid reduction
that is explained by material cell loss.

## Universal Manifest Invocation

Use this skill for any target or compound library when the manifest supplies the
toxicity evidence inputs, predicted/observed output tables, resources, validation,
reporting location, and an explicit argv `command` or ordered `steps`.

```bash
bash scripts/run_skill.sh --skill triage-compound-toxicity --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill triage-compound-toxicity --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill triage-compound-toxicity --manifest MANIFEST --status
bash scripts/run_skill.sh --skill triage-compound-toxicity --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill triage-compound-toxicity --manifest MANIFEST --resume --execute --confirm
```

Keep prediction, observation, unknowns, and dual-readout decisions separate; do
not infer safety from a missing database record.

## Concrete Operation Procedure

Call the registered triage tool using the evidence JSONL from the preceding skill:

```text
toxicity_triage({
  "compound_evidence": "{campaign_root}/04_admet/compound_evidence.jsonl"
})
```

Write one row per library ID with observed toxicity count, predicted alert count, unknown
status, endpoint, concentration/exposure context, applicability, rationale, and safety
score. Mark each compound `observed`, `predicted_only`, or `unknown`; an empty database
result is not low toxicity. Require matched lipid and viability readouts in the downstream
validation plan when a lipid phenotype is claimed.

## Standalone Command-Line Procedure

Run the prediction backend directly when no manifest is supplied, then join it with
observed evidence by the stable library or parent ID:

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
QIKPROP="${QIKPROP:-$SCHRODINGER/qikprop}"
INPUT_SDF="${INPUT_SDF:?LigPrep-prepared candidate SDF}"
OUT_DIR="${OUT_DIR:-admet}"
mkdir -p "$OUT_DIR"
"$QIKPROP" -fast -nosim -LOCAL -WAIT "$INPUT_SDF" > "$OUT_DIR/qikprop.log" 2>&1
```

Parse the QikProp output with its molecule identifier and keep predicted properties
separate from experimental toxicity records. A generic join must produce one row per
input ID with `observed`, `predicted_only`, or `unknown`, the endpoint and exposure
context, source/citation IDs, applicability, alert rationale, and a reproducible safety
score. Use `jq`, a CSV tool, or a small versioned Python/R script for the join; do not
classify a missing database result as safe and do not call a structural alert observed
cytotoxicity. Reject rows whose parent ID or structure hash cannot be matched.

## Pitfalls

- Spontaneous adverse-event counts do not establish compound-specific causality.
- Structural alerts and QikProp properties are predictions, not observed cell death.
- Lipid reduction accompanied by material viability loss is a likely false positive.

## Verification

Require one row per stable input ID, identity/hash match, evidence class, endpoint and exposure,
source/citation, applicability, observed/predicted/unknown label, alert rationale, uncertainty,
and a matched lipid/viability decision for phenotype nominations.
