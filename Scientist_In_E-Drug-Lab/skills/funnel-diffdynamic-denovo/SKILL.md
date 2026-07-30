---
name: funnel-diffdynamic-denovo
description: H1a DiffDynamic pocket-conditioned de novo generation through a reusable campaign runner.
---

# H1a DiffDynamic De Novo

Use the original receptor PDB, not PrepWizard output. Configure `stages.H1A.command`
as an argv list pointing to an existing DiffDynamic runner; set `cwd` and environment
in the manifest instead of writing a new launcher.

```bash
masld-agent funnel run --manifest MANIFEST --stage H1A
masld-agent funnel run --manifest MANIFEST --stage H1A --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H1A
```

The expected evidence is a non-empty `result_*.pt` or a manifest-declared output.
Keep every retry under `logs/funnel/H1A/attempt_XX`; never overwrite an older run.
