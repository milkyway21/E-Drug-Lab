---
name: "dd-md-desmond"
description: "Run Schrödinger Desmond MD on docked protein–ligand complexes (build → equilibrate → production), including pose-frame/corrected-pose rebuild and SEA decision triage. Invoke after Glide/Shape/IFD poses, when ligand is out of pocket / needs pose correction then MD, or when user asks MD—not FEP or DiffDynamic sampling."
---

⚠ Superseded note: for flowchart-track H work, prefer `funnel-desmond-short-md` / `funnel-desmond-long-md`. This skill holds cross-cutting MD operations knowledge.

# DD MD Desmond — Post-Docking Molecular Dynamics

Target-agnostic operator skill for Schrödinger Desmond stability MD.

For full content see the upstream HSD17B13_MD scripts directory and the
funnel-desmond-* skills. This skill carries supplementary references for
membrane-system builds and GPU-parallel launch patterns learned from
campaign work.

## Quick links

- `references/membrane-build-gpu-launch.md` — membrane system build QC
  checklist + multi-GPU parallel launch rules + launcher template.

## Key rules (also in the reference file)

1. **Reuse verified MSJ templates** — never hand-write a full protocol
   when a validated `prod_2ns_eq_50ns.msj` and `build_membrane_system.msj`
   exist in the campaign repo.
2. **Post-build composition QC is mandatory** — verify atom count,
   POPC/water/ion/NAD/ligand counts against reference before submitting
   production.
3. **Use standalone launcher scripts** — never submit MD via multi-line
   inline terminal commands (escaping bugs are common: backslashes
   treated as args, cd missing separators, etc.).
4. **Set both `CUDA_VISIBLE_DEVICES` AND `SCHRODINGER_CUDA_VISIBLE_DEVICES`**
   when assigning a GPU.
5. **Verify GPU placement ~30 s after launch** with `nvidia-smi` + log
   `JobId:` line.
