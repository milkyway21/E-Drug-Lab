---
name: "dd-md-desmond"
description: "Run or resume Schrödinger Desmond MD on docked protein-ligand complexes, including corrected-pose system preparation, production validation, and SEA routing. Use after validated docking poses or when diagnosing pose-frame MD failures; prefer funnel-desmond-short-md/long-md for H8/H9 and do not use for FEP or DiffDynamic sampling."
---

⚠ Superseded note: for flowchart-track H work, prefer `funnel-desmond-short-md` / `funnel-desmond-long-md`. This skill holds cross-cutting MD operations knowledge.

# DD MD Desmond — Post-Docking Molecular Dynamics

Target-agnostic operator skill for Schrödinger Desmond stability MD.

Use the funnel Desmond skills for stage policy and `desmond-md-campaign` for
portable implementation details. This skill carries supplementary guidance for
membrane-system builds and GPU-parallel launch patterns.

## Quick links

- [`desmond-membrane-md-ops`](../desmond-membrane-md-ops/SKILL.md) — membrane
  build QC and multi-GPU operational rules.

## Key rules (also in the reference file)

1. **Reuse verified MSJ templates** — never hand-write a full protocol
   when a validated `prod_2ns_eq_50ns.msj` and `build_membrane_system.msj`
   exist in the campaign repo.
2. **Post-build composition QC is mandatory** — verify manifest-declared
   protein/ligand/membrane/water/ion/cofactor counts or ranges before submitting
   production.
3. **Use standalone launcher scripts** — never submit MD via multi-line
   inline terminal commands (escaping bugs are common: backslashes
   treated as args, cd missing separators, etc.).
4. **Set both `CUDA_VISIBLE_DEVICES` AND `SCHRODINGER_CUDA_VISIBLE_DEVICES`**
   when assigning a GPU.
5. **Verify GPU placement ~30 s after launch** with `nvidia-smi` + log
   `JobId:` line.
