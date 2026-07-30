# 工具运行环境与 conda 调用方案

> 2026-06-20 整理。e-drug-lab 五个外部工具的运行环境与调用方式决策。

## 决策（用户确认）

全 conda 路线，**保留原 `*_docker.py` 代码作为 Windows/Docker 备用，API 默认走 conda**。

| 工具 | conda 环境 | 状态 | runner |
|------|-----------|------|--------|
| DiffDynamic | `diffdynamic` | ✅ 现成（torch 2.4.1, CUDA True）| `DiffDynamicRunner` ✅ |
| DiffGUI | `diffgui_new` | ✅ 现成（已用 conda）| `DiffGuiRunner`（路径配置化）|
| GLARE | `diffgui_new` | ✅ 现成（与 DiffGUI 共用）| `GlareRunner`（路径配置化）|
| TAME-VS | `/data/ye/envs/TAME_VS2` | ✅ 已建（py3.9+torch2.4.1cu118+PyG+rdkit）| `TameVSCondaRunner` ✅ |
| DrugClip | `drugclip`（新建）| ❌ 待建 | 新建 conda runner |

## 关键事实

- **conda 路径**：`/home/user/anaconda3/bin/conda`。`conda_runner.find_conda()` 自动发现。
- **磁盘**：原 25G，`conda clean --all` 回收后 56G。pkgs 缓存曾占 62G。
- **DiffDynamic 入口**（`/data/ye/DiffDynamic/`）：`batch_sampleandeval_parallel.py`（dynamic）、`run_prudent_generations.py`（prudent）、`evaluate_pocket_quality.py`（评估）、`configs/sampling.yml`。env `diffdynamic` 可用。
- **TAME-VS 环境坑**：旧 `TAME_VS`/`qlj_tamevs1` 是 Python 3.7 且无 torch，跑不了 GNN 阶段。**按官方 README 新建 `TAME_VS2`（Python 3.9）**，建在数据盘 `/data/ye/envs/TAME_VS2`（按路径 `-p`，见磁盘策略）。
  - PyTorch 2.4.1+cu118（与 diffdynamic 一致，RTX 5880 Ada 算力 8.9 已验证可用）。
  - **torch_scatter/sparse/cluster 必须用 PyG 官方预编译 wheel**：`pip install torch_scatter torch_sparse torch_cluster torch_geometric -f https://data.pyg.org/whl/torch-2.4.0+cu118.html`。源码编译会因系统 CUDA 12.2 ≠ torch cu118 失败。装上的是 torch_scatter 2.1.2+pt24cu118 / torch_geometric 2.6.1。TAME-VS GNN 模型硬依赖 `from torch_scatter import scatter_add`。
  - **numpy 必须锁 1.26.4**（requirements.txt 要求）：装 torch 会带入 numpy 2.x，与 rdkit-pypi 2022.9.5 不兼容，需显式降级。
  - 官方仓库 = `bymgood/TAME-VS-2.0`，本地 `tools/Target-driven-ML-enabled-VS` 即此仓库。7 阶段流水线见 `Starting_point_1.sh`（CRLF 编码）。
  - **ChEMBL SQLite**：本地找到 `chembl_35.db`（25G，有效，249 万分子），复制到数据盘 `/data/ye/tame-vs-data/chembl/chembl_35.db`。TAME-VS 代码用 ChEMBL 35 完全够（标准表结构，requirements 未锁版本）。通过 `Compound_retrieving.py -d <db_path>` 传入。
- **DrugClip**：本身是个 FastAPI 服务（`uvicorn app.api_server:app` 端口 8500），原 docker runner 通过 HTTP 调用。conda 方案：在 `drugclip` 环境直起 uvicorn，同样 HTTP 调用。依赖 torch(CPU)、rdkit-pypi 2022.9.5、lmdb、**unicore 需从本地 `code/unicore` 编译**、unimol 本地目录。模型权重 `deliverables/drugclip-package/models/checkpoint_best.pt`。
- **DrugClip**：本身是个 FastAPI 服务（`uvicorn app.api_server:app` 端口 8500），原 docker runner 通过 HTTP 调用。conda 方案：在 `drugclip` 环境直起 uvicorn，同样 HTTP 调用。依赖 torch(CPU)、rdkit-pypi 2022.9.5、lmdb、**unicore 需从本地 `code/unicore` 编译**、unimol 本地目录。模型权重 `deliverables/drugclip-package/models/checkpoint_best.pt`。

## 统一抽象（Task 1 已完成）

- `backend/app/services/conda_runner.py`：`find_conda()` / `conda_run()` / `conda_run_json()` / `conda_env_exists()` / `set_conda_exe()`。conda 路径可经 `tool_paths.conda_exe` 配置覆盖。
- `backend/app/services/tool_runner_base.py`：`CondaToolRunner` 基类，子类声明 `conda_env`+`root`，调 `self._run()`。
- `config.py` 新增字段：`ToolPathsSettings.conda_exe`；`DrugClipSettings.runtime/conda_env`；`TameVSSettings.runtime/conda_env`；`DiffDynamicSettings.runtime/conda_env/root/sampling_config/default_device/outputs_dir`。原 wsl/docker 字段保留备用。

## 既有 bug（已修）

- **`.env` 加载 `schrodinger` 字段报 JSONDecodeError**：根因是 os 环境有裸变量
  `SCHRODINGER=/opt/schrodinger2023-3/`（薛定谔套装安装路径），被 pydantic-settings
  当作 `schrodinger` 嵌套字段的裸值去 `json.loads`。修法：`config.get_settings()` 构造
  时临时 pop 裸 `SCHRODINGER`（backend 不消费它），构造后恢复。其他字段无裸变量碰撞故无碍。
  backend python 环境 = conda env `edrug`（含 pydantic-settings 2.5、fastapi）。FastAPI app 87 路由可正常加载。

## 测试规则（DiffDynamic，来自 CLAUDE.md）

`batch_size=5`、`max_samples=5`、`vina_timeout=20`、自动链式、**永不删 diffdynamic.db**。
