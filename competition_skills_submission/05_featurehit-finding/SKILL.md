---
name: featurehit-finding
description: Use to route pose-seeded compound-library expansion.
---

# FeatureHit Finding

Route topology, pharmacophore, and three-dimensional shape searches from validated ligand poses
to a frozen, lineage-complete library hit set.

## When to Use

Use after primary Glide pose selection when a fixed compound library must be searched for
topologically, pharmacophorically, or shape-related candidates.

## Prerequisites

- Ligand-only query poses with parent, prepared-state, pose, grid, and score lineage.
- Immutable source library with stable IDs, record count, and hash.
- Explicit backend, score semantics, exact-N policy, resources, and output directory.

## How to Run

Use the manifest to coordinate selected child backends. Standalone work calls the native
RDKit, Phase, QuickShape, or GPU Shape path appropriate to the declared evidence type.

## Quick Reference

| Evidence arm | Backend | Score meaning |
| --- | --- | --- |
| Topology | RDKit Morgan | Fingerprint Tanimoto |
| Pharmacophore | Phase screen | Hypothesis match score |
| 3D shape | QuickShape or Shape GPU | Shape similarity |
| Fusion | Deterministic exact-N policy | Selection provenance |

## Procedure

1. Extract and validate ligand-only best poses from the pose viewer.
2. Freeze library identity and probe the exact installed backend and format.
3. Run each evidence arm independently and preserve invalid/rejected records.
4. Aggregate best score per stable library ID and canonical structure.
5. Fuse under the declared policy and validate exact-N rows and structures.

This main skill coordinates H3 without replacing the exact-N validators or plot recipes.

## Child skills

- `funnel-featurehit` for topology/pharmacophore feature generation
- `funnel-shape-screen` for pose-based Shape screening
- `pose-library-screening` for library comparison and exact-N selection
- `rdkit` for structure parsing, descriptors, deduplication, and fingerprints

## Gate

Keep generated-parent, pose, library, and selected-hit IDs linked. Report observed counts,
similarity/feature criteria, excluded structures, and all figures before moving to ADMET.
Use only current-task library outputs and preserve relative provenance.

## Universal Manifest Invocation

This skill is library- and target-neutral. The manifest must identify the current
task and declare pose/query/library inputs, expected hit and feature outputs,
resource limits, validation rules, reporting location, and an explicit argv
`command` or ordered `steps`; it must not rely on hidden project paths or counts.

```bash
bash scripts/run_skill.sh --skill featurehit-finding --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill featurehit-finding --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill featurehit-finding --manifest MANIFEST --status
```

After inspecting the query format and exact-count policy, authorize the run:

```bash
bash scripts/run_skill.sh --skill featurehit-finding --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill featurehit-finding --manifest MANIFEST --resume --execute --confirm
```

Keep generated-parent, pose, feature, library, and selected-hit IDs traceable under
`campaign_root`; a wrapper completion message does not replace artifact validation.

## Generic H3 Method

H3 has two independent evidence arms. The topology arm uses RDKit Morgan fingerprints;
the 3D arm uses Schrödinger Shape or an explicitly named Phase backend. A Morgan score
must never be written as a pharmacophore score. Both arms preserve query pose, parent
compound, library ID, backend, parameters, and source file before exact-N fusion.

The sequence is: extract real ligand-only Glide poses, freeze one best pose per parent,
validate library records, probe the installed backend, run a one-pose smoke screen, run
the frozen full screen, parse and deduplicate hits, fuse arms under the manifest policy,
and validate the exact-N output. Shape and Phase outputs are ranking evidence, not
experimental activity evidence.

The H3 handoff includes query pose count, valid/invalid library count, backend and version,
feature parameters, score distributions, rejected records, exact-N selection order,
canonical SMILES, and relative figure/report paths. If a backend cannot read the declared
format, stop and use an existing supported utility rather than renaming files or silently
changing method.

## Concrete Operation Procedure

Start H3 from validated ligand-only poses, not a receptor-containing pose viewer:

```bash
masld-agent funnel validate --manifest "$MANIFEST" --stage H2
SHAPE="$(masld-agent platform-resolve --id sz.bin.quick_shape)"
SHAPE_GPU="$(masld-agent platform-resolve --id sz.bin.shape_screen_gpu)"
ONED="$(masld-agent platform-resolve --id sz.bin.oned_screen)"
"$SHAPE" -h; "$SHAPE_GPU" -h; "$ONED" -h
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$QUERY_POSE_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --output "$CAMPAIGN_ROOT/03_h3/morgan_hits.csv"
```

Extract one best pose per frozen parent into `QUERY_POSE_SDF`, then run the Shape arm
with the registered QuickShape/Phase executable appropriate to the database extension.
Keep Morgan and Shape tables separate until deterministic exact-N fusion. Validate query
count, library valid/invalid count, score columns, canonical uniqueness, and parent IDs;
only the frozen exact-N SDF advances to ADMET.

## Standalone Command-Line Procedure

The shared workflow can be run without a manifest: extract ligand-only query poses, choose
one native screening arm, and preserve each arm's source and score semantics. Use the
commands in `funnel-featurehit` for RDKit/Phase and `funnel-shape-screen` for Shape; the
minimum public contract is:

```bash
test -s "$QUERY_POSE_SDF" && test -s "$LIBRARY_SDF"
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$QUERY_POSE_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --output "$CAMPAIGN_ROOT/03_h3/morgan_hits.csv"
```

Only merge ranked tables after parsing valid records, preserving query/parent/library
lineage, and applying the declared exact-N policy.

## Pitfalls

- Morgan topology similarity is not a pharmacophore or 3D-shape result.
- A receptor-containing pose viewer is not a ligand query file.
- `.1dbin` and GPU `.bin` databases are not interchangeable by renaming or symlinking.
- Query records and prepared states can inflate output counts unless explicitly removed.

## Verification

Require query and library hashes/counts, backend versions and parameters, score columns,
JobDJ completion where applicable, invalid/rejection rows, stable query-parent-library joins,
canonical uniqueness, and exact agreement between frozen manifest rows and SDF records.
