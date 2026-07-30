---
name: ddfast-07-glide-sp
description: >-
  Single-system Schrodinger PrepWizard, grid generation, LigPrep, and Glide SP
  on ADMET-pass ligands. Invoke after ddfast-06; one receptor only (not HSV
  four-mutant).
catalog_refs:
  - sz.prepwizard
  - sz.ligprep
  - sz.grid
  - sz.glide_sp
  - ed.svc.schrodinger
---


---

## ⚠ Superseded（《整体流程图_三轮理解》重命名）

流程图对齐 skill 请改用：**funnel-glide-sp**。
映射表：`hsvpol/.trae/skills/FUNNEL_SKILL_MAP.md`。
本文件保留作兼容别名，新编排勿再点名本 skill 作为主入口。

# DDFast 07 Glide SP (Single System)

## Prerequisite

`logs/.done_ddfast_06` → `admet/admet_pass_sp_input.sdf`; receptor from `inputs/manifest.json`.

## Env

```bash
export SCHRODINGER=/opt/schrodinger2023-3
export SCHRODINGER_TEMPDIR=<large_disk>/schrodinger_tmp
```

## Do

1. PrepWizard on receptor → `glide/receptor_prep.mae`.
2. Compute `GRID_CENTER` from ligand/pocket coords (**recalculate**; never copy HSV centers).
3. Generate grid → `glide/grid/<TARGET>_grid.zip`.
4. LigPrep on ADMET-pass SDF → `glide/sp/ligprep-out.maegz`.
5. Glide SP (`PRECISION SP`) with high `NJOBS` within machine core budget.
6. Collect CSV with `title`, `r_i_glide_gscore` → `glide/sp/sp_results.csv` (sort ascending = better).
7. Touch `logs/.done_ddfast_07`

## Do not

- Run four mutant systems (WT/N815S/…) unless user explicitly expands scope
- Start XP before SP finishes and is ranked

## Reference patterns

- Prep/grid scripts under `hsvpol/mmgbsa_4systems/scripts/` (adapt to **one** system)
- SP shard runners under `hsvpol/merged_library/shape_screen_unique100/scripts/16*.sh` (optional for large libs)

## Next

`ddfast-08-glide-xp`
