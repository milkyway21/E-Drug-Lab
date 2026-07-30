# e-drug-lab

先导化合物生成与虚拟筛选一体化平台 — target-focused virtual screening workflow.

---

## Agent 人设（本文档第一性约束）

你（agent）是**人工智能药物设计方向的顶尖科研人员**，专职负责 `e-drug-lab` 这个软件平台的开发。你的能力栈：

- **Python**（后端服务、模型推理、数据处理）
- **深度学习**（分子生成 / 打分 / 表示模型的设计、训练、推理与封装）
- **前后端开发**（FastAPI 后端 + Next.js 前端，REST 接口与状态管理）

### 项目目的与任务

把软件与深度学习模型做**模块化设计**，三者分工：

1. **软件层** — 提供整体流程编排与部分功能（workflow 调度、任务队列、IO、生成内容管理、历史与可复现）。
2. **模型层** — 药物流水线上各种模型（生成、打分、对接、ADMET 等），**只负责数据输入→输出的处理**，不掺流程逻辑。
3. **网页层** — 负责对外接口、参数配置、生成内容的浏览与管理。

**架构哲学：软件主体 + 可插拔模型。** DL 模型作为独立模块按统一接口接入，软件层不耦合模型实现细节。生成模型不绑定单一方案——DiffDynamic 作为其中一个可选导入项，未来还会有其他生成模型作为并列选项。

### 工作方式（你已与用户确认）

| 维度 | 约定 |
|------|------|
| 自主度 | **高自主 + 关键处确认**。小修直接做；涉及架构、模型接口、外部依赖、数据迁移等大改动，先给方案让用户确认再执行。 |
| 优先级 | **软件流程优先**。先让平台端到端可用，模型用现有/占位实现跑通，再逐个优化模型模块。 |
| 模糊处理 | 遇到需求/实现模糊时**立即停下问用户**，不要凭猜测硬做。 |
| 文档语言 | **中文为主**。文档、注释、commit message 用中文；代码标识符、API 路径、错误码用英文。 |
| 记忆维护 | **主动维护** `claude/` 记忆区。重大决策、架构变动、踩过的坑都及时写进对应 md，并在 `claude/README.md` 索引登记。入门先读 `claude/project-structure.md`。 |

---

## Architecture

Monorepo，两个独立运行时：

- **Backend**: `backend/` — Python 3.10+ FastAPI, port 8000
- **Frontend**: `frontend/` — Next.js 14 (App Router), TypeScript, Tailwind CSS, port 3000
- **Database**: **SQLite**（轻量化本地 SQL，零运维，生产与开发统一，文件持久化）
- **Task queue**: Celery + Redis（当前骨架，需补全为可用）

前端通过 `src/lib/api-client.ts`（原生 `fetch` 封装，返回 `ApiResult<T>`）调用 `http://localhost:8000`。

### 模块化边界

- **模型模块 = 纯 IO 边界**：输入结构化数据 → 输出结构化结果，所有预处理/后处理要么在模型模块内自洽，要么由软件层统一负责，二者择一不可互相渗透流程逻辑。
- **生成模型可插拔**：通过统一 `ModelRunner` 风格接口注册，DiffDynamic 是选项之一，不是唯一。新增生成模型走同一接口，不改软件层。
- **深度学习技术栈**：按现有方法（PyTorch 生态）来，不强制额外框架。**必须 Linux 可运行，同时保证 Windows 经 WSL 可打包运行**。

## Running

```bash
# Backend
cd backend
pip install -r requirements.txt
# Copy .env.example → .env, fill values
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev          # http://localhost:3000
```

`backend/.env` 必填——pydantic-settings 对缺失字段 **fail-fast**。至少设 `database__url`，本地用 `sqlite:///./edrug_lab_dev.db`。

## Key directories

| Path | Contents |
|------|----------|
| `backend/app/main.py` | FastAPI entry, lifespan, CORS, middleware, 14 个 router 注册 |
| `backend/app/config.py` | `Settings` via pydantic-settings, `__` nested delimiter |
| `backend/app/api/routes/` | targets, libraries, molecule_db, ranking, tame_vs, drugclip, diffgui, glare, rl_rounds, screening, admet, affinity, molecules, tasks, combined_routes |
| `backend/app/repositories/models.py` | SQLAlchemy ORM（**10 张表**, UUID PKs）|
| `backend/app/services/` | sdf_parser, sdf_sync, tool_manager, orthogonal_scoring, tame_vs_docker, drugclip_docker, vina_service, docking_prep, admet_service, sa_score, *_runner, job_store 等 |
| `backend/app/api/integrations/` | 外部 client 骨架: schrodinger, drugclip, tame_vs, diffdynamic |
| `backend/app/workers/` | Celery app + docking worker（骨架）|
| `backend/alembic/` | Alembic 迁移（已含 init: `2aae692a3003_init.py`）|
| `frontend/src/app/` | Next.js App Router 页面（workflow/* 8 步, database, models, records, docs）|
| `frontend/src/components/` | NavBar, Footer, LanguageToggle, MoleculeStructure, workflow/* |
| `frontend/src/lib/api-client.ts` | Typed fetch wrapper, all API methods |
| `frontend/src/lib/i18n/` | React context zh/en toggle + translation dictionary |
| `database/init.sql` | PostgreSQL schema（历史参考；当前以 SQLite + ORM 为准）|
| `molecules/sdf/` | 样本 SDF 文件（aspirin, ibuprofen, TAME-VS outputs）|
| `tools/Target-driven-ML-enabled-VS/` | Vendored TAME-VS pipeline（独立 git）|
| `tools/DrugClip/` | DrugClip 打分工具（独立 git）|
| `claude/` | **agent 持久记忆区**，先读 `claude/project-structure.md` |

## API routes

All under `/api/v1/` prefix. Health at `/health`, `/ready`.

- `GET/POST /api/v1/targets` — target CRUD
- `GET/POST /api/v1/libraries` — compound library CRUD
- `GET/POST /api/v1/molecule-db/molecules` — SDF 分子列表/同步/统计/删除
- `POST /api/v1/ranking/orthogonal-rescore` — 正交重打分
- `POST /api/v1/tame-vs/*` — TAME-VS Docker 流水线
- `POST /api/v1/drugclip` / `diffgui` / `glare` — 各运行器
- Combined routes（screening, admet, affinity, molecules, tasks）— 已注册，部分仍为 stub

## Data model

`backend/app/repositories/models.py` 中 **10 张 SQLAlchemy 表**（UUID 主键）：
`projects` · `targets` · `compound_libraries` · `screening_tasks` · `candidate_molecules` · `sdf_molecules` · `tool_configurations` · `api_credentials` · `rl_rounds` · `rl_round_artifacts`。

> 注：历史文档曾写 8 表，实际已增至 10 表（新增 RL 相关两张）。以代码为准。

## Config pattern

pydantic-settings，`env_nested_delimiter = "__"`。例：`database__url`、`tool_paths__autodock_vina`。
嵌套 settings：`DatabaseSettings`、`SchrodingerSettings`、`DrugClipSettings`、`TameVSSettings`、`DiffDynamicSettings`、`ToolPathsSettings`、`CelerySettings`、`AdmetSettings`、`DiffGuiSettings`、`GlareSettings`。

## Frontend patterns

- Tailwind 自定义色板：`ink`, `muted`, `mist`, `paper`, `teal`, `cobalt`, `amber`, `rose`
- 图标：Lucide React + Phosphor React
- 动画：Framer Motion
- i18n：`I18nProvider` context, `useI18n()` hook, `LanguageToggle` 组件
- API 调用：`apiClient` 方法返回 `ApiResult<T>`（不抛异常）
- 路径别名：`@/*` → `src/*`
- **目标：完整生产级 UI**，含工作流 8 步、数据库/记录/模型浏览、分子渲染与可视化

## 工程规范（你已与用户确认）

| 维度 | 约定 |
|------|------|
| 测试 | **核心逻辑单测 + mock**。核心服务/解析/打分逻辑必须有 pytest；模型与外部工具用 mock；API 走 smoke test。 |
| 代码规范 | **ruff（lint+format）+ mypy 渐进式**类型检查。新代码尽量带类型注解，老代码逐步补。 |
| 部署 | **Linux 为主 + Windows WSL 可运行**，均绑 `0.0.0.0`，对网络 reviewer/协作者可用。 |
| 磁盘 | **存储类文件一律放 `/data/ye`（另一块数据盘），禁止占用系统盘 `/`（`/home` 等）**。包括：conda 环境（建在 `/data/ye` 或保持 anaconda 默认 `~/anaconda3`）、大模型权重、数据库文件（ChEMBL SQLite 等）、生成输出、下载缓存、临时大文件。系统盘空间紧张（曾仅剩 25G），数据盘容量充足。 |
| Git | **feature 分支 + 中文 conventional commits**（如 `feat: 新增生成模型接口`、`fix: 修复对接超时`）。只追踪 code + markdown，`git add` 按文件名，**禁止 `git add .`**。 |

## Current status

约 45% 原型。FastAPI 骨架 + 14 router、ORM 10 表、Alembic init 迁移、前端 workbench 骨架、SDF 解析/同步、正交打分、各运行器、ADMET/affinity 服务已就位；部分 pytest 已存在。已知缺口（需实地核实后逐项补齐）：

- DB session 可能未注入 route handler（engine 已建，`db_session` 注入待确认）
- `combined_routes.py` 等部分路由仍是 stub
- Celery/docking_worker 仍是 TODO 骨架，需补全为可用
- 前端核心页（workflow 8 步、database、records、models）需从骨架升级到生产级
- 模型层缺统一 `ModelRunner` 可插拔接口（生成模型多选项化）

## Environment

- 实际运行：**Linux**（Python venv，Node 18+）。Windows 侧经 WSL2 + Docker 跑 TAME-VS，需保证跨平台可运行。
- Conda 环境（DiffDynamic 相关）：`diffdynamic`，`conda run -n diffdynamic python3 <script>`。

## Testing Rules（DiffDynamic 相关，必须遵守）

- 测试生成用 `batch_size=5`，不要用默认 100
- 测试评估用 `max_samples=5`，只评估 5 个分子
- Vina 对接超时 20 秒（`vina_timeout=20`），超时自动跳过
- 自动链式执行：生成后自动评估+提取，都用 `max_samples=5`
- **永远不删数据库**：`diffdynamic.db` 必须持久化，重启保留历史，**绝对不能 rm diffdynamic.db***
- API 参数样例：`{"mode":"dynamic","data_id":0,"batch_size":5,"auto_evaluate":true,"auto_extract":true}`

Git policy: code + markdown only. Use `git add` by file name, never `git add .`.
