# Scientist_In_E-Drug-Lab

**e-drug-lab 平台药物发现科研助手**（Hermes Plugin / Skill / MCP 扩展，**不修改 Hermes 核心**）。覆盖靶点假说、机制、证据链、结构/口袋、配体与对接验证计划等，**不限单一疾病**。

- 平台：[`/data/ye/e-drug-lab`](file:///data/ye/e-drug-lab)
- 人设：[`config/SOUL.md`](config/SOUL.md)（启动时同步到 `.hermes/SOUL.md`）
- 平台能力目录：[`config/platform/PLATFORM.md`](config/platform/PLATFORM.md) + [`catalog.yaml`](config/platform/catalog.yaml)（同步到 `.hermes/`，**不改人设**）
- **AI4S 生命科学赛道**为可选竞赛预设（默认疾病 MASLD；可切 HCC，须向组委会确认，禁止混淆）。库内化合物 Top10（C1）仍由 `ai4s_masld_lipid` S01–S08 负责；本 Agent 侧重靶点 / 机制 / Proposal+Method。

竞赛相关配置与报告含 **`competition_scope_warning`**（仅在讨论该赛道/提交时强调）。

## Quick start (Linux)

```bash
cd /data/ye/e-drug-lab/Scientist_In_E-Drug-Lab
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install -e "./vendor/hermes-agent"
# 对话（Hermes 多 Provider，从 CC-Switch 同步密钥）
bash scripts/start_agent.sh
# 离线科学管线
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
```

## Windows (PowerShell / WSL2)

Prefer WSL2 and the Linux commands above. Native Windows:

```powershell
cd \data\ye\e-drug-lab\Scientist_In_E-Drug-Lab
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install -e ".\vendor\hermes-agent"
masld-agent offline-demo --fixture tests/fixtures/hsd17b13 --output runs
```

## Dialogue (Hermes multi-provider)

**不要用**自研 LLM REPL。对话与 Claude Code CLI 一样走 Hermes Provider 抽象：

```bash
bash scripts/start_agent.sh
# 或
HERMES_HOME=$PWD/.hermes hermes chat --provider volcengine-plan
HERMES_HOME=$PWD/.hermes hermes chat --provider volcano-anthropic
hermes model
```

详见 [docs/hermes_integration.md](docs/hermes_integration.md)。

## Skills（药物设计 / 论文 / 自写）

```bash
python scripts/import_drug_skills.py   # 导入/刷新到 .hermes/skills
# ddfast 00–10 | drug-design×20 | writing×10 | masld-ai4s（s00–s08 + scientist）
```

## CLI（科学管线）

```bash
masld-agent run --competition config/competition_life_science.yaml \
  --disease MASLD --modality small_molecule_inhibitor --top-targets 10 --output runs/demo

masld-agent evaluate-target --gene HSD17B13 --uniprot Q7Z5P4 --output runs/hsd17b13

masld-agent offline-demo --fixture tests/fixtures/hsd17b13
```

## 三平台（DiffDynamic / e-drug-lab / 薛定谔）

先查目录与健康，再跑计算；大任务须 `--confirm`。调用优先库导入 e-drug-lab services（不依赖未起的 FastAPI）。

```bash
masld-agent platform-catalog --system dd   # 或 ed / sz；--id dd.mode.scaffold_fast
masld-agent platform-health
masld-agent diffdynamic-status
masld-agent schrodinger-status
masld-agent diffdynamic-generate --protein R.pdb --ligand L.sdf --dry-run
masld-agent schrodinger-dock --receptor R.pdb --smiles 'CCO' --dry-run
```

Online literature (Europe PMC):

```bash
masld-agent run --online --output runs/online_demo
```

## AI4S 提交辅助（人设不变）

身份仍以 [`config/SOUL.md`](config/SOUL.md) 为准。以下命令仅用于书生国智**生命科学赛道**提交语境（HepG2-FFA 双读出、Top10 模板、校验与打包）。官方简报缓存：[`config/briefs/life_zh.md`](config/briefs/life_zh.md)。

```bash
masld-agent competition-brief
masld-agent export-top10-template --output runs/top10_nomination.csv
masld-agent hepg2-plan --run-dir runs/<run_id>
masld-agent dual-readout-lint --text runs/<run_id>/proposal.md
masld-agent validate-submission --run-dir runs/<run_id>
masld-agent pack-submission --run-dir runs/<run_id> --output runs/<run_id>/submission/ai4s_bundle.zip
```

- 库内 Top10（C1）必须来自官方 SDF；未填结构时标记 `pending_library_nomination`。
- 评分维度 60/20/20 见 [`config/competition_life_science.yaml`](config/competition_life_science.yaml)。
- `offline-demo` / `run` 会写入 `submission/README_AI4S.md` 指针。

## LLM credentials

- 推荐：`bash scripts/start_agent.sh sync`（从 CC-Switch 当前 Claude provider 写入 `.hermes/.env`）
- 或复制 `.env.example` → `.env`（`OPENAI_API_KEY` / `ANTHROPIC_*` / `MASLD_LLM_*`）
- 模板：`config/hermes.config.yaml`、`config/providers.example.yaml`
- Scientific DB / RDKit calls **never** go through the LLM.

## Hermes Plugin

`hermes_agent.plugins` → `masld_agent.hermes_plugin:register`

Eval mode disables uncontrolled memory (`config/hermes.config.yaml` + `config/competition_life_science.yaml`).

## Docker

```bash
docker compose build
docker compose run --rm masld-agent
```

## Tests

```bash
pytest -q
python scripts/test_volcano_llm.py   # optional Coding Plan smoke (not chat)
```

## License

MIT — see `LICENSE` / `NOTICE` (Hermes and third-party attributions).
