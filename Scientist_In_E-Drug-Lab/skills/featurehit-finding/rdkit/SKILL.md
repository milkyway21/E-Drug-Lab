---
name: rdkit
description: Perform reproducible local cheminformatics with RDKit, including structure parsing, canonicalization, physicochemical descriptors, Morgan similarity, and SMARTS filtering. Use for ligand-table preparation and library triage; do not substitute RDKit descriptors for QikProp, docking, or MD evidence.
---

# RDKit Cheminformatics

Prefer the bundled command-line utilities over one-off Python programs. Set
`SKILLS_ROOT` to the root of the installed shared skill tree and choose any Python
interpreter that has RDKit available; no repository-specific virtual environment is
required by this skill.

## Choose the existing utility

### Physicochemical properties

```bash
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/molecular_properties.py" \
  --file <input.smi-or-sdf> \
  --output <properties.csv>
```

Use for local 2D descriptors such as molecular weight, LogP, TPSA, hydrogen-bond
counts, rotatable bonds, and ring counts. These are identity and triage
features, not a replacement for the manifest-selected ADMET backend.

### Similarity screening

```bash
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  <query-smiles-or-file> <library.smi-or-sdf> \
  --method morgan --radius 2 --bits 2048 --metric tanimoto \
  --threshold <threshold> --output <hits.csv>
```

For campaign comparisons, freeze Morgan radius 2, 2048 bits, and Tanimoto unless
the manifest explicitly defines another method. Preserve query ID, library ID,
canonical SMILES, similarity, and source lineage. Apply a deterministic final
sort: similarity descending, then molecule ID ascending.

### Substructure filtering

```bash
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/substructure_filter.py" \
  <input.smi-or-sdf> \
  --exclude '<SMARTS>' \
  --output <filtered.sdf> \
  --report <filter_report.csv>
```

Use explicit SMARTS from the task specification or
[references/smarts_patterns.md](references/smarts_patterns.md). Record the
pattern, include/exclude mode, match count, parse failures, and output count.
Do not silently add medicinal-chemistry filters after selection rules are
frozen.

## Input and lineage rules

- Check every parsed molecule; RDKit suppliers can yield `None` for invalid
  records.
- Preserve the original record ID and source path before canonicalization.
- Keep invalid records in a rejection table with a reason; never silently drop
  them.
- Treat salts, stereochemistry, tautomers, and protonation according to the
  manifest. Canonical SMILES alone does not define a prepared 3D state.
- Read `.sdf.gz` as binary gzip data with a streaming supplier, or decompress it
  to a stage-local immutable input before using bundled utilities.
- Never overwrite the source library. Write derived files to the declared stage
  directory.

## Determinism and exact-N gates

- Record RDKit version and all fingerprint/filter parameters.
- Canonicalize before deduplication and retain a parent-to-record lineage table.
- Resolve ties with stable molecule IDs, not file iteration order.
- If fewer than the requested number satisfy frozen rules, stop at the gate and
  report the shortfall. Do not relax thresholds or duplicate molecules.
- Validate output row count, unique IDs, parse-success count, and exact-N count
  before downstream use.

## Extending existing behavior

Use the detailed API references only when no bundled utility covers the task:

- [references/api_reference.md](references/api_reference.md)
- [references/descriptors_reference.md](references/descriptors_reference.md)
- [references/smarts_patterns.md](references/smarts_patterns.md)

Prefer extending a project-owned reusable utility with a documented CLI and a
test over creating a task-local script. Keep chemistry policy in the manifest or
configuration, not as hidden constants in code.

Report after the stage: inputs, RDKit version, command/parameters, valid and
rejected counts, deduplication counts, exact-N status, and output paths.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill rdkit --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill rdkit --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill rdkit --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill rdkit --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies the existing utility command, input/output paths, descriptor or
fingerprint parameters, invalid-record policy, resource limits, and output validation.
For feature-hit work, record whether RDKit is used for topology similarity, physchem
triage, canonicalization, or SMARTS filtering. RDKit does not create a Schrödinger
pharmacophore hypothesis, docking pose, ADMET result, or MD conclusion.

## Concrete Operation Procedure

Run from the project root with the existing scripts; never replace them with an inline
Python snippet:

```bash
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
mkdir -p "$CAMPAIGN_ROOT/chemistry"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/molecular_properties.py" \
  --file "$INPUT_SDF" --output "$CAMPAIGN_ROOT/chemistry/properties.csv"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$QUERY_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --threshold "$THRESHOLD" \
  --output "$CAMPAIGN_ROOT/chemistry/morgan_hits.csv"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/substructure_filter.py" \
  "$INPUT_SDF" --exclude "$SMARTS" \
  --output "$CAMPAIGN_ROOT/chemistry/filtered.sdf" \
  --report "$CAMPAIGN_ROOT/chemistry/filter_report.csv"
```

Record RDKit version, parse failures, invalid records, SMARTS, threshold, fingerprint
parameters, canonicalization policy, and output counts. A shortfall is reported rather
than filled by duplicates or a silently relaxed threshold.

## Standalone Command-Line Procedure

The RDKit child is directly reusable when the shared skill tree and a Python environment
are supplied by the caller:

```bash
SKILLS_ROOT="${SKILLS_ROOT:?root of the installed shared skills}"
PYTHON="${PYTHON:-python3}"
INPUT_SDF="${INPUT_SDF:?input SDF}"
LIBRARY_SDF="${LIBRARY_SDF:?reference library SDF}"
OUT_DIR="${OUT_DIR:-rdkit}"
mkdir -p "$OUT_DIR"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/molecular_properties.py" \
  --file "$INPUT_SDF" --output "$OUT_DIR/properties.csv"
"$PYTHON" "$SKILLS_ROOT/featurehit-finding/rdkit/scripts/similarity_search.py" \
  "$INPUT_SDF" "$LIBRARY_SDF" --method morgan --radius 2 --bits 2048 \
  --metric tanimoto --threshold "${THRESHOLD:-0.7}" --output "$OUT_DIR/morgan_hits.csv"
```

Use the bundled `substructure_filter.py` for SMARTS exclusions, preserve parse failures,
and record RDKit version, fingerprint settings, threshold, canonicalization policy, and
input/output counts. Do not relax a threshold or fill a shortfall with duplicate records.
