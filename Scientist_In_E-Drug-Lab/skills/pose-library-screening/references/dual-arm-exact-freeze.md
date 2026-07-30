# Dual-arm Morgan + QuickShape exact-N freeze

Use this recipe when a frozen pose set searches a fixed SDF/Phase library through a
2D topology arm and a 1D/3D Shape arm.

## Identity and lineage

Library SDF titles may be blank even when a stable property such as `ID` exists.
Use the stable library property as `library_id`; keep the original 1-based record
index as a second lineage key. Do not promote generated LigPrep titles or aligned
Shape-state titles to final compound IDs.

Freeze query lineage before screening:

- parent ID;
- prepared-state/pose ID;
- docking score and rank;
- query index used by each similarity backend;
- source grid and pose-viewer path.

## Morgan arm

Recommended explicit provenance fields:

```text
backend=rdkit_morgan
radius=2
n_bits=2048
aggregation=max Tanimoto over frozen query poses
```

For every valid library structure, write:

```text
morgan_rank, library_index, library_id, canonical_smiles,
morgan_best_similarity, morgan_query_index
```

Count invalid SDF records and preserve the evidence. `library_valid < library_total`
is acceptable only when the difference is reported and the final exact set is drawn
from valid current-library structures.

## QuickShape arm

Read SDFGZ with `gzip.open(path, "rb")` and RDKit
`ForwardSDMolSupplier`. Then:

1. skip query records or any record without numeric `r_phase_Shape_Sim`;
2. map hit title/property back to `library_id`;
3. retain the best Shape score per library ID across conformers/states/queries;
4. record `shape_rank`, `shape_similarity`, and the winning Shape query ID;
5. use the original library molecule for final output, not the aligned state.

`-best` chooses the best query per screened structure but does not guarantee only one
protonation/stereo state per library ID; perform ID-level reduction explicitly.

## Deterministic no-weight-specified fusion

When the user requests both arms but gives no score weighting, use alternating rank
fusion with deterministic backfill:

```text
Morgan rank 1, Shape rank 1, Morgan rank 2, Shape rank 2, ...
```

At each candidate:

- reject an already selected `library_id`;
- reject an already selected canonical structure;
- stable-tie-break each arm by library ID and source index;
- if overlap/exhaustion prevents N, continue down the other arm;
- fail closed if exact N cannot be reached.

This is a diversity-preserving merge policy, not a calibrated biological score.
Record the policy in the manifest.

## Exact-N manifest schema

Minimum columns:

```text
selection_order
library_id
canonical_smiles
selection_arm
morgan_rank
morgan_best_similarity
morgan_query_index
shape_rank
shape_similarity
shape_query_id
source_library_index
feature_backend
shape_backend
```

## Hard validation

PASS requires all of:

- manifest data rows exactly N;
- output SDF readable records exactly N;
- unique library IDs exactly N;
- unique canonical structures exactly N;
- every selected ID found in the current frozen library;
- backend and query provenance present;
- no plan count presented as a completed count.

Report stage completion as:

```text
planned N; completed N; validation PASS/FAIL;
valid/invalid library counts; arm contribution counts;
key relative paths; next stage.
```

Similarity and Shape scores are computational ranking evidence, not experimental
activity or target inhibition.
