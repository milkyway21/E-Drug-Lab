---
name: rdkit
description: Perform reproducible local cheminformatics with RDKit, including structure parsing, canonicalization, physicochemical descriptors, Morgan similarity, and SMARTS filtering. Use for ligand-table preparation and library triage; do not substitute RDKit descriptors for QikProp, docking, or MD evidence.
---

# RDKit Cheminformatics

Prefer the bundled command-line utilities over one-off Python programs. Run
them with the project's existing Python environment from the repository root.

## Choose the existing utility

### Physicochemical properties

```bash
.venv/bin/python skills/rdkit/scripts/molecular_properties.py \
  --file <input.smi-or-sdf> \
  --output <properties.csv>
```

Use for local 2D descriptors such as molecular weight, LogP, TPSA, hydrogen-bond
counts, rotatable bonds, and ring counts. These are identity and triage
features, not a replacement for the manifest-selected ADMET backend.

### Similarity screening

```bash
.venv/bin/python skills/rdkit/scripts/similarity_search.py \
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
.venv/bin/python skills/rdkit/scripts/substructure_filter.py \
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
