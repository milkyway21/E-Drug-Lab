# e-drug-lab 项目结构记忆

> 先导化合物生成与虚拟筛选一体化平台（target-focused virtual screening workflow）。
> Monorepo：FastAPI 后端 + Next.js 前端 + PostgreSQL/SQLite + Celery/Redis。
> 本文件由 agent 整理，作为后续会话的入门地图。最后更新：2026-06-20。

## 1. 顶层布局

```
/data/ye/e-drug-lab/
├── backend/          # Python 3.10+ FastAPI, port 8000
├── frontend/         # Next.js 14 (App Router) + TS + Tailwind, port 3000
├── database/         # init.sql — PostgreSQL schema (10 tables)
├── molecules/        # 样本分子 (sdf/, pdbqt/)
├── models/           # (空，预留给模型权重)
├── tools/            # 外部 vendored 工具（各自独立 git）
│   ├── DrugClip/                      # DrugClip 打分工具
│   └── Target-driven-ML-enabled-VS/   # TAME-VS 全流程（+ _OLD 旧版）
├── deliverables/     # 打包交付物 (drugclip-package, target-driven-vs-package)
├── data/             # data/results/ 运行产出
├── outputs/          # outputs/tame-vs/ TAME-VS 产出
├── saves/            # run_state.json 运行状态
├── docs/             # 设计/评审文档 (plan.md, *_CODE_REVIEW.md, TAME_VS_INTEGRATION.md)
├── bio-research/     # bio-research 插件 (skills)
├── nature-skills/    # nature 系列学术写作技能
├── skills/           # admet-filter 等 skill
├── claude/           # ← 本文件夹：agent 持久记忆
├── CLAUDE.md         # 项目说明（架构、运行、约束、测试规则）
├── GUIDE.md          # 详细指南（26KB）
├── CODE_REVIEW.md    # 代码评审记录
├── README.md / WORK.md
└── .gitignore        # 策略：只追踪 code + markdown
```

## 2. 后端 `backend/app/`

入口 `backend/app/main.py`：FastAPI app，lifespan + CORS + middleware，注册 14 个 router。
所有 API 前缀 `/api/v1/`，健康检查 `/health`、`/ready`。

### 2.1 路由 `api/routes/`
| 文件 | 职责 |
|------|------|
| `targets.py` | 靶点 CRUD |
| `libraries.py` | 化合物库 CRUD |
| `molecule_db.py` | SDF 分子库：列表/同步/统计/删除 |
| `ranking.py` | 正交重打分 `orthogonal-rescore` |
| `tame_vs.py` | TAME-VS Docker 流水线（status/build/smoke/prepare/ingest）|
| `drugclip.py` | DrugClip 打分 |
| `diffgui.py` | DiffGui 运行器 |
| `glare.py` | GLARE 运行器 |
| `rl_rounds.py` | 强化学习轮次 |
| `screening.py` | 筛选（combined）|
| `admet.py` | ADMET 评估 |
| `affinity.py` | 亲和力评估 |
| `molecules.py` | 分子查询（combined）|
| `tasks.py` | 任务状态（combined）|
| `combined_routes.py` | 旧聚合路由（部分 stub）|

### 2.2 外部集成 `api/integrations/`
`schrodinger.py`、`drugclip.py`、`tame_vs.py`、`diffdynamic.py` —— 各外部 API client 骨架。

### 2.3 服务层 `services/`
`sdf_parser` / `sdf_sync`（SDF 解析与同步）、`tool_manager`、`orthogonal_scoring`、
`tame_vs_docker` / `drugclip_docker`、`vina_service` / `docking_prep`（对接）、
`admet_service`、`sa_score`、`diffgui_runner` / `glare_runner` / `conda_runner`
（子进程运行器）、`pipeline_eval_bridge`、`rl_round_service`、`xlsx_report`、`job_store`。

### 2.4 其他
- `config.py` — pydantic-settings `Settings`，`env_nested_delimiter="__"`。
  嵌套：Database / Schrodinger / DrugClip / TameVS / DiffDynamic / ToolPaths / Celery / Admet / DiffGui / Glare。
- `core/` — `errors.py`（AppError）、`paths.py`、`screening_tools.py`、`workflow_steps.py`
- `db.py` — SQLAlchemy engine
- `repositories/models.py` — ORM（见下）
- `workers/` — `celery_app.py` + `docking_worker.py`（TODO 骨架）
- `alembic/` — 迁移（已含 `2aae692a3003_init.py`）
- `tests/` — pytest：sdf_parser / orthogonal_scoring / ranking_naming / docking_prep / drugclip_*

## 3. 数据模型 `repositories/models.py`（10 张表，UUID 主键）
`projects` · `targets` · `compound_libraries` · `screening_tasks` ·
`candidate_molecules` · `sdf_molecules` · `tool_configurations` · `api_credentials` ·
`rl_rounds` · `rl_round_artifacts`
（CLAUDE.md 中写 8 表，实际已增至 10 表，新增 RL 相关两张）

## 4. 前端 `frontend/src/`

Next.js App Router。`lib/api-client.ts` 用原生 fetch 封装，返回 `ApiResult<T>`（不抛异常）。

### 页面 `app/`
- 顶层：`page.tsx`(首页) · `database/` · `models/` · `records/` · `docs/` · `layout.tsx` · `globals.css`
- `workflow/`：`page.tsx`(总览) + 8 个步骤页
  - `target-prep` · `library-build` · `virtual-screening` · `admet-filter`
  - `affinity-eval` · `candidate-rank` · `compound-sourcing` · `rl-training`
  - `workflow/layout.tsx`

### 组件 `components/`
- 顶层：`NavBar` · `Footer` · `LanguageToggle` · `MoleculeStructure`
- `workflow/`：`WorkflowLayout` · `PipelineRunner` · `ModelSelector` · `MoleculePanel` · `ResultCard`

### 库 `lib/`
`api-client.ts` · `docking-metrics.ts` · `models-config.ts` · `workflow-context.tsx`
· `i18n/`（`i18n-context.tsx` + `translations.ts`，中英切换）

样式：Tailwind 自定义色板 `ink/muted/mist/paper/teal/cobalt/amber/rose`；
图标 Lucide + Phosphor；动画 Framer Motion；路径别名 `@/* → src/*`。

## 5. 运行

```bash
# 后端
cd backend && pip install -r requirements.txt
cp .env.example .env   # 必填，pydantic fail-fast；至少 database__url
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev   # http://localhost:3000
```
dev 数据库：`sqlite:///./edrug_lab_dev.db`（自动创建）。

## 6. 当前状态（约 45% 原型）

✅ 已实现：FastAPI 骨架 + 14 router、ORM 10 表、Alembic init 迁移、前端 workbench 骨架、
SDF 解析/同步、正交打分、DrugClip/TAME-VS/DiffGui/GLARE 运行器、ADMET/affinity 服务、部分 pytest。

⚠️ 已知缺口（来自 CLAUDE.md，需实地核实）：
- DB session 可能未注入 route handler（engine 建了，`db_session` 注入待确认）
- `combined_routes.py` 部分 stub
- Celery/docking_worker 仍是 TODO 骨架
- 后端测试覆盖有限
- CLAUDE.md 描述为 Windows/WSL2 环境，但实际运行在 Linux（以实际为准）

## 7. 约束与测试规则（来自 CLAUDE.md）
- Git 策略：只追踪 code + markdown，`git add` 按文件名，**禁止 `git add .`**
- DiffDynamic 测试：生成 `batch_size=5`、评估 `max_samples=5`、vina 超时 20s、自动链式执行
- **永远不删 `diffdynamic.db`**（持久化历史）
- API 测试样例：`{"mode":"dynamic","data_id":0,"batch_size":5,"auto_evaluate":true,"auto_extract":true}`

## 8. 相关文档指针
- `CLAUDE.md` — 项目权威说明（架构/运行/约束）
- `GUIDE.md` — 详细操作指南（26KB）
- `docs/plan.md` — 重构计划
- `docs/PIPELINE_CODE_REVIEW.md` / `docs/CODE_REVIEW.md` — 流水线与整体评审
- `docs/TAME_VS_INTEGRATION.md` — TAME-VS 集成说明
- `CODE_REVIEW.md`（根）、`drugclip_issues.md` — 待办与已知问题
