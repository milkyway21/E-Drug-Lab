---
name: funnel-diffdynamic-denovo
description: Run H1a DiffDynamic pocket-conditioned de novo generation through a reusable manifest-configured runner with strict clean receptor PDB and native ligand SDF inputs. Use when the selected profile enables the de novo branch; do not create a task-local launcher.
---

# H1a DiffDynamic De Novo

Use the coordinate-cleaned receptor PDB from E2b, not the untouched complex and not
PrepWizard output. `inputs.receptor_pdb` must end in `.pdb` and
`inputs.reference_ligand_sdf` must end in `.sdf`; resolve both from
`structure_preparation_manifest.json.diffdynamic_input`. CIF/mmCIF, PDB ligand files,
MOL2, MAE, and MAEGZ are hard-gated. Confirm the receptor excludes water and the selected
ligand while retaining explicitly required metals/cofactors.

Configure `stages.H1A.command`
as an argv list pointing to an existing DiffDynamic runner; set `cwd` and environment
in the manifest instead of writing a new launcher.

```bash
masld-agent funnel run --manifest MANIFEST --stage H1A
masld-agent funnel run --manifest MANIFEST --stage H1A --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H1A
```

The expected evidence is a non-empty `result_*.pt` or a manifest-declared output.
Keep every retry under `logs/funnel/H1A/attempt_XX`; never overwrite an older run.
