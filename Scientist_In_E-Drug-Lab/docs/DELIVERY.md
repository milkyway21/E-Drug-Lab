# Delivery notes

## Implemented

- `src/masld_agent` full offline E2E + CLI
- Pydantic models, scoring, HTTP cache
- Tools: competition, literature, uniprot, open_targets, pdb, pubchem, chembl, rdkit_eval, docking, ai4s_brief
- Platform adapters: `masld_agent.platform` + `config/platform/{PLATFORM.md,catalog.yaml}`
  (DiffDynamic / e-drug-lab / Schrödinger catalog, health, gated CLI/MCP/Hermes tools)
- AI4S submission helpers: Top10 CSV template, dual-readout lint, validate, HepG2 plan, pack zip
- Hermes plugin entry + Skill + MCP server module (brief / validate / pack + platform tools)
- Docker / compose / docs
- Fixtures: HSD17B13, KHK
- Official brief cache: `config/briefs/life_zh.md`

## Identity

- Agent persona remains e-drug-lab cross-disease scientist (`config/SOUL.md`); AI4S/MASLD is a competition preset only.
- Platform knowledge syncs as `.hermes/PLATFORM.md` + `.hermes/platform/catalog.yaml` (does not replace SOUL).

## Limits

- Full Vina docking pipeline is intentionally `skipped_missing_dependency` / not wired to invent scores; production docking prefers Schrödinger via `schrodinger_service` (`masld-agent schrodinger-dock`).
- Large DiffDynamic / Glide jobs require explicit `--confirm`; defaults are dry-run / sample_only / small ligand sets.
- `api/integrations/*` remote stubs are **not** production paths.
- Open Targets / PubChem live calls require network; offline demo uses fixtures.
- Hermes vendor tree is optional (`vendor/hermes-agent`); plugin loads when Hermes is installed.
- Ligand SMILES in HSD17B13 fixture are null offline (fetch by CID online) to avoid fabricated structures.
- Official-library Top10 (C1) is **not invented**; template + `pending_library_nomination` until SDF-sourced molecules are filled.

## Acceptance commands

```bash
pip install -e ".[dev]"
pytest -q
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
masld-agent competition-brief
masld-agent dual-readout-lint --text <(echo '只降脂不写活力')
# expect non-zero exit / missing cell_viability
masld-agent platform-health
masld-agent platform-catalog --system sz
masld-agent diffdynamic-status
masld-agent schrodinger-status
```
