---
name: admet
description: Use to route ADMET prediction and safety evidence.
---

# ADMET

Combine validated property prediction, compound evidence enrichment, and toxicity triage while
keeping experimental observations, predictions, and unknowns separate.

## When to Use

Use after a frozen candidate/library stage and before later docking refinement, nomination, or
experimental validation planning.

## Prerequisites

- Frozen structures with stable parent/library IDs and source hash.
- Declared ADMET backend, preparation-state policy, filters, applicability domain, and exact N.
- Evidence sources and toxicity schema that distinguish observations from predictions.

## How to Run

The agent defaults to the manifest-selected backend and child skills. Standalone mode invokes
the native prediction tool and joins its rows to explicit evidence and toxicity tables.

## Quick Reference

| Child skill | Purpose | Evidence class |
| --- | --- | --- |
| `ddfast-06-qikprop-admet` | LigPrep and QikProp | Prediction |
| `enrich-compound-evidence` | IDs, assays, literature | Curated/source evidence |
| `triage-compound-toxicity` | Safety hierarchy | Observed/predicted/unknown |
| Compatibility route | Preserve old stage names | Real backend identity |

## Procedure

1. Validate frozen input structures, IDs, count, and hash.
2. Prepare one declared state per parent and run the selected backend.
3. Parse numeric and missing rows without inventing values.
4. Enrich exact identities and triage toxicity by evidence level.
5. Apply frozen rules, report shortfalls, and freeze survivors with provenance.

This main skill owns H4 and the evidence-side E4/E5 review. It does not substitute a
Schrodinger or DrugFlow result with an LLM estimate.

## Child skills

- `funnel-drugflow-hepg2` for the configured ADMET route
- `ddfast-06-qikprop-admet` for Schrödinger QikProp compatibility
- `enrich-compound-evidence` for compound annotations and literature evidence
- `triage-compound-toxicity` for observed/predicted/unknown toxicity tiers

## Gate

Record backend, version, input count, observed output count, missing fields, filters, and
artifact validation. Unknown toxicity is not low toxicity. Only validated survivors proceed
to the next docking refinement stage.

## Universal Manifest Invocation

This skill works with any target, disease, compound library, and declared ADMET
backend. The caller supplies relative structure/data inputs, expected descriptor and
selection outputs, resources, validation rules, reporting location, and an explicit
argv `command` or ordered `steps`; unknown evidence is never converted to safety.

```bash
bash scripts/run_skill.sh --skill admet --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill admet --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill admet --manifest MANIFEST --status
```

Authorize only after checking backend identity, parent-state lineage, numeric fields,
and exact-N rules:

```bash
bash scripts/run_skill.sh --skill admet --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill admet --manifest MANIFEST --resume --execute --confirm
```

Place prediction tables, observed evidence, toxicity gaps, and reports below
`campaign_root`; retain failed rows and distinguish prediction from experiment.

## Concrete Operation Procedure

Start from the validated H3 exact-N SDF and preserve parent/library IDs:

```bash
masld-agent funnel validate --manifest "$MANIFEST" --stage H3
QIKPROP="$(masld-agent platform-resolve --id sz.bin.qikprop)"
LIGPREP="$(masld-agent platform-resolve --id sz.bin.ligprep)"
"$LIGPREP" -h; "$QIKPROP" -h
masld-agent funnel plan --final-count "$FINAL_COUNT" --profile full \
  --target-id "$TARGET_ID" > "$CAMPAIGN_ROOT/00_funnel_plan.json"
H4_TARGET="$(jq -r '.stage_targets.H4' "$CAMPAIGN_ROOT/00_funnel_plan.json")"
```

Run `ddfast-06-qikprop-admet` for numeric prediction, then call `enrich-compound-evidence`
and `triage-compound-toxicity` on the same frozen IDs. Require one parent-state mapping,
numeric QikProp rows, observed/predicted/unknown toxicity columns, exact-N validation, and
a report update before H5. QikProp predictions never become experimental HepG2 results.

## Standalone Command-Line Procedure

The shared ADMET route is still usable without a manifest: preserve the frozen H3 input,
run the native backend, then join predictions with evidence and toxicity tables.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  LIGPREP="${LIGPREP:-$(masld-agent platform-resolve --id sz.bin.ligprep)}"
  QIKPROP="${QIKPROP:-$(masld-agent platform-resolve --id sz.bin.qikprop)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
LIGPREP="${LIGPREP:-$SCHRODINGER/ligprep}"
QIKPROP="${QIKPROP:-$SCHRODINGER/qikprop}"
INPUT_SDF="$(realpath inputs/h3_frozen.sdf)"
OUT="$(realpath -m outputs/04_admet)"
mkdir -p "$OUT"
"$LIGPREP" -isd "$INPUT_SDF" -osd "$OUT/prepared.sdf" -epik -WAIT
"$QIKPROP" -fast -nosim -LOCAL -WAIT -outname "$OUT/qikprop" "$OUT/prepared.sdf"
```

Record backend/version, input/output counts, failed rows, prediction fields, observed
toxicity evidence, unknowns, and the exact selection rule. Never call QikProp a HepG2
experiment or treat a missing database record as low toxicity.

## Pitfalls

- QikProp predictions are not HepG2 viability or clinical safety observations.
- Unknown toxicity is not low toxicity, and a database miss is not reassuring evidence.
- Prepared states must map back to parents before exact-N selection.
- Do not replace a missing licensed backend with LLM, mock, or unrelated descriptor values.

## Verification

Require input/backend/version hashes, parent-state map, numeric and failed rows, applicability
and rule columns, observed/predicted/unknown toxicity labels, evidence IDs, deterministic
selection, exact-N table/SDF agreement, and a report that states all prediction limits.
