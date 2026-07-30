# e-drug lab 使用教程

> 先导化合物生成与虚拟筛选一体化平台 — 用户指南

---

## 目录

1. [项目简介](#项目简介)
2. [环境准备](#环境准备)
3. [启动项目](#启动项目)
4. [页面功能说明](#页面功能说明)
5. [操作流程](#操作流程)
6. [API 接口说明](#api-接口说明)
7. [配置说明](#配置说明)
8. [常见问题](#常见问题)

**快速跳转**： [TAME-VS 接口](#tame-vs-apiv1tame-vs) · [DrugCLIP 接口](#drugclip-apiv1drugclip) · [DiffGUI 接口](#diffgui-apiv1diffgui) · [GLARE / RL 接口](#glare-apiv1glare) · [一键 Pipeline](#流程五一键-pipeline推荐体验完整链路) · [化合物库构建页](#流程四化合物库构建分步页面)

---

## 项目简介

e-drug lab 是一个面向计算化学研究者的**靶向虚拟筛选工作平台**，整合了以下能力：

- **靶点管理**：从 RCSB PDB 下载蛋白结构，预处理用于对接
- **化合物库构建**：DiffGUI AI 生成或 SDF 上传，构建候选化合物库
- **虚拟筛选**：TAME-VS、DrugCLIP、GLARE 强化学习筛选
- **强化学习训练**：GLARE seed/wet-lab 强化与策略训练，产出下一轮筛选 checkpoint
- **ADMET 预测**：吸收、分布、代谢、排泄、毒性评估（开发中）
- **亲和力评估**：MM/GBSA 结合自由能、MD 模拟稳定性（开发中）
- **候选排序**：基于正交重打分算法，对多个评估指标进行综合排名

**当前版本**：原型阶段。分子数据库、正交排序、ADMET 过滤、TAME-VS / DrugCLIP 小样本虚拟筛选端到端已可用；大库筛选、真实 Vina 对接、MM/GBSA 等仍为部分实现或占位。

---

## 环境准备

### 依赖

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.10+ | 后端运行环境 |
| Node.js | 18+ | 前端构建环境 |
| npm | 9+ | 前端包管理 |
| WSL2 + Docker | 推荐 | TAME-VS、DrugCLIP 虚拟筛选需要 |
| NVIDIA GPU | 可选 | DrugCLIP compose 默认请求 GPU；镜像内 PyTorch 为 CPU 版时需自行对齐 |

### 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 安装前端依赖

```bash
cd frontend
npm install
```

### 配置环境变量

```bash
cd backend
cp .env.example .env
```

`.env` 中**必须填写**的项：

```env
database__url=sqlite:///./edrug_lab_dev.db
```

其余项（API 密钥、工具路径等）均为可选，缺少时不影响启动。

---

## 启动项目

### 方式一：命令行启动（推荐）

**终端 1 — 启动后端：**

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

**终端 2 — 启动前端：**

```bash
cd frontend
npm run dev
```

### 方式二：指定端口

```bash
# 后端（端口 8000）
cd backend && python -m uvicorn app.main:app --reload --port 8000

# 前端（端口 3000）
cd frontend && PORT=3000 npm run dev
```

### 验证启动

- 后端健康检查：访问 http://localhost:8000/health ，返回 `{"status":"healthy"}`
- 前端页面：访问 http://localhost:3000

启动后首页会显示后端连接状态和可用工具数量。

---

## 页面功能说明

### 首页 (`/`)

展示平台状态概览：
- **后端状态**：healthy / degraded / offline
- **工具可用数**：如 AutoDock Vina、Fpocket 等
- **快速入口**：Workflow、Database、Models 三张导航卡片

### 工作流 (`/workflow`)

五步药物发现流程已扩展为 **七步强化学习闭环**。页面底部有 **One-Click Pipeline（一键流水线）**，可连续跑 Step 1–7；也可点击各步骤卡片进入分步页面，勾选模型后点击 **Run selected** 单独执行。

| 步骤 | 页面 | 主要可用模型 |
|------|------|-------------|
| 1. 靶点准备 | `/workflow/target-prep` | PDB 下载 (Ready) |
| 2. 化合物库构建 | `/workflow/library-build` | **DiffGUI** (Ready)、SDF 同步 (Ready) |
| 3. 虚拟筛选 | `/workflow/virtual-screening` | **TAME-VS** (Ready)、**DrugCLIP** (Ready)、**GLARE** (Ready) |
| 4. ADMET 过滤 | `/workflow/admet-filter` | RDKit 规则 + ADMET-AI (Ready) |
| 5. 亲和力评估 | `/workflow/affinity-eval` | Vina 版本检测 / 属性估算 (Partial) |
| 6. 候选排序 | `/workflow/candidate-rank` | 正交重排序 (Ready) |
| 7. 强化学习训练 | `/workflow/rl-training` | Seed Reinforce、GLARE Train、Wet-lab Reinforce (Ready) |

> `/workflow/compound-sourcing` 已重定向到 `/workflow/library-build`。

分步页面右侧有 **Pipeline 分子面板**，可将当前步骤结果加入全局 pipeline，供后续步骤与排序使用。工作流上下文会持久化 `roundId`、`glareCheckpoint` 与 `librarySource`。

### 分子数据库 (`/database`)

**当前最完善的功能页面**，支持：

- **分子列表**：分页浏览所有已同步的 SDF 分子
- **筛选过滤**：按分子量范围、LogP 范围、QED 最小值、文件名过滤
- **排序**：按 MW、LogP、QED、TPSA、重原子数等升序/降序
- **文本搜索**：搜索分子名、SMILES、分子式、InChIKey
- **统计概览**：平均 MW、LogP、QED、TPSA、可旋转键数
- **同步功能**：点击 Sync 按钮，将磁盘上的 SDF 文件解析入库
- **分子详情**：点击分子行，查看完整理化性质

### 模型与工具 (`/models`)

展示已注册的外部工具和 API 服务状态：
- **本地工具**：AutoDock Vina、Fpocket
- **外部 API**：Schrodinger、DrugClip、TAME-VS、DiffDynamic
- **工具可用性**：从 `/ready` 接口实时获取

### 执行记录 (`/records`)

历史执行记录展示（当前为占位页面）：
- 靶点设置记录
- SDF 同步记录
- 对接任务记录

### 文档 (`/docs`)

文档入口（当前为占位页面），提供导航到各功能模块的链接。

---

## 操作流程

### 流程一：浏览分子数据库

1. 启动项目后，打开 http://localhost:3000
2. 点击顶部导航栏的 **Database**
3. 首次进入页面为空，点击 **Sync** 按钮同步示例 SDF 文件
4. 同步完成后，分子列表自动加载
5. 使用顶部的过滤条件筛选分子：
   - 设置 MW 范围（如 150 - 500）
   - 设置 LogP 范围（如 -2 - 5）
   - 设置 QED 最小值（如 0.4）
6. 点击任意分子行，查看右侧详情面板

### 流程二：正交重排序 Demo

1. 进入 `/workflow/candidate-rank` 页面
2. 页面自动加载 demo 数据（含 Aspirin、Ibuprofen、一个 artifact 候选）
3. 查看排名结果表格：
   - **Primary Score**：主评估指标（如 Vina 对接分）
   - **Orthogonal Score**：正交指标（如 MM/GBSA 打分）
   - **Gap**：两个指标的 desirability 差异
   - **Final Score**：最终综合得分
   - **Flag**：artifact 标记（高 gap 候选会被标记并降权）

### 流程三：靶点管理

1. 进入 `/workflow/target-prep` 页面
2. 输入靶点名称和 PDB ID（如 `4HHB`）
3. 在 **Available models** 区域勾选 **RCSB PDB Download**
4. 点击 **Run selected (1)** 按钮，自动执行：创建靶点 → 下载 PDB → 预处理
5. 结果卡片显示靶点 ID、PDB ID、状态等信息

### 流程四：化合物库构建（分步页面）

1. 进入 `/workflow/library-build`（原 compound-sourcing 已重定向至此）
2. 填写库名称（可选）
3. 在 **Available models** 勾选一种来源并点击 **Run selected**：

| 模型 | 网页行为 |
|------|----------|
| **DiffGUI** | 调用 `POST /api/v1/diffgui/generate`（默认 5 分子测试规模）→ 轮询 job → `ingest` 入库 → 载入 Pipeline |
| **SDF Upload** | 创建化合物库记录 → 同步 `molecules/sdf/` 目录 → 将分子载入 Pipeline |

### 流程四 B：虚拟筛选（分步页面）

1. 进入 `/workflow/virtual-screening`
2. 勾选 TAME-VS / DrugCLIP / GLARE 之一并运行：

| 模型 | 网页行为 |
|------|----------|
| **TAME-VS** | 检查 Docker → `smoke-test` → 结果转 SDF 入库 → 载入 Pipeline |
| **DrugCLIP** | 检查 Docker → 自动启服务 → `pipeline-screen` → 入库 → 载入 Pipeline |
| **GLARE** | 将 Pipeline 分子桥接为 `evaluated.xlsx` → 使用最新 checkpoint 执行 `query` 筛选 |

### 流程四 C：候选排序（分步页面）

1. 进入 `/workflow/candidate-rank`
2. 使用 Pipeline 中的 ADMET + 对接/筛选分数进行正交重排序

### 流程四 D：强化学习训练（分步页面）

1. 进入 `/workflow/rl-training`
2. 在 Step 6 排序完成后，选择 **GLARE Train**（含 seed reinforce + train）或单独 **Seed / Wet-lab Reinforce**
3. 训练完成后 checkpoint 写入 `backend/outputs/rl_rounds/round_{id}/`，供**下一轮** Step 3 GLARE 筛选使用
4. 上传 wet-lab pDC50 xlsx 后，可触发 **Wet-lab Reinforce**

### 流程五：一键 Pipeline（推荐体验完整链路）

1. 打开 http://localhost:3000/workflow ，滚动到 **One-Click Pipeline**
2. **Step 1 靶点**：输入 PDB ID，选择下载/上传方式
3. **Step 2 库构建**：`DiffGUI`（5 分子）或 `SDF Upload`
4. **Step 3 虚拟筛选**：`TAME-VS` / `DrugCLIP` / `GLARE`（首轮无 checkpoint 时 GLARE 自动跳过）
5. **Step 4–5**：ADMET 过滤、亲和力估算
6. **Step 6**：正交排序
7. **Step 7 RL 训练**：GLARE seed reinforce + train，产出下一轮筛选 checkpoint

> **测试规模约定**：生成 `num_mols=5`，评估 `max_samples=5`，Vina 超时 20s（DiffDynamic 对接场景）。

### 流程六：DrugCLIP 仅 API 调用

```bash
# 1. 查看状态（docker_available、service_healthy、package_path）
curl http://localhost:8000/api/v1/drugclip/status

# 2. 启动容器（WSL 内 docker compose up -d）
curl -X POST http://localhost:8000/api/v1/drugclip/service/start \
  -H "Content-Type: application/json" -d "{}"

# 3. 容器健康（直连 8500）
curl http://localhost:8500/health

# 4. 冒烟测试：3 分子 + 4HHB，结果写入 molecules/sdf/drugclip/ 并 sync 入库
curl -X POST http://localhost:8000/api/v1/drugclip/smoke-test

# 5. 按 PDB ID 跑 pipeline 小库筛选（与网页一键 Pipeline Step2-DrugCLIP 相同）
curl -X POST http://localhost:8000/api/v1/drugclip/pipeline-screen \
  -H "Content-Type: application/json" \
  -d '{"target_pdb_id": "4HHB", "top_k": 10, "auto_ingest": true}'

# 6. 通用筛选（路径必须是容器内路径，如 /app/work/xxx.sdf）
curl -X POST http://localhost:8000/api/v1/drugclip/screen \
  -H "Content-Type: application/json" \
  -d '{
    "sdf_path": "/app/work/smoke_library.sdf",
    "pocket_pdb_path": "/app/work/smoke.pdb",
    "top_k": 10,
    "ingest": true
  }'

# 7. 停止服务
curl -X POST http://localhost:8000/api/v1/drugclip/service/stop \
  -H "Content-Type: application/json" -d "{}"
```

### 流程七：TAME-VS 仅 API 调用

```bash
# 1. 状态
curl http://localhost:8000/api/v1/tame-vs/status

# 2. 启动 / 停止 / 重启 Compose 服务
curl -X POST http://localhost:8000/api/v1/tame-vs/service/start
curl -X POST http://localhost:8000/api/v1/tame-vs/service/stop
curl -X POST http://localhost:8000/api/v1/tame-vs/service/restart

# 3. 服务健康
curl http://localhost:8000/api/v1/tame-vs/service/health

# 4. 冒烟测试（小库，结果 ingest 到分子库）
curl -X POST http://localhost:8000/api/v1/tame-vs/smoke-test

# 5. Enamine 50K 全库筛选（网页一键 Pipeline 选 TAME-VS 时调用）
curl -X POST http://localhost:8000/api/v1/tame-vs/full-50k-screen \
  -H "Content-Type: application/json" \
  -d '{"top_percent": 2.0, "target_pdb_id": "8V1T", "auto_ingest": true}'

# 6. 准备自定义 CSV 指纹库
curl -X POST http://localhost:8000/api/v1/tame-vs/prepare-library \
  -H "Content-Type: application/json" \
  -d '{
    "input_csv": "E:/path/to/library.csv",
    "output_name": "my_library_fp",
    "smiles_col": 1,
    "compound_id_col": 2,
    "auto_ingest": true
  }'

# 7. 手动导入已有 CSV 结果
curl -X POST http://localhost:8000/api/v1/tame-vs/ingest-results \
  -H "Content-Type: application/json" \
  -d '{"result_csv": "E:/path/to/scores.csv", "sdf_name": "tame_vs_results.sdf"}'

# 8. 构建 Docker 镜像（首次或更新后）
curl -X POST http://localhost:8000/api/v1/tame-vs/build-image \
  -H "Content-Type: application/json" -d '{}'
```

### 流程八：通过 API 使用（其他接口）

使用 curl 或任何 HTTP 客户端直接调用 API：

```bash
# 查看所有分子（第 1 页，每页 20 条）
curl http://localhost:8000/api/v1/molecule-db/molecules?page=1&page_size=20

# 按分子量范围过滤
curl "http://localhost:8000/api/v1/molecule-db/molecules?min_mw=150&max_mw=500"

# 同步 SDF 文件
curl -X POST http://localhost:8000/api/v1/molecule-db/sync \
  -H "Content-Type: application/json" \
  -d '{"sdf_directory": "E:/e-drug-lab/molecules/sdf"}'

# 获取统计信息
curl http://localhost:8000/api/v1/molecule-db/stats

# 正交重排序
curl -X POST http://localhost:8000/api/v1/ranking/orthogonal-rescore \
  -H "Content-Type: application/json" \
  -d '{
    "candidates": [
      {
        "molecule_id": "mol-1",
        "name": "Candidate A",
        "metrics": [
          {"metric_name": "docking", "value": -8.5, "model_name": "vina", "method_family": "docking"},
          {"metric_name": "mmgbsa", "value": -35.0, "model_name": "mmgbsa", "method_family": "physics"}
        ]
      }
    ],
    "primary_metric": "docking",
    "orthogonal_metric": "mmgbsa"
  }'

# 下载 PDB 结构
curl -X POST http://localhost:8000/api/v1/targets/download \
  -H "Content-Type: application/json" \
  -d '{"pdb_id": "4HHB"}'
```

---

## API 接口说明

所有 API 路径前缀为 `/api/v1/`，完整的 Swagger 文档访问：http://localhost:8000/docs

### 分子数据库 `/api/v1/molecule-db`

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/molecules` | 分子列表（分页/排序/过滤/搜索） |
| GET | `/molecules/{id}` | 分子详情 |
| DELETE | `/molecules/{id}` | 删除分子记录 |
| POST | `/sync` | 同步 SDF 文件到数据库 |
| GET | `/sync/status` | 同步状态 |
| GET | `/stats` | 统计信息（avg MW, LogP, QED, TPSA） |

**查询参数（GET /molecules）：**

| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码（默认 1） |
| page_size | int | 每页条数（默认 50，最大 200） |
| sort_by | string | 排序字段（molecular_weight, logp, qed, tpsa 等） |
| sort_order | string | asc 或 desc |
| search | string | 搜索关键词 |
| min_mw / max_mw | float | 分子量范围 |
| min_logp / max_logp | float | LogP 范围 |
| min_qed | float | QED 最小值 |
| sdf_filename | string | SDF 文件名过滤 |

### 靶点管理 `/api/v1/targets`

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 靶点列表 |
| POST | `/` | 创建靶点 |
| GET | `/{id}` | 靶点详情 |
| POST | `/download` | 从 RCSB 下载 PDB |
| POST | `/predict` | AlphaFold 预测（占位） |
| POST | `/{id}/preprocess` | 预处理 |

### 分子库管理 `/api/v1/libraries`

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 库列表 |
| POST | `/` | 创建库 |
| POST | `/upload` | 上传 SDF 文件 |
| GET | `/{id}` | 库详情 |
| POST | `/{id}/filter` | 应用过滤规则 |

### 正交排序 `/api/v1/ranking`

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/orthogonal-rescore` | 正交重打分排名 |
| GET | `/orthogonal-demo` | Demo 数据演示 |

### TAME-VS `/api/v1/tame-vs`

通过 Windows **WSL2** 调用 Docker，运行 Target-driven ML 虚拟筛选。筛选结果会转为 SDF 并调用 `sync_sdf_library` 写入分子库。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/status` | Docker / 服务状态（`docker_available`、`service_healthy`） |
| GET | `/service/health` | 探测 TAME-VS 容器 HTTP 健康 |
| POST | `/service/start` | `docker compose up -d` |
| POST | `/service/stop` | `docker compose down` |
| POST | `/service/restart` | 先 stop 再 start |
| POST | `/build-image` | 构建 `target-driven-vs-api` 镜像 |
| POST | `/smoke-test` | 小库冒烟测试 + 可选入库 |
| POST | `/full-50k-screen` | Enamine 50K 筛选（`top_percent`、`target_pdb_id`、`auto_ingest`） |
| POST | `/prepare-library` | 从 CSV 生成 Morgan 指纹库 |
| POST | `/ingest-results` | 将已有 CSV 结果转 SDF 并入库 |

**`POST /full-50k-screen` 请求体示例：**

```json
{
  "top_percent": 2.0,
  "target_pdb_id": "8V1T",
  "auto_ingest": true
}
```

**网页对应关系：**

| 接口 | 网页入口 |
|------|----------|
| `smoke-test` | `/workflow/virtual-screening` → 勾选 TAME-VS → Run selected |
| `full-50k-screen` | API 直接调用（一键 Pipeline 默认使用 smoke-test 规模） |

### DrugCLIP `/api/v1/drugclip`

通过 WSL2 Docker 运行对比学习虚拟筛选服务（默认 `http://localhost:8500`）。宿主机会把 SDF/PDB 复制到 `deliverables/drugclip-package/work/`，再以容器内路径 `/app/work/...` 调用筛选。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/status` | Docker、服务、包路径状态 |
| GET | `/service/health` | 代理探测容器 `/health` |
| POST | `/service/start` | `docker compose up -d`（body 可带 `package_path`） |
| POST | `/service/stop` | `docker compose down` |
| POST | `/smoke-test` | 内置 3 分子（阿司匹林/布洛芬/咖啡因）+ 4HHB 口袋，筛选并入库 |
| POST | `/pipeline-screen` | 按 PDB ID 下载/缓存口袋，跑小库筛选并入库 |
| POST | `/screen` | 通用筛选（**必须**传容器内 `sdf_path`、`pocket_pdb_path`） |

**`POST /pipeline-screen` 请求体：**

```json
{
  "target_pdb_id": "4HHB",
  "top_k": 10,
  "auto_ingest": true
}
```

**`POST /screen` 请求体：**

```json
{
  "sdf_path": "/app/work/smoke_library.sdf",
  "pocket_pdb_path": "/app/work/smoke.pdb",
  "top_k": 10,
  "pocket_center": null,
  "pocket_radius": 10.0,
  "ingest": true
}
```

**入库说明**：`ingest=true` 时，结果写入 `molecules/sdf/drugclip/*.sdf`，并 `sync` 到 `sdf_molecules` 表。容器仅返回 `name` + `score`；内置冒烟库通过分子名映射 SMILES，**自定义大库可能出现 `converted_molecules: 0`**。

**网页对应关系：**

| 接口 | 网页入口 |
|------|----------|
| `smoke-test` | `/workflow/virtual-screening` → 勾选 DrugCLIP → Run selected |
| `pipeline-screen` | `/workflow` → One-Click Pipeline → Step 3 选 DrugCLIP |
| `service/start` | 上述页面在 `service_healthy=false` 时自动调用 |

**使用前检查：**

```bash
wsl -d eDrugUbuntu docker ps          # 应有 drugclip-api
curl http://localhost:8500/health    # {"status":"ok",...}
curl http://localhost:8000/api/v1/drugclip/status
```

### DiffGUI `/api/v1/diffgui`

通过本地 **conda `diffgui_new`** 子进程调用 `/data/ye/diffgui/scripts/run_batch_generate.py`，用于 Step 2 化合物库构建。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/status` | 检查 diffgui 根目录、conda 环境、配置与脚本 |
| POST | `/generate` | 启动批量生成（默认 `async_run=true`，返回 `job_id`） |
| GET | `/jobs/{job_id}` | 查询生成任务状态 |
| POST | `/ingest` | 将 `round_{id}_all.sdf` 复制到 `molecules/sdf/diffgui/` 并 sync 入库 |

**`POST /generate` 请求体示例（测试规模）：**

```json
{
  "round_id": 1,
  "protein_path": "/data/ye/diffgui/data/vav1/vav1_protein.pdb",
  "num_mols": 5,
  "batch_size": 5,
  "require_achiral": true,
  "async_run": true
}
```

也可传 `target_id`（使用已预处理靶点的 `structure_path`）。

**网页对应关系：**

| 接口 | 网页入口 |
|------|----------|
| `generate` + `ingest` | `/workflow/library-build` → 勾选 DiffGUI |
| `generate` | `/workflow` → One-Click Pipeline → Step 2 选 DiffGUI |

### GLARE `/api/v1/glare`

封装 `/data/ye/diffgui/glare_selector/` 下的 train / query / reinforce 脚本。Pipeline 分子经 `pipeline_eval_bridge` 转为 `evaluated.xlsx`（含 `canonical_smiles` 等 GLARE 所需列）。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/status` | 配置、数据库、checkpoint 列表 |
| POST | `/screen` | 虚拟筛选（`train_glare_policy.py query`） |
| POST | `/train` | RL 训练（seed reinforce / wet-lab reinforce / train） |
| POST | `/import-wetlab` | 上传 pDC50 xlsx（multipart，`round_id` 查询参数） |
| GET | `/jobs/{job_id}` | 查询异步任务 |

**`POST /screen` 请求体：**

```json
{
  "round_id": 1,
  "pipeline_molecules": [{"id": "mol-1", "smiles": "CCO", "properties": {"qed": 0.5}}],
  "top_n": 50,
  "checkpoint": null
}
```

`checkpoint` 省略时自动选取最新 checkpoint；首轮 Step 3 GLARE 可跳过，需先完成 Step 7 训练后下一轮筛选才可用 checkpoint。

**`POST /train` 请求体：**

```json
{
  "round_id": 1,
  "pipeline_molecules": [],
  "run_seed_reinforce": true,
  "run_train": true,
  "wetlab_file": null
}
```

### RL 轮次 `/api/v1/rl-rounds`

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 历史轮次列表 |
| POST | `/` | 创建轮次 `{round_id, target_id, config_snapshot}` |
| GET | `/{round_id}` | 轮次详情与 `step_log` |
| POST | `/{round_id}/advance` | 写入步骤日志 |

产物目录：`backend/outputs/rl_rounds/round_{id}/`（含 `evaluated.xlsx`、checkpoint、排名 CSV）。

> **注意**：`vav1_molecular_glue_screening.db` 为只读/追加，集成代码不会删除该库。

---

## 配置说明

配置文件为 `backend/.env`，使用 `__` 作为嵌套分隔符。

### 数据库配置

```env
database__url=sqlite:///./edrug_lab_dev.db   # SQLite 开发库
database__pool_size=10
database__echo=false                          # 设为 true 打印 SQL 日志
```

切换到 PostgreSQL：

```env
database__url=postgresql://user:password@localhost:5432/edrug_lab
```

### 外部 API 配置（可选）

```env
schrodinger__api_key=your-key
diffdynamic__api_key=your-key
```

缺少这些配置不影响启动，仅在调用对应功能时会报错。

### DrugCLIP 配置（WSL + Docker）

```env
drugclip__wsl_distro=eDrugUbuntu
drugclip__package_path=deliverables/drugclip-package
drugclip__service_url=http://localhost:8500
drugclip__image_name=drugclip-api:latest
drugclip__output_dir=outputs/drugclip
drugclip__timeout=600
```

包路径相对于仓库根目录 `e-drug-lab/`。首次使用需在 WSL 中构建镜像：

```bash
wsl -d eDrugUbuntu
cd /mnt/e/e-drug-lab/deliverables/drugclip-package
docker build -t drugclip-api:latest .
docker compose up -d
```

### DiffGUI / GLARE 配置（本地 conda）

```env
diffgui__root=/data/ye/diffgui
diffgui__conda_env=diffgui_new
diffgui__sample_config=configs/sample/sample.yml
diffgui__default_device=cuda:0

glare__root=/data/ye/diffgui
glare__config_path=glare_selector/glare_config.yaml
glare__db_path=vav1_molecular_glue_screening.db
glare__seed_activity_file=data/seed/seed_activity_data.xlsx
glare__conda_env=diffgui_new
```

DiffGUI/GLARE 子进程与 edrug 后端环境隔离，避免 torch/rdkit 版本冲突。`diffgui_new` 环境需安装 `openpyxl`（读写 xlsx）。

### TAME-VS 配置（WSL + Docker）

```env
tame_vs__wsl_exe=C:\Windows\System32\wsl.exe
tame_vs__wsl_distro=eDrugUbuntu
tame_vs__repo_path=tools/Target-driven-ML-enabled-VS
tame_vs__package_path=deliverables/target-driven-vs-package
tame_vs__image_name=edrug-lab/tame-vs:latest
tame_vs__service_url=http://localhost:8001
tame_vs__output_dir=outputs/tame-vs
tame_vs__timeout=600
```

> `tame_vs__service_url` 应与 TAME-VS 容器映射端口一致，**不要**与后端 FastAPI 的 `8000` 冲突。若未单独部署容器服务，可先使用 `smoke-test` / `prepare-library` 等不依赖 HTTP 推理的路径。

### 本地工具路径（可选）

```env
tool_paths__autodock_vina=C:\tools\vina\vina.exe
tool_paths__fpocket=C:\tools\fpocket\fpocket.exe
tool_paths__rdkit_data=C:\tools\rdkit\Data
```

### 应用配置

```env
APP_DEBUG=true          # 开发模式
APP_HOST=0.0.0.0
APP_PORT=8000
APP_LOG_LEVEL=INFO
APP_LOG_FORMAT=text     # 改为 json 输出结构化日志
CORS_ORIGINS=http://localhost:3000
```

---

## 常见问题

### Q: 后端启动报错 "database.url is required"

确认 `.env` 文件存在且包含 `database__url=sqlite:///./edrug_lab_dev.db`。

### Q: 前端页面显示 "offline"

1. 确认后端已在 8000 端口运行：`curl http://localhost:8000/health`
2. 确认 CORS 配置包含 `http://localhost:3000`

### Q: Sync 后分子列表为空

1. 确认 `molecules/sdf/` 目录下有 `.sdf` 文件
2. 检查后端日志是否有解析错误
3. 尝试指定 SDF 目录：`curl -X POST .../sync -d '{"sdf_directory": "/absolute/path/to/sdf"}'`

### Q: RDKit 导入报错 "AttributeError: _ARRAY_API not found"

这是 NumPy 2.x 与 RDKit 版本不兼容的警告，不影响功能。如需消除：

```bash
pip install "numpy<2"
```

### Q: TAME-VS 功能不可用

TAME-VS 需要 WSL2 和 Docker：

1. 确认 WSL：`wsl --list --verbose`（默认发行版 `eDrugUbuntu`）
2. 确认 Docker：`wsl -d eDrugUbuntu docker --version`
3. 查看状态：`curl http://localhost:8000/api/v1/tame-vs/status`
4. 若镜像缺失： `POST /api/v1/tame-vs/build-image`
5. 启动服务：`POST /api/v1/tame-vs/service/start`

清过 Docker 存储后需重新 build 镜像。

### Q: DrugCLIP smoke-test / pipeline-screen 失败

1. **容器未运行**

   ```bash
   wsl -d eDrugUbuntu docker ps
   curl http://localhost:8500/health
   ```

   失败则：`curl -X POST http://localhost:8000/api/v1/drugclip/service/start -d {}`

2. **`package_exists: false`** — 检查 `deliverables/drugclip-package` 是否在仓库根目录

3. **`Torch not compiled with CUDA enabled`** — `docker-compose.yml` 要求 GPU，但镜像 Dockerfile 默认安装 CPU 版 PyTorch。需重建带 CUDA 的镜像，或调整 compose 为 CPU 模式（性能受限）

4. **`converted_molecules: 0`** — 筛选结果无 SMILES，仅内置 3 个冒烟分子名可映射；自定义库需扩展容器 API 或后端映射逻辑

5. **`wsl --shutdown` 后** — 需重新 `docker compose up -d`

### Q: 网页 Pipeline 里 DrugCLIP / TAME-VS 报错

- 确认后端 (8000) 与前端 (3000) 均已启动
- 一键 Pipeline Step 2 选 DrugCLIP 前，Step 1 填好 PDB ID
- 服务启动后约等待 15 秒再筛选（页面已内置等待，过短可手动再点 Run）
- 打开浏览器开发者工具 → Network，查看 `/api/v1/drugclip/*` 或 `/api/v1/tame-vs/*` 返回 JSON

### Q: 如何添加自己的分子

1. 将 `.sdf` 文件放入 `molecules/sdf/` 目录
2. 在数据库页面点击 **Sync** 按钮
3. 或通过 API：`POST /api/v1/molecule-db/sync`

### Q: 如何查看 API 文档

启动后端后，访问 http://localhost:8000/docs 查看 Swagger UI。
