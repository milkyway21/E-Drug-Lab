---
name: funnel-glide-sp
description: H2/H5 LigPrep and Glide SP with parent-state lineage and deterministic parent ranking.
---

# Glide SP

Use stage H2 for primary SP and H5 for refined SP. Reuse the manifest grid; do not
rebuild it when a validated ZIP already exists. Preserve `parent_id -> prepared_state`
mapping and rank each parent by numeric minimum `r_i_glide_gscore`.

Before execution inspect `$SCHRODINGER/ligprep -h` and `$SCHRODINGER/glide -h`.
Completion requires a non-empty CSV, readable pose viewer, numeric scores, and the
expected parent-level selection manifest.

Schrödinger 2023-3 non-interactive pitfall: a distributed Glide launch can stop at
an `existing job by this name` prompt even after changing the apparent job name.
Do not retry a full ligand set by renaming alone. First run one prepared-state probe
in an isolated task directory. The validated non-interactive pattern is to omit the
`JOBNAME` keyword from the Glide input, pass one unique CLI `-JOBNAME`, and add the
official `-OVERWRITE` startup flag. Require `ExitStatus: finished`, a success log,
and a real `_pv.maegz` before applying the same call to the frozen full input. Clear
project `PYTHONPATH` for Schrödinger tools when a custom `sitecustomize.py` shadows
Schrödinger's own module.

```bash
masld-agent funnel run --manifest MANIFEST --stage H2 --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H2
```
