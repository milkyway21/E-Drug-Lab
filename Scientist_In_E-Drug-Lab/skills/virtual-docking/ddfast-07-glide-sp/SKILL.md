---
name: ddfast-07-glide-sp
description: Compatibility alias for single-receptor LigPrep and Glide SP after QikProp filtering. Use only when an existing task names ddfast-07; route new H2/H5 work to funnel-glide-sp and never use this alias for multi-receptor or HSV workflows.
---

# DDFast 07 Glide SP Compatibility

Use `funnel-glide-sp` for all new work. Keep this skill only to resume manifests that
already identify the stage as `ddfast-07-glide-sp`.

## Resume Contract

1. Read the manifest and run `masld-agent funnel validate` before computing.
2. Reuse the manifest-declared prepared receptor and grid; do not rebuild validated
   inputs merely because a wrapper failed.
3. Preserve parent-to-prepared-state lineage through LigPrep and rank each parent by
   its numeric minimum `r_i_glide_gscore`.
4. For non-interactive Schrödinger 2023-3 Glide, omit `JOBNAME` from the input,
   provide one CLI `-JOBNAME`, and include `-OVERWRITE`.
5. Require a finished log, readable pose viewer, numeric score table, and exact-N
   parent manifest before marking completion.

```bash
masld-agent funnel run --manifest MANIFEST --stage H2
masld-agent funnel run --manifest MANIFEST --stage H2 --execute --confirm
masld-agent funnel validate --manifest MANIFEST --stage H2
```

Capability catalog IDs: `sz.prepwizard`, `sz.ligprep`, `sz.grid`, `sz.glide_sp`,
and `ed.svc.schrodinger`.
