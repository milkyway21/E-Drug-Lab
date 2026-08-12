---
name: funnel-featurehit
description: Expand H3 hits from validated seed molecules using an explicitly named Morgan, Phase, or shape backend with deterministic lineage. Use after primary Glide SP selection; do not label topology similarity as pharmacophore evidence.
---

# FeatureHit

Set `stages.H3.backend` to `rdkit_morgan`, `schrodinger_phase`, or
`shape_only`. Do not call Morgan a pharmacophore result. For Morgan use radius 2,
2048 bits, deterministic Tanimoto sorting, and write query ID, library ID, score,
canonical SMILES, and backend to the output manifest.

Phase is allowed only after probing the installed 2023-3 CLI and verifying the
database and query formats. Failed Phase attempts must remain isolated and must not
be merged with valid hits.

## Detailed Generic Procedure

### Inputs

Declare `inputs.query_pose_sdf`, `inputs.library_sdf` or an approved library database,
`inputs.parent_manifest`, and output feature table, ranked hits, and exact-N manifest.
The query SDF contains ligand records extracted from real Glide poses, not a
protein-containing pose viewer file. Each query keeps `parent_id`, `pose_id`, `grid_id`,
and source path.

### Backend selection

- `rdkit_morgan`: parse every record, compute declared radius and bit length, take maximum
  Tanimoto over query poses, and sort score descending then stable ID.
- `schrodinger_phase`: verify installed Phase feature-generation and screening help,
  query/database formats, feature definition, and output property names with one real
  query. Record feature hypothesis and Phase version.
- `shape_only`: route to `funnel-shape-screen`; do not report a Shape score as a feature
  count or pharmacophore match.

Do not mix backend outputs before each has a complete ranked table. Invalid structures,
missing IDs, duplicate states, and score parse failures are rejection rows with reasons.

### Feature output contract

Each row contains `query_id`, `parent_id`, `library_id`, `canonical_smiles`, `backend`,
`backend_version`, `parameters`, `feature_or_similarity_score`, `rank`, `source_path`,
and `status`. The summary contains total, valid, invalid, duplicate, and exact-N counts.
Report pharmacophore interpretation only when the backend generated pharmacophore
features.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-featurehit --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-featurehit --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-featurehit --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-featurehit --manifest MANIFEST --resume --execute --confirm
```

The manifest explicitly supplies backend command, feature parameters, query/library paths,
resource limits, output schema, and reporting path. The launcher never chooses Morgan,
Phase, Shape, a target, or a hit threshold from the skill name.

## Concrete Operation Procedure

For a topology arm, use the bundled RDKit utility and preserve the winning query pose:

```bash
masld-agent funnel validate --manifest "$MANIFEST" --stage H2
mkdir -p "$CAMPAIGN_ROOT/03_h3"
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$QUERY_POSE_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --threshold "$MORGAN_THRESHOLD" \
  --output "$CAMPAIGN_ROOT/03_h3/morgan_hits.csv"
```

Use `rdkit_morgan` only for topology similarity. For a true feature/pharmacophore arm,
call the registered Phase command after a one-query help and format probe; record the
feature hypothesis, version, query IDs, library IDs, score field, and rejection rows.
Do not merge the arms until both ranked tables and their exact-N validation pass.

## Standalone Command-Line Procedure

For Morgan similarity, call the shared RDKit utility with an ordinary Python interpreter:

```bash
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
mkdir -p "$CAMPAIGN_ROOT/03_h3"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$QUERY_POSE_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --threshold "${MORGAN_THRESHOLD:-0.0}" \
  --output "$CAMPAIGN_ROOT/03_h3/morgan_hits.csv"
```

For a pharmacophore hypothesis already created and validated by Phase, screen the
library with the native Phase command. The `.phypo` file is an explicit input; this
command does not invent a hypothesis:

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
PHASE_SCREEN="${PHASE_SCREEN:-}"
if [ -z "${PHASE_SCREEN}" ] && command -v masld-agent >/dev/null 2>&1; then
  PHASE_SCREEN="$(masld-agent platform-resolve --id sz.bin.phase_screen)"
fi
PHASE_SCREEN="${PHASE_SCREEN:-$SCHRODINGER/phase_screen}"
"$PHASE_SCREEN" "$LIBRARY_SDF" "$HYPOTHESIS_PHYPO" "$CAMPAIGN_ROOT/03_h3/phase" \
  -distinct -keep "${HIT_CAP:-1000}" -osd -report 1
```

Parse the documented Phase score (`PHASE_SCREEN_SCORE`), keep stable library IDs and
winning query/hypothesis IDs, and keep Morgan, Phase, and Shape rankings separate until
the deterministic exact-N fusion. A Morgan score is topology similarity, not a feature
match.
