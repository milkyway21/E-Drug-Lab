# E-Drug Lab platform knowledge

This file is **platform capability knowledge** for Scientist_In_E-Drug-Lab.
It does **not** change agent identity (see `config/SOUL.md`: cross-disease drug discovery).

## Three systems

| System | Role | Prefer invoke via |
|--------|------|-------------------|
| **DiffDynamic** | Pocket-conditioned molecule generation | e-drug-lab `DiffDynamicRunner` → conda `diffdynamic` |
| **e-drug-lab backend** | Service wrappers + Affinity APIs | Library import (HTTP optional / often down) |
| **Schrödinger** | PrepWizard / LigPrep / Grid / Glide / QikProp / MMGBSA / IFD | `schrodinger_service` → `/opt/schrodinger2023-3` |

Authoritative machine catalog: [`catalog.yaml`](catalog.yaml). Query with:

```bash
masld-agent platform-catalog
masld-agent platform-health
```

## Hard rules

1. **Never invent** docking scores, generated structures, or ADMET numbers.
2. **DiffDynamic input PDB** = original receptor (not PrepWizard mae). PrepWizard output is for Glide.
3. **Large jobs** (batch≥100, full Glide funnel) require explicit `confirm=true`.
4. **Do not** use `backend/app/api/integrations/*` remote stubs as production.
5. DDFast funnel order: gate → denovo/scaffold → extract novina → dedup → QikProp(MODERATE) → Glide SP → XP → MMGBSA/IFD → rank.
6. Schrödinger: absolute paths; LigPrep `-nt` ≠ threads; IFD **1:1 only** (no N×N).
7. GPU policy for DDFast sampling: prefer GPUs **1–5**, split seeds to avoid OOM.

## Quick env

```bash
# DiffDynamic
conda activate diffdynamic
export PYTHONPATH=/data/ye/DiffDynamic:$PYTHONPATH
cd /data/ye/DiffDynamic

# Schrödinger
export SCHRODINGER=/opt/schrodinger2023-3
# optional large temp:
# export SCHRODINGER_TEMPDIR=/data/.../schrodinger_tmp
```

## When unsure

Call `platform-catalog --id <id>` or `--system dd|ed|sz` before proposing commands.
