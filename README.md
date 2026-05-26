# e-drug lab

e-drug lab 是一个面向先导化合物生成与虚拟筛选流程的一体化平台原型。项目目标是把靶点准备、分子库管理、SDF 分子解析、虚拟筛选、ADMET 过滤、亲和力评估、候选排序和任务管理串成一个药物发现工作流。

当前仓库更接近“可继续开发的原型”：FastAPI 后端、SQLAlchemy 数据模型、SDF 同步服务、外部工具/API 客户端骨架已经存在；前端已恢复为可构建的 Next.js/Tailwind 工作台，但多数后端业务仍是占位实现。

## 当前完整度

| 模块 | 当前状态 | 完整度判断 |
| --- | --- | --- |
| 后端 API 框架 | FastAPI 应用入口、CORS、中间件、统一错误处理、健康检查已实现 | 基础可用 |
| 靶点管理 | 提供列表、创建、下载、结构预测、预处理等接口 | 占位实现，未接真实业务 |
| 分子库管理 | 提供列表、创建、上传、过滤接口 | 占位实现，未接真实存储 |
| SDF 分子数据库 | 有 RDKit 解析、目录扫描、数据库同步、分页筛选和统计接口 | 设计较完整，但数据库连接未真正初始化 |
| 数据模型 | 定义了项目、靶点、分子库、筛选任务、候选分子、SDF 分子、工具配置和 API 凭据模型 | 有模型，已补 `database/init.sql` |
| 任务队列 | Celery 配置和 AutoDock Vina docking worker 骨架存在 | worker 内核心 docking 逻辑仍是 TODO |
| 外部工具/API | AutoDock Vina、Fpocket、Gromacs、RDKit、Schrodinger、DrugClip、TAME-VS、DiffDynamic 配置或客户端骨架存在 | 只完成封装和配置，未形成完整调用链 |
| 前端 | Next.js 16、React、TypeScript、Tailwind 工作台页面已恢复 | 可类型检查并可生产构建 |
| 文档和数据 | `docs/COMPLETION_REPORT.md`、`database/init.sql`、示例 SDF 文件已恢复 | 可作为本地开发起点 |

总体判断：项目当前约为 45% 左右的原型完整度。前端、数据库 schema 和示例分子文件已经恢复；后端接口和数据结构方向清楚，但多数核心业务仍是占位返回，数据库 session 也尚未接入 FastAPI 生命周期。

## 技术栈

### 后端

- Python 3.10+
- FastAPI
- Pydantic / pydantic-settings
- SQLAlchemy
- PostgreSQL / asyncpg
- Celery + Redis
- RDKit、NumPy、Pandas、SciPy
- httpx

### 前端

从目录命名推断计划使用：

- Next.js
- React
- TypeScript
- Tailwind CSS

当前前端已恢复为工作台骨架，包含总览、工作流、分子库、模型、记录和文档页面。

## 项目结构

```text
e-drug-lab/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py                      # FastAPI 应用入口
│       ├── config.py                    # 环境变量和配置管理
│       ├── core/
│       │   └── errors.py                # 统一错误类型和异常处理
│       ├── api/
│       │   ├── routes/
│       │   │   ├── targets.py           # 靶点管理 API
│       │   │   ├── libraries.py         # 分子库管理 API
│       │   │   ├── molecule_db.py       # SDF 分子数据库 API
│       │   │   └── combined_routes.py   # 筛选/ADMET/任务等路由草稿，当前未注册
│       │   └── integrations/
│       │       ├── schrodinger.py       # Schrodinger 客户端骨架
│       │       ├── drugclip.py          # DrugClip 客户端骨架
│       │       ├── tame_vs.py           # TAME-VS 客户端骨架
│       │       └── diffdynamic.py       # DiffDynamic 客户端骨架
│       ├── repositories/
│       │   └── models.py                # SQLAlchemy 数据模型
│       ├── services/
│       │   ├── sdf_parser.py            # RDKit SDF 解析
│       │   ├── sdf_sync.py              # SDF 文件夹同步到数据库
│       │   └── tool_manager.py          # 本地工具可用性检查与执行
│       └── workers/
│           ├── celery_app.py            # Celery 应用配置
│           └── docking_worker.py        # docking 任务骨架
├── frontend/
│   └── src/
│       ├── app/                         # Next.js App Router 页面规划
│       ├── components/                  # 导航、布局、语言切换等组件规划
│       └── lib/                         # API client、i18n 规划
├── database/
│   └── init.sql                         # 当前为空字节，需恢复或重写
├── molecules/
│   └── sdf/                             # Aspirin / Ibuprofen SDF 示例文件
├── docs/
│   └── COMPLETION_REPORT.md             # 当前为空字节
└── saves/
    └── run_state.json                   # 当前为空字节
```

## 后端接口概览

当前 `backend/app/main.py` 注册了以下路由：

- `GET /health`：健康检查
- `GET /ready`：检查本地工具可用状态
- `GET /api/v1/tools/status`：返回工具状态
- `/api/v1/targets`：靶点列表、创建、下载、结构预测、预处理
- `/api/v1/libraries`：分子库列表、创建、上传、过滤
- `/api/v1/molecule-db`：SDF 分子列表、详情、同步、统计、删除
- `/api/v1/ranking/orthogonal-rescore`：正交重打分排序；同一指标可提交多个模型输出，先选择一个代表观测值，再用正交指标生成最终分
- `/api/v1/ranking/orthogonal-demo`：正交重打分示例数据
- `/api/v1/tame-vs/status`：检查 Windows WSL Docker、TAME-VS 仓库、Dockerfile 和输出目录
- `/api/v1/tame-vs/build-image`：通过 `C:\Windows\System32\wsl.exe docker build ...` 构建 TAME-VS 镜像
- `/api/v1/tame-vs/smoke-test`：生成两分子测试 CSV，通过 WSL Docker 跑 TAME-VS fingerprint preparation，成功后自动转 SDF 并同步入分子库
- `/api/v1/tame-vs/prepare-library`：对指定 CSV 执行 TAME-VS library preparation，默认自动导入输出分子
- `/api/v1/tame-vs/ingest-results`：把 TAME-VS 结果 CSV 转成 SDF，并复用 SDF sync 入库

`backend/app/api/routes/combined_routes.py` 中还规划了筛选、ADMET、亲和力评估、分子生成和任务管理接口，目前已注册到主应用，但仍主要是占位返回。

## 正交重打分策略

项目现在支持“同一指标多个模型值”的数据结构：

- `candidate_metric_values`：保存单个候选分子在某个指标上的一次模型/方法输出，例如 Vina docking score、GNINA score、MM/GBSA score。
- `orthogonal_scores`：保存正交重打分后的最终排序结果、主分数、正交分数、一致性差距和 artifact 标记。

选择单个指标代表值时不做平均：

1. 如果请求指定 preferred model，则选择该模型的观测值。
2. 如果没有 preferred model，则在同一优先级组内选择最接近中位数的实际观测值。
3. 选择结果始终是某个真实模型输出，不是均值。

最终分数不由主打分函数决定，而由正交重打分主导。逻辑是：如果某个分子在主打分函数中很好，但在正交方法中明显变差，就把它标记为可能的 scoring-function artifact 并扣分。这对应“利用某一打分函数漏洞的分子，在独立正交方法中应暴露异常”的筛选思路。

## 环境变量

后端启动时会通过 pydantic-settings 读取 `.env`。以下变量是当前配置模型要求或常用的关键项：

```env
APP_DEBUG=true
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/edrug_lab
DATABASE_POOL_SIZE=10
DATABASE_ECHO=false

SCHRODINGER_API_KEY=your-key
SCHRODINGER_BASE_URL=https://api.schrodinger.com/v1

DRUGCLIP_API_KEY=your-key
DRUGCLIP_BASE_URL=https://api.drugclip.com/v1

TAME_VS_API_KEY=your-key
TAME_VS_BASE_URL=https://api.tamevs.org/v1

DIFFDYNAMIC_API_KEY=your-key
DIFFDYNAMIC_BASE_URL=https://api.diffdynamic.org/v1

TOOL_AUTODOCK_VINA=/path/to/vina
TOOL_FPOCKET=/path/to/fpocket
TOOL_GROMACS=/path/to/gmx
TOOL_RDKIT_DATA=/path/to/rdkit/Data

TAME_VS_REPO_PATH=tools/Target-driven-ML-enabled-VS
TAME_VS_IMAGE_NAME=edrug-lab/tame-vs:latest
TAME_VS_WSL_EXE=C:\Windows\System32\wsl.exe
TAME_VS_WSL_DISTRO=eDrugUbuntu
TAME_VS_OUTPUT_DIR=outputs/tame-vs

CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

注意：这些配置类目前多数使用必填字段。缺少数据库连接、外部 API key 或工具路径时，应用会在导入配置阶段失败。

## 本地运行

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Celery worker

需要先启动 Redis，并配置好 `.env`：

```bash
cd backend
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

### 前端

前端已恢复，可按 Next.js 项目方式运行：

```bash
cd frontend
npm install
npm run dev
```

## 已知问题

- 已发现的全 0 字节文件已恢复或移除，不再有非 `node_modules` / 非 `.next` 的全空文件。
- npm audit 仍报告 Next 16.2.6 内部依赖的 `postcss <8.5.10` 中等级公告；当前 npm 给出的自动修复方案会降级到 Next 9.3.3，不适合作为本项目修复路径。
- 当前 Windows 已安装 WSL 2.7.3，并将 Ubuntu 24.04 WSL2 发行版 `eDrugUbuntu` 导入到 `E:\WSL\eDrugUbuntu`；该发行版内已安装 Docker Engine 29.5.2，并构建了 `edrug-lab/tame-vs:latest`。
- FastAPI 当前把 `app.state.db_session` 设为 `None`，`/api/v1/molecule-db/*` 相关接口会返回数据库未连接。
- `combined_routes.py` 未注册到主应用，且内部路由变量名不一致。
- 多数业务接口返回空数组、随机 UUID 或固定状态，尚未接真实筛选、ADMET、亲和力评估和分子生成逻辑。
- docking worker 中 AutoDock Vina 调用仍是 TODO。
- `python -m compileall backend/app` 可以通过语法编译，但这只能证明 Python 文件语法可解析，不能证明服务可以在缺少 `.env`、数据库、Redis 和外部工具时正常运行。

## 建议的下一步

1. 在应用启动时创建真实 SQLAlchemy engine/sessionmaker，并让 `molecule_db` 路由获得数据库 session。
2. 补 Alembic migration，把 `database/init.sql` 纳入可重复迁移流程。
3. 修复并注册 `combined_routes.py`，统一 `screening_router` 命名。
4. 把靶点、分子库、筛选任务和 SDF 分子接口接入真实数据库。
5. 实现 AutoDock Vina、Fpocket、ADMET、DiffDynamic 等工具/API 的真实调用链。
6. 增加后端单元测试、接口测试和最小端到端流程测试。
