---
name: pose-library-screening
description: Use to fuse reproducible pose-seeded library screens.
---

# Pose-Seeded Library Screening

Coordinate independent topology and three-dimensional screening arms, recover asynchronous
jobs, and freeze an exact-N source-library set with complete query and parent lineage.

## When to Use

Use after validated docking-pose extraction when multiple similarity arms must be compared or
fused into a deterministic library expansion.

## Prerequisites

- Frozen ligand-only poses and parent/pose selection table.
- Immutable library with stable IDs, original structures, count, and hash.
- Selected backends, resource policy, hit caps, fusion rule, and exact-N target.

## How to Run

Use the manifest as the orchestration default. Standalone users extract query poses, run each
native backend separately, and apply the same stable-ID fusion and validation contract.

## Quick Reference

| Task | Preferred operation | Evidence retained |
| --- | --- | --- |
| Query freeze | Best numeric Glide pose per parent | Parent/state/pose/grid |
| Topology arm | Morgan fingerprint | Similarity and winning query |
| Shape arm | Native Shape route by format | Similarity and aligned hit |
| Final freeze | Stable alternating/rank fusion | Arm and selection order |

## Procedure

1. Extract ligand-only query records and validate their lineage.
2. Freeze and validate the original source library.
3. Run each backend independently with one real-input probe first.
4. Recover, parse, aggregate, and deduplicate each ranked arm.
5. Fuse deterministically and retrieve final structures from the original library.

## Concrete Operation Procedure

Freeze queries and library identity before choosing a screening arm:

```bash
masld-agent funnel validate --manifest "$MANIFEST" --stage H2
SHAPE="$(masld-agent platform-resolve --id sz.bin.quick_shape)"
SHAPE_GPU="$(masld-agent platform-resolve --id sz.bin.shape_screen_gpu)"
ONED="$(masld-agent platform-resolve --id sz.bin.oned_screen)"
JOBCONTROL="$(masld-agent platform-resolve --id sz.bin.jobcontrol)"
"$SHAPE" -h; "$SHAPE_GPU" -h; "$ONED" -h; "$JOBCONTROL" -h
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$QUERY_POSE_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --output "$CAMPAIGN_ROOT/03_h3/morgan_hits.csv"
```

Use QuickShape for `.1dbin`, the registered GPU tool for `.bin`, and keep the two ranked
arms separate until fusion. Treat Job Control submission as incomplete until the exact
job finishes and Shape scores parse. Deduplicate by official library ID and canonical
structure, then write exactly the planned H3 rows and SDF records. Preserve query parent,
pose, source-library index, backend parameters, and rejection counts for ADMET.

Use this skill when real docked poses seed a fixed compound-library search and the
result must be frozen to an auditable exact-N set. It covers 2D Morgan/FeatureHit,
Schrödinger Shape routes, parent/state lineage, asynchronous JobDJ handling, and
resume-first recovery. It is target-agnostic.

## Relationship to funnel skills

This is the class-level execution umbrella for pose-seeded library screening. Keep
`funnel-featurehit` and `funnel-shape-screen` as H3 stage entrypoints and use
`funnel-glide-sp` for the upstream docking gate; those skills should delegate the
cross-target mechanics, probes, JobDJ recovery, and exact-N fusion here rather than
copying session-specific recipes. It does not replace the funnel orchestrator or
campaign-memory flush rules.

## Operating contract

1. Freeze real query poses and their parent lineage before searching the library.
   A pose-viewer receptor record is not a ligand query; extract ligand records only.
2. Treat requested counts as targets until artifacts pass hard validation.
3. Reuse completed upstream artifacts. If a later wrapper fails, do not rerun
   generation, LigPrep, docking, Morgan, or Shape merely to make the wrapper green.
4. Keep products under the manifest's numbered task directories. Job-control scratch
   may be elsewhere, but recovered scientific outputs must be moved back and recorded.
5. For long jobs, inspect runner reports and job logs at roughly 300-second intervals.
   Do not restart the current job while it is active.
6. After each stage report planned count, observed count, validation, key relative
   paths, and the next step; then continue automatically unless a hard gate fails.
7. After two same-class CLI/argument failures, stop blind parameter edits. Inspect
   official help and run one minimal real-input probe before returning to the full set.

## 1. Freeze and validate query poses

- Rank numeric Glide scores ascending; more negative is better.
- Select one best state/pose per frozen parent, preserving parent ID, state ID, source
  row, score, receptor grid, and pose-viewer path.
- Verify the exact number of ligand poses independently of file non-emptiness.
- Convert only the ligand records to the query format needed by the screening backend.
- If library SDF titles are blank, use a stable library property such as `ID`; never
  silently substitute transient LigPrep titles as the final compound identity.

## 2. Route by library format and backend

### Morgan / FeatureHit arm

Use RDKit Morgan fingerprints with explicit, recorded parameters. A robust default
for pose-seeded topology similarity is radius 2 and 2048 bits. For each library
compound, retain the maximum Tanimoto over all query poses and the winning query ID.
Record invalid structures rather than dropping them silently. Morgan is a topology
similarity backend, not a pharmacophore engine.

### Schrödinger Shape arm

- `shape_screen_gpu generate` produces `.bin`; screen that format with
  `shape_screen_gpu run`.
- Phase 1D databases use `.1dbin`; screen them with `oned_screen` or `quick_shape`.
  Do not rename `.1dbin` to `.bin`, create an extension-only symlink, or blindly
  decompress it for `shape_screen_gpu`.
- Use `quick_shape` when the task requires a 1D topology prefilter followed by true
  3D Shape alignment. Record both the 1D and 3D backends.
- Under Schrödinger 2023-3, do not pass `-osd` and `-ocsv` together.

Before a full screen, probe the exact installed CLI and run one real ligand pose with
small `keep/reduce` caps. Require numeric `r_phase_Shape_Sim` in the returned hits.

## 3. Schrödinger JobDJ completion and recovery

A launcher exit code of zero or a printed `JobId:` means submitted, not completed.
Parse the exact job ID and wait with the official interface:

`"$JOBCONTROL" -wait -int 300 <job_id>` after resolving `sz.bin.jobcontrol`.

Completion requires all of:

- parent job finished successfully;
- expected subjobs completed normally;
- final success marker in the program log;
- readable, non-empty output with the expected properties/record count.

Set the launch CWD to the intended numbered output directory before submission.
Schrödinger restores outputs to the launch CWD, not to a location inferred from a
wrapper's log path. If the job succeeded but the wrapper checked the wrong location,
use `jobcontrol -show` and `jobcontrol -files`, move only that task's recovered files
into the manifest directory, and resume from parsing/freezing without resubmitting.

For distributed Glide name prompts, do not repeatedly change names on the full set.
First probe one prepared ligand. A validated non-interactive pattern is to omit the
`JOBNAME` keyword from the Glide input, pass one CLI `-JOBNAME`, and use the official
`-OVERWRITE` startup flag. Preserve successful LigPrep artifacts.

If a project-level custom `sitecustomize.py` shadows Schrödinger's Python modules,
clear `PYTHONPATH` only for Schrödinger subprocesses and re-run the capability probe;
do not encode the contaminated path as a permanent rule.

## 4. Parse Shape output honestly

Read `.sdfgz` through gzip binary decompression. QuickShape output may contain query
records plus hits and may contain several protonation/stereo states for one library
ID. For hit ranking:

1. skip records without numeric `r_phase_Shape_Sim`;
2. map every hit back to the frozen library ID;
3. retain the best Shape score per library ID;
4. retain the winning Shape query ID;
5. canonical-deduplicate before exact-N selection.

Do not infer the hit count from total SDFGZ records without subtracting/query-filtering
query records.

## 5. Deterministic dual-arm exact-N freeze

Keep the Morgan and Shape arms separate until both have auditable ranked tables. A
reasonable no-weight-specified policy is alternating rank fusion with deterministic
backfill:

1. sort each arm by its native score and stable library-ID tie-break;
2. alternate Morgan and Shape candidates;
3. reject duplicate library IDs and duplicate canonical structures;
4. if one arm is exhausted or overlaps, backfill from the other in rank order;
5. fetch the final structures from the original frozen library, not aligned Shape
   states from another task;
6. stop unless manifest rows, readable SDF records, unique IDs, and unique canonical
   structures all equal N.

The exact-N manifest should include selection order, library ID, canonical SMILES,
selection arm, Morgan rank/similarity/query, Shape rank/similarity/query, source
library index, and backend provenance.

## 6. Verification and reporting

Hard validation should cover:

- query pose count and parent uniqueness;
- total library records, valid records, and invalid-record evidence;
- backend identity and parameter provenance;
- JobDJ parent/subjob completion;
- output record semantics, not just file size;
- exact-N manifest rows and exact-N readable SDF records;
- ID uniqueness and canonical uniqueness;
- proof that every frozen structure came from the current task's frozen library.

Computational similarity, GlideScore, and Shape similarity are ranking evidence only;
they are not experimental activity or target-inhibition proof.

For funnel tasks, pass the validated exact-N counts, backend provenance, and real Shape/Morgan
figures to `reporting`. The aggregate report receives one H3 section; the existing exact-N
manifest and JobDJ logs remain the authoritative evidence.

Hand the exact-N library manifest to `enrich-compound-evidence`. Preserve official library
ID and parent InChIKey so E4 can join PubChem, ChEMBL, literature, QikProp, docking, and MD
without using raw SMILES as the only key.

## References

- `references/schrodinger-jobdj-recovery.md` — minimal probes, asynchronous wait,
  non-interactive Glide, output-CWD recovery, and resume rules.
- `references/dual-arm-exact-freeze.md` — Morgan/QuickShape parsing and exact-N fusion
  schema/checklist.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill pose-library-screening --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill pose-library-screening --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill pose-library-screening --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill pose-library-screening --manifest MANIFEST --resume --execute --confirm
```

The manifest explicitly names frozen query poses, source library, backend arm(s), output
schema, exact-N policy, CPU/GPU resources, and report path. It must declare whether the
3D arm is `shape_screen_gpu`, `quick_shape`, or another installed Phase-compatible tool;
the skill never infers that choice from a file extension alone.

## Pitfalls

- Do not fetch final structures from aligned Shape states instead of the frozen source library.
- Do not infer successful completion from wrapper exit or JobDJ submission.
- Do not resolve score ties from file iteration order.
- Do not backfill an exact-N shortfall by duplicating structures or changing frozen thresholds.

## Verification

Confirm one query per parent, library count/hash, backend probes and versions, JobDJ completion,
per-arm score semantics, invalid/query-record exclusions, unique IDs and canonical structures,
selection order, and exact equality among target N, manifest rows, and source-derived SDF records.

## Standalone Command-Line Procedure

First extract ligand-only queries from the Glide pose viewer. A PV file contains receptor
and ligand atoms, so `structconvert` alone is not a sufficient extraction step. Use
`structsubset` to select records when needed, then the bundled generic Schrödinger Python
script to select ligand atoms by an explicit ASL and preserve pose properties.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
RUN="${RUN:-}"
STRUCTSUBSET="${STRUCTSUBSET:-}"
STRUCTCONVERT="${STRUCTCONVERT:-}"
if command -v masld-agent >/dev/null 2>&1; then
  RUN="${RUN:-$(masld-agent platform-resolve --id sz.bin.run)}"
  STRUCTSUBSET="${STRUCTSUBSET:-$(masld-agent platform-resolve --id sz.bin.structsubset)}"
  STRUCTCONVERT="${STRUCTCONVERT:-$(masld-agent platform-resolve --id sz.bin.structconvert)}"
fi
RUN="${RUN:-$SCHRODINGER/run}"
STRUCTSUBSET="${STRUCTSUBSET:-$SCHRODINGER/utilities/structsubset}"
STRUCTCONVERT="${STRUCTCONVERT:-$SCHRODINGER/utilities/structconvert}"
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
POSE_VIEWER="$(realpath inputs/glide_pv.maegz)"
OUT="$(realpath -m outputs/03_h3/queries)"
mkdir -p "$OUT"
SELECTED="$POSE_VIEWER"
if [ -n "${POSE_RECORDS:-}" ]; then
  SELECTED="$OUT/selected_records.maegz"
  "$STRUCTSUBSET" "$POSE_VIEWER" "$SELECTED" -n "$POSE_RECORDS"
fi
"$RUN" python3 \
  "$SKILLS_ROOT/featurehit-finding/pose-library-screening/scripts/extract_ligand_records.py" \
  --input "$SELECTED" \
  --output "$OUT/query_ligands.sdf" \
  --ligand-asl "${LIGAND_ASL:?explicit ligand ASL, for example a residue or property selector}" \
  --summary "$OUT/query_ligands.summary.json"
```

If no record subset is required, pass the PV directly to the extractor and omit the
`structsubset`/`structconvert` probe. The output summary must show the number of records
seen, written, and rejected. Verify ligand atom count, non-empty 3D coordinates, parent
ID/pose ID properties, and one query per frozen parent before Morgan, Phase, or Shape.

For a topology arm use the shared RDKit utility; for a `.1dbin` use QuickShape or
`oned_screen`; for a `.bin` use `shape_screen_gpu run`. Keep each ranked table separate
until exact-N fusion and retrieve final structures from the original frozen library.
