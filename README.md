# E-Drug-Lab

靶点导向的药物发现实验平台：**Web 工作流** + **Scientist Agent** + **本地计算工具链**（DiffDynamic / Schrödinger / DrugCLIP / TAME-VS 等）。

面向「从靶点与口袋 → 分子生成 / 筛选 → ADMET → 对接打分 → 排序与湿实验交接」的一体化原型；**禁止编造**对接分数、生成结构或 ADMET 数值。

| 组件 | 作用 | 入口 |
|------|------|------|
| **Backend** | FastAPI：靶点/分子库/筛选任务、工具封装、SDF 同步与排序 | `backend/` |
| **Frontend** | Next.js：工作流页面（靶点准备、建库、VS、ADMET、亲和力、排序等） | `frontend/` |
| **Scientist_In_E-Drug-Lab** | 科研助手（CLI / Hermes Skill / MCP）：靶点假说、证据、平台能力目录与门控 | `Scientist_In_E-Drug-Lab/` |

可选：AI4S 生命科学赛道为竞赛预设（见 Agent 内 `config/competition_*.yaml`）；**库内化合物 Top10 提名**与 Agent 靶点假说职责分离。

---

## 仓库结构

```text
backend/                      FastAPI + services + integrations
frontend/                     Next.js 工作流 UI
Scientist_In_E-Drug-Lab/      Scientist Agent（masld-agent）与平台 catalog
database/                     SQL 初始化
docs/                         平台/集成说明
molecules/、outputs/          本地数据与产物（默认不入库）
```

Git 默认只跟踪**代码与 Markdown**（见根目录 `.gitignore`）。大文件、conda/node 依赖、运行产物、以及 `skills_pack` 内完整 skill 正文一般不随仓库全量发布。

---

## 平台能力（三系统）

权威说明：[`Scientist_In_E-Drug-Lab/config/platform/PLATFORM.md`](Scientist_In_E-Drug-Lab/config/platform/PLATFORM.md)  
机器可读目录：[`catalog.yaml`](Scientist_In_E-Drug-Lab/config/platform/catalog.yaml)

| 系统 | 角色 | 生产调用方式 |
|------|------|----------------|
| **DiffDynamic** | 口袋条件分子生成（Fast / Prudent 等） | `DiffDynamicRunner` → conda `diffdynamic`，代码根常为 `/data/ye/DiffDynamic` |
| **e-drug-lab** | HTTP/库封装、任务与分子库 | Backend services；Agent 优先库导入而非未启动的 FastAPI |
| **Schrödinger** | PrepWizard / LigPrep / Grid / Glide / QikProp / MMGBSA / IFD | `schrodinger_service` → `/opt/schrodinger2023-3` |

硬约束摘要：

1. DiffDynamic 采样受体用**原始 PDB**；PrepWizard 结果只给 Glide。
2. 大批量 / 全漏斗 Glide 须显式确认（`confirm=true`）。
3. `backend/app/api/integrations/*` 的**远程 stub 不是生产路径**。
4. 不把 DiffDynamic 生成分子直接写入 AI4S 官方库 Top10 CSV。

Backend 中与平台相关的实现包括（部分分支已入库）：

- `backend/app/services/diffdynamic_runner.py`、`schrodinger_service.py`、`admet_service.py`
- `backend/app/api/routes/diffdynamic.py`、`admet.py`、`affinity.py`
- 配置示例：`backend/.env.example`

> 新路由模块若尚未在 `main.py` 中 `include_router`，需在本机接线后再对外提供 HTTP。

---

## 快速开始（克隆后冷启动）

**不要**提交真实 API Key。只复制 `*.example` → 本地文件并自行填写。DiffDynamic / Schrödinger / GPU 为可选外部依赖；缺省时 HTTP 与 Agent 对话仍可起，漏斗计算步骤会门控失败。

### 1. Backend

```bash
cd backend
cp .env.example .env   # 至少设置 database__url=sqlite:///./edrug_lab_dev.db
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- Health：`GET http://localhost:8000/health`
- Ready：`GET http://localhost:8000/ready`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev            # 默认 http://0.0.0.0:3001（见 package.json）
```

可选：复制注释模板到 `.env.local`（勿提交）以覆盖 `NEXT_PUBLIC_API_BASE_URL`。

### 3. Scientist Agent

详见 [`Scientist_In_E-Drug-Lab/README.md`](Scientist_In_E-Drug-Lab/README.md)。

```bash
cd Scientist_In_E-Drug-Lab
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Hermes（不入库；见 vendor/README.md）
mkdir -p vendor
git clone --depth 1 https://github.com/NousResearch/hermes-agent.git vendor/hermes-agent
pip install -e ./vendor/hermes-agent

cp .env.example .env                                    # 填 OPENAI_API_KEY / OPENAI_BASE_URL 等
cp config/providers.example.yaml config/providers.yaml  # 本地用，默认不入库
# 如需改中继地址：编辑 config/hermes.config.yaml 中的 placeholder，或 export OPENAI_BASE_URL=...

python scripts/import_drug_skills.py   # 从 skills/ 链接到 .hermes/skills
bash scripts/start_agent.sh            # 或 start_agent.sh shell → masld-agent …

masld-agent platform-health
masld-agent platform-catalog --system dd
```

人设：[`config/SOUL.md`](Scientist_In_E-Drug-Lab/config/SOUL.md)  
Skills：仓库内 [`Scientist_In_E-Drug-Lab/skills/`](Scientist_In_E-Drug-Lab/skills/)（funnel 全量 + 精简 ddfast/drug-design/campaign）；[`skills_pack/MANIFEST.json`](Scientist_In_E-Drug-Lab/skills_pack/MANIFEST.json) 为导入清单。

---

## 环境变量

| 文件 | 用途 |
|------|------|
| [`backend/.env.example`](backend/.env.example) | 数据库、DiffDynamic、Schrödinger、DrugCLIP、TAME-VS、Celery、CORS 等 |
| [`Scientist_In_E-Drug-Lab/.env.example`](Scientist_In_E-Drug-Lab/.env.example) | Agent / Hermes Provider |
| [`Scientist_In_E-Drug-Lab/config/providers.example.yaml`](Scientist_In_E-Drug-Lab/config/providers.example.yaml) | 多模型 Provider 模板 |

**不要**提交 `.env`、`providers.yaml` 或任何 API Key。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [`Scientist_In_E-Drug-Lab/docs/DELIVERY.md`](Scientist_In_E-Drug-Lab/docs/DELIVERY.md) | Agent 交付范围与验收命令 |
| [`Scientist_In_E-Drug-Lab/docs/architecture.md`](Scientist_In_E-Drug-Lab/docs/architecture.md) | Agent 架构 |
| [`Scientist_In_E-Drug-Lab/docs/LINUX.md`](Scientist_In_E-Drug-Lab/docs/LINUX.md) / [`WINDOWS.md`](Scientist_In_E-Drug-Lab/docs/WINDOWS.md) | 安装 |
| [`docs/TAME_VS_INTEGRATION.md`](docs/TAME_VS_INTEGRATION.md) | TAME-VS 集成（若存在） |
| [`WORK.md`](WORK.md) | 历史说明备份 |

---

## 开发状态

活跃原型。部分 frontend 工作流与本地工具路径依赖机房环境（conda、GPU、Schrödinger 许可证）。远程 API stub 仅作占位，生产请走本地 runner / service。

---

## License

见 [`Scientist_In_E-Drug-Lab/LICENSE`](Scientist_In_E-Drug-Lab/LICENSE)（Agent 子树）；仓库其余部分以项目声明为准。
