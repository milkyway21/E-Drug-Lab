# Campaign Contract

## Contents

1. Environment
2. Directory layout
3. Medoid input CSV
4. Selection manifest
5. Queue state
6. Completion criteria
7. Analysis outputs

## Environment

- Run Desmond and Schrodinger API code with `$SCHRODINGER/run python3`.
- Use a large local `SCHRODINGER_TEMPDIR` for production and SEA scratch data.
- Do not use conda for Desmond. RDKit-only selection steps may use an existing chemistry environment when needed.

## Directory Layout

```text
<campaign-root>/
├── 03_systems/<batch>/<molecule_id>/<molecule_id>-out.cms
├── 04_trajectories/<batch>/<molecule_id>/attempt_XX/
│   ├── state.json
│   ├── attempt_validation.json
│   ├── <molecule_id>_202ns-out.cms
│   └── *_6_trj/
├── 05_analysis/<batch>/
│   ├── selection_manifest.csv
│   ├── md_queue_status.csv
│   ├── sea/<molecule_id>/
│   └── final_200ns/
└── logs/<batch>/
```

Use a new batch name for a new coordinate frame, protocol, candidate set, or production length.

## Medoid Input CSV

Required columns:

| Column | Meaning |
|---|---|
| `molecule_id` | Stable unique ID |
| `source_cms` | Full-system final CMS matching the source DTR |
| `source_trajectory` | Source production DTR directory containing `clickme.dtr` |
| `pocket_asl` | Target-pocket atom selection; may instead be supplied globally |

Optional verification columns:

| Column | Meaning |
|---|---|
| `planned_medoid_time_ns` | Expected medoid time; enforce within one source frame interval |
| `expected_cluster_fraction` | Expected dominant late-cluster fraction |

The extractor fits target-pocket C-alpha atoms, clusters aligned ligand-heavy coordinates by average linkage, uses a 2.0 A default cutoff, selects the dominant-cluster medoid, and writes the complete selected frame.

## Selection Manifest

For unified analysis, include at least:

```text
molecule_id,smiles,pose_xp,mmgbsa
```

Recommended additional fields include source CMS/DTR, medoid time, dominant-cluster fraction, atom/component counts, formal charge, atom and force-field fingerprints, box matrix, clash count, pocket distance, Murcko scaffold, and maximum pairwise Morgan similarity.

## Queue State

Each `attempt_XX/state.json` should record molecule ID, attempt number, GPU ID, job name/ID, submit time, last-seen time, and last progress size/time. Keep queue status in a single CSV written atomically.

Use deterministic retry order and at most three attempts unless the user changes policy. Do not reuse an attempt directory.

## Completion Criteria

A 200 ns production job is valid only when all conditions pass:

- Multisim completed successfully.
- Final CMS exists, is readable, and is not a tiny placeholder.
- DTR is readable and has strictly increasing finite times.
- Coverage is at least 199.998 ns for a requested 200 ns run.
- Expected 200 ps output normally gives at least 1001 frames.
- Maximum frame gap is no more than the configured tolerance, normally 250.5 ps.
- Final-frame `topo.check_consistency` passes.
- Box matrix is finite and non-singular.

The old shorthand threshold of 190 ns is not a completion criterion.

## Analysis Outputs

Required decision outputs:

- `md200_decision_table.csv` and `.xlsx`
- `md200_traces.csv`
- `md200_contacts.csv`
- `md200_transitions.csv`
- per-molecule reports and representative structures
- combined RMSD figure and publication plate

Use the final 50 ns as the primary decision window for a 200 ns trajectory. Flag transitions after 180 ns as insufficiently sampled rather than declaring a stable final pose.
