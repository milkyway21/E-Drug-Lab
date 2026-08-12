# E-Drug-Lab

面向药物发现任务的端到端科研平台，包含三部分：

- `backend/`：FastAPI 后端，提供靶点、蛋白/配体、化合物库、筛选、ADMET、对接和任务接口。
- `frontend/`：Next.js 工作流界面，用于查看靶点、分子库、虚拟筛选、ADMET、亲和力和任务状态。
- `Scientist_In_E-Drug-Lab/`：基于 Hermes Agent 的科研助手，通过 skills、插件和本地 CLI 编排药物发现流程。

项目遵循证据优先原则：没有实际计算结果时，不编造生成结构、对接分数、ADMET 数值或分子动力学结论。

## 仓库结构

```text
backend/                         FastAPI 后端与本地服务封装
frontend/                        Next.js 前端
Scientist_In_E-Drug-Lab/         Scientist Agent、插件、CLI、配置与 skills
Scientist_In_E-Drug-Lab/vendor/
  hermes-agent/                  Hermes Agent 源码快照，已纳入本仓库
competition_skills_submission/  按比赛流程图整理的实体 skills 提交目录
docs/                            平台与集成文档
```

`vendor/hermes-agent` 是普通源码目录，不是 Git 子模块；其嵌套 Git 历史、运行时缓存、虚拟环境、构建产物和凭据不会上传。

## 安装与启动

以下命令在 Linux/WSL2 中执行。真实 API key 不要写入 Git；只复制 `.env.example` 为本地 `.env`。

### 1. 后端

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

健康检查：`http://localhost:8000/health` 和 `http://localhost:8000/ready`。

### 2. 前端

另开终端：

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://localhost:3001/`。前端默认把浏览器请求发送到同一主机的后端 `8000` 端口；需要覆盖时，在 `frontend/.env.local` 设置 `NEXT_PUBLIC_API_BASE_URL`，该文件不要提交。

### 3. Scientist Agent 与 Hermes

```bash
cd Scientist_In_E-Drug-Lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e ./vendor/hermes-agent

cp .env.example .env
cp config/providers.example.yaml config/providers.yaml
python scripts/import_drug_skills.py
bash scripts/start_agent.sh chat
```

`scripts/start_agent.sh` 会准备 `HERMES_HOME`、加载本地 provider 配置、同步 Agent 人设和 skills，并启动 Hermes 对话界面。API key 只放在本地 `.env`、`.hermes/.env` 或系统密钥管理器中；仓库不提供任何真实密钥。

科学管线 CLI：

```bash
bash scripts/start_agent.sh shell
masld-agent platform-health
masld-agent platform-catalog
masld-agent funnel autopilot --final-count 10 --profile test --target-id TARGET
```

Hermes 负责对话、工具调用和 skill 编排；科研计算由 `masld-agent`、后端服务以及本地 DiffDynamic/Schrödinger 等工具执行。Hermes 核心源码位于 `Scientist_In_E-Drug-Lab/vendor/hermes-agent/`，项目适配通过插件与 skills 完成。

## 八类 Skills

技能主类按整体流程图组织。每个主类下保留现有子 skill 名称；Agent 运行时使用 `Scientist_In_E-Drug-Lab/skills/`，Hermes 导入后使用 `.hermes/skills/`。

| 顺序 | 主类 | 作用 | 主要子 skill 示例 |
|---:|---|---|---|
| 01 | `drug-discovery-orchestrator` | 任务拆解、流程编排、持续监测、时间调度和汇总报告 | `funnel-orchestrator`、`time-scheduler`、`reporting` |
| 02 | `target-discovery` | 生物学证据、靶点结构、PDB、口袋和蛋白/配体准备 | `research-target-biology`、`rank-protein-structures`、`prepare-native-protein-ligand` |
| 03 | `dd-generation` | DiffDynamic de novo 与 Prudent 分子生成 | `funnel-diffdynamic-denovo`、`funnel-diffdynamic-prudent` |
| 04 | `virtual-docking` | Schrödinger Glide SP/XP、网格、对接和 MMGBSA | `funnel-glide-sp`、`funnel-glide-xp`、`funnel-mmgbsa` |
| 05 | `featurehit-finding` | 姿势提取、药效团/形状筛选、RDKit 特征和库中 hit 搜索 | `pose-library-screening`、`funnel-featurehit`、`rdkit` |
| 06 | `admet` | ADMET、QikProp、毒性分层和化合物证据补充 | `ddfast-06-qikprop-admet`、`funnel-drugflow-hepg2`、`triage-compound-toxicity` |
| 07 | `molecular-dynamics` | Desmond 短程/长程分子动力学、监测和轨迹分析 | `funnel-desmond-short-md`、`funnel-desmond-long-md`、`dd-md-desmond-sea-qc` |
| 08 | `all-analysis` | 候选提名、机制假说、证据整合和最终报告 | `nominate-lipid-modulators`、`write-mechanism-validation-report` |

同步 skills 到 Hermes：

```bash
cd Scientist_In-E-Drug-Lab
python scripts/import_drug_skills.py --hermes-home .hermes --check
```

比赛提交用的全实体目录位于：
`competition_skills_submission/`。其中包含 `01_` 到 `08_` 八个实体主目录，不使用符号链接，适合单独打包提交。

## 外部计算依赖

后端和 Agent 的基础代码可以单独启动；完整药物发现漏斗还依赖使用者本地安装的计算环境：

- DiffDynamic 及其 conda 环境、模型和 GPU；
- Schrödinger Suite、许可证和 Glide/Desmond/QikProp/MMGBSA；
- 可选的 DrugCLIP、TAME-VS 或其他本地服务；
- 访问 PubMed、RCSB PDB、PubChem 等公开数据库的网络环境。

这些依赖的路径和开关放在各自的 `.env.example`、平台 catalog 和 skills 中，不上传密钥、模型权重、实验产物或本地数据库。

## 常用文档

- [Agent README](Scientist_In-E-Drug-Lab/README.md)
- [Hermes 集成说明](Scientist_In-E-Drug-Lab/docs/hermes_integration.md)
- [Agent 架构](Scientist_In-E-Drug-Lab/docs/architecture.md)
- [平台能力目录](Scientist_In-E-Drug-Lab/config/platform/PLATFORM.md)
- [比赛实体 skills 目录](competition_skills_submission/README.md)

## 安全与提交

不要提交以下内容：`.env`、`.env.local`、`.hermes/`、`providers.yaml`、`auth.json`、API key、私钥、GPU 运行产物、模型权重和本地数据库。提交前可检查：

```bash
git status --short
git diff --check
git grep -nE 'sk-[A-Za-z0-9]{20,}|ark-[A-Za-z0-9-]{20,}' -- ':!*.md'
```

## License

项目代码与 Agent 子树的许可证见各自目录中的 `LICENSE` / `NOTICE` 文件。Hermes 源码保留其上游许可证与版权声明。
