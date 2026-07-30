# e-drug-lab 实施计划

> 基于 `docs/CODE_REVIEW.md` 审查结论与项目当前 ~45% 完整度制定
> 最后更新：2026-05-27
>
> 标记说明：`- [ ]` 未完成，`- [x]` 已完成

---

## 阶段一：基础设施修复（P0 — 阻塞性问题）

> 目标：让后端能正确启动、数据库能正确连接、核心数据通路能跑通。

### 1.1 数据库 Session 生命周期重构
- **审查编号**: #F
- **文件**: `backend/app/main.py`, `backend/app/api/routes/molecule_db.py`
- **依赖**: 无
- **任务**:
  - [x] 创建 `backend/app/db.py`，实现 `get_db()` generator（每请求创建/关闭 session）
  - [x] SQLite 路径使用 `create_engine` + `SessionLocal`，保持同步
  - [x] PostgreSQL 路径预留 `create_async_engine` + `AsyncSession` 接口（暂不实现）
  - [x] `main.py` lifespan 中只创建 engine + sessionmaker，不再持有 session
  - [x] `main.py` lifespan 中添加 `yield` 后关闭 session 的 cleanup 逻辑
  - [x] `molecule_db.py` 所有路由函数签名改为 `db: Session = Depends(get_db)`
  - [x] `tame_vs.py` 的 `_db()` 函数改为使用 `Depends(get_db)`
  - [x] `sdf_sync.py` 调用方传入 session 而非从 app.state 获取

### 1.2 SDF 同步策略重写
- **审查编号**: #G, #H
- **文件**: `backend/app/services/sdf_sync.py`
- **依赖**: 1.1
- **任务**:
  - [x] 不再 `db.query(SDFMolecule).all()` 加载全部记录，改为只查询 hash 集合
  - [x] 同步策略改为基于 `(sdf_file_path, conformer_index)` 的 upsert
  - [x] 文件存在 + hash 相同 → 跳过
  - [x] 文件存在 + hash 不同 → 删除该文件旧记录，重新解析插入
  - [x] 文件不存在 + hash 存在于 db → 删除 orphan
  - [x] 新文件 → 解析插入
  - [x] 分批 commit（每 100 条 conformer），避免大事务

### 1.3 SDF 扫描性能优化
- **审查编号**: #L
- **文件**: `backend/app/services/sdf_parser.py`, `backend/app/repositories/models.py`
- **依赖**: 1.2
- **任务**:
  - [ ] `scan_sdf_directory` 返回值增加 `file_mtime` 字段
  - [ ] `SDFMolecule` 模型增加 `file_mtime` 列
  - [ ] 同步时先比较 size + mtime，两者都匹配则跳过 SHA-256 计算
  - [ ] 更新 `database/init.sql` 添加 `file_mtime` 列

### 1.4 配置系统宽松化
- **审查编号**: #O
- **文件**: `backend/app/config.py`, `backend/.env.example`
- **依赖**: 无
- **任务**:
  - [x] `SchrodingerSettings.api_key` → `Optional[str] = None`
  - [x] `DrugClipSettings.api_key` → `Optional[str] = None`
  - [x] `DiffDynamicSettings.api_key` → `Optional[str] = None`
  - [x] `ToolPathsSettings.autodock_vina` → `Optional[str] = None`
  - [x] `ToolPathsSettings.fpocket` → `Optional[str] = None`
  - [x] `ToolPathsSettings.rdkit_data` → `Optional[str] = None`
  - [x] `database.url` 保留必填（无数据库无法启动）
  - [x] 使用时检查 `if config.api_key is None: raise ConfigurationError(...)`
  - [x] `.env.example` 中标注哪些是可选的
  - [x] 验证修改后 `.env` 缺少可选项时应用能正常启动

---

## 阶段二：核心业务路由实现（P1 — 功能缺失）

> 目标：让靶点管理、分子库管理、筛选任务不再是空壳，能走通基本 CRUD。

### 2.1 靶点管理 CRUD 接入数据库
- **文件**: `backend/app/api/routes/targets.py`
- **依赖**: 1.1
- **任务**:
  - [x] `list_targets` → 查询 `targets` 表，支持分页和 source 过滤
  - [x] `create_target` → 插入 `targets` 表，关联 project_id
  - [x] `get_target` → 按 id 查询，404 时返回 `TargetNotFoundError`
  - [x] `download_target` → 调用 RCSB PDB 下载结构文件，存入 `structure_path`，更新 status
  - [x] `predict_structure` → 入 Celery 队列（占位，后续实现 AlphaFold）
  - [x] `preprocess_target` → 调用 tool_manager 执行预处理

### 2.2 分子库管理 CRUD 接入数据库
- **文件**: `backend/app/api/routes/libraries.py`
- **依赖**: 1.1
- **任务**:
  - [x] `list_libraries` → 查询 `compound_libraries` 表，支持分页
  - [x] `create_library` → 插入记录
  - [x] `upload_library` → 接收 SDF/CSV 文件，存入本地路径，解析分子数
  - [x] `get_library` → 按 id 查询
  - [x] `filter_library` → 基于 `LibraryFilterRequest` 的条件过滤

### 2.3 combined_routes 拆分重构
- **文件**: `backend/app/api/routes/combined_routes.py`
- **依赖**: 1.1
- **任务**:
  - [x] 拆分为独立文件：`screening.py`
  - [x] 拆分为独立文件：`admet.py`
  - [x] 拆分为独立文件：`affinity.py`
  - [x] 拆分为独立文件：`molecules.py`
  - [x] 拆分为独立文件：`tasks.py`
  - [ ] 未实现的路由返回 `501 Not Implemented`
  - [x] 更新 `main.py` 中的 import 和 router 注册

### 2.4 molecule_db 序列化统一
- **审查编号**: #I
- **文件**: `backend/app/api/routes/molecule_db.py`, `backend/app/repositories/models.py`
- **依赖**: 1.1
- **任务**:
  - [x] 创建 `to_dict()` / `_serialize_molecule()` 统一序列化方法
  - [x] `list_molecules` 使用统一序列化方法
  - [x] `get_molecule` 使用统一序列化方法

### 2.5 列表查询 count 优化
- **审查编号**: #K
- **文件**: `backend/app/api/routes/molecule_db.py`
- **依赖**: 1.1
- **任务**:
  - [ ] 探索 window function 方案：`func.count().over()` 与主查询合并
  - [ ] 或标注 TODO：当前数据量小，待大库时优化

---

## 阶段三：科学计算质量加固（P1 — 正确性验证）

> 目标：保证正交重打分、SDF 解析等科学计算的正确性。

### 3.1 正交重打分算法调优
- **审查编号**: #C
- **文件**: `backend/app/services/orthogonal_scoring.py`
- **依赖**: 无
- **任务**:
  - [x] 对 `artifact_flag=True` 的分子施加额外惩罚（`final_score *= 0.3` 或归零）
  - [x] 考虑非线性惩罚：`penalty = max(0.0, gap - threshold) ** 2 * weight`
  - [x] 添加 direction 一致性校验到 `select_representative_metric`
  - [x] 补充 docstring 说明 `gap_threshold=35.0` 的来源
  - [x] 补充 docstring 说明 `penalty_weight=0.65` 的来源

### 3.2 后端单元测试 — 正交重打分
- **文件**: `backend/tests/test_orthogonal_scoring.py`
- **依赖**: 3.1
- **任务**:
  - [x] `test_desirability_lower_is_better` — 验证越小越好方向的 percentile 转换
  - [x] `test_desirability_higher_is_better` — 验证越大越好方向
  - [x] `test_select_preferred_model` — 验证优先模型选择
  - [x] `test_select_median_observed_value` — 验证非优先时取中位数观测值
  - [x] `test_artifact_detection` — 验证 gap > threshold 时正确标记
  - [x] `test_artifact_extra_penalty` — 验证修复后的额外惩罚
  - [x] `test_single_candidate_edge_case` — 单个候选的 edge case
  - [x] `test_all_artifacts_edge_case` — 所有候选都是 artifact
  - [x] 全部测试通过（16/16）

### 3.3 后端单元测试 — SDF 解析
- **文件**: `backend/tests/test_sdf_parser.py`
- **依赖**: 无
- **任务**:
  - [x] 用 `aspirin.sdf` 验证 MW ≈ 180.16
  - [x] 用 `aspirin.sdf` 验证 LogP ≈ 1.2
  - [x] 用 `ibuprofen.sdf` 验证 MW ≈ 206.28
  - [x] 用 `ibuprofen.sdf` 验证 LogP ≈ 3.5
  - [x] 验证 InChIKey 一致性
  - [x] 验证多构象 SDF 文件的 conformer index
  - [x] 验证损坏 SDF 文件的错误处理
  - [x] 全部测试通过（11/11）

### 3.4 后端单元测试 — SDF 同步
- **文件**: `backend/tests/test_sdf_sync.py`
- **依赖**: 1.2
- **任务**:
  - [ ] 验证新文件插入
  - [ ] 验证未变文件跳过
  - [ ] 验证修改文件的 hash 更新
  - [ ] 验证删除文件的 orphan 清理
  - [ ] 验证大文件场景不 OOM（mock 大数据集）
  - [ ] 全部测试通过

### 3.5 后端单元测试 — csv_to_sdf 转换
- **文件**: `backend/tests/test_tame_vs_docker.py`
- **依赖**: 3.6
- **任务**:
  - [ ] 验证标准 CSV → SDF 转换正确性
  - [ ] 验证缺失 SMILES 行被跳过
  - [ ] 验证无效 SMILES 被跳过
  - [ ] 验证空 CSV 不生成空 SDF 文件
  - [ ] 全部测试通过

### 3.6 修复 csv_to_sdf 空文件问题
- **审查编号**: #N
- **文件**: `backend/app/services/tame_vs_docker.py`
- **依赖**: 无
- **任务**:
  - [x] 先验证 CSV 可读性（检查行数 > 0）
  - [x] 写入后检查 `converted > 0`，否则删除空 SDF 文件

---

## 阶段四：外部工具集成（P2 — 功能增强）

> 目标：让 AutoDock Vina、Fpocket 等工具真正可执行。

### 4.1 ToolManager execute 改为异步
- **审查编号**: #M
- **文件**: `backend/app/services/tool_manager.py`
- **依赖**: 无
- **任务**:
  - [x] 新增 `async_execute()` 方法使用 `asyncio.create_subprocess_exec`
  - [x] 保留 `execute()` 同步方法供 Celery worker 使用
  - [ ] 在 async 路由中使用 `async_execute`，避免阻塞事件循环

### 4.2 AutoDock Vina Docking Worker 实现
- **文件**: `backend/app/workers/docking_worker.py`
- **依赖**: 4.1
- **任务**:
  - [ ] 实现 `run_docking` 中的实际 AutoDock Vina 调用
  - [ ] 使用 `ToolManager.execute()` 执行 vina 命令
  - [ ] 解析 Vina 输出日志提取 docking scores
  - [ ] 将结果写入 `candidate_molecules` 表
  - [ ] 将结果写入 `candidate_metric_values` 表
  - [ ] 进度回调更新 `screening_tasks.progress`

### 4.3 Celery 配置延迟初始化
- **审查编号**: #Q
- **文件**: `backend/app/workers/celery_app.py`
- **依赖**: 无
- **任务**:
  - [x] 将 `settings = get_settings()` 从模块级移到 factory 函数
  - [x] 确保 `pytest` import 不会触发 .env 读取
  - [x] 验证 worker 进程仍能正确初始化

### 4.4 Fpocket 口袋检测集成
- **文件**: `backend/app/services/pocket_detection.py`（新建）
- **依赖**: 4.1
- **任务**:
  - [ ] 创建 `pocket_detection.py` 服务模块
  - [ ] 实现调用 Fpocket 对 PDB 文件执行口袋检测
  - [ ] 解析 Fpocket 输出（pocket 着色 PDB + 信息文件）
  - [ ] 提取 top pocket 坐标和评分
  - [ ] 存入 `targets.binding_site` JSON 字段
  - [ ] 暴露 API: `POST /api/v1/targets/{id}/detect-pockets`

### 4.5 ADMET 预测接口实现
- **文件**: `backend/app/api/routes/admet.py`
- **依赖**: 2.3
- **任务**:
  - [ ] 集成 ADMET 预测模型（本地 RDKit 计算或外部 API）
  - [ ] `POST /api/v1/admet/predict` → 接收 SMILES 列表，返回 ADMET profiles
  - [ ] `POST /api/v1/admet/filter` → 基于 Lipinski Veber 等规则过滤
  - [ ] 结果写入 `candidate_molecules.admet_profile` JSON 字段

### 4.6 MM/GBSA 亲和力评估
- **文件**: `backend/app/api/routes/affinity.py`
- **依赖**: 4.2
- **任务**:
  - [ ] `POST /api/v1/affinity/mmgbsa` → 入 Celery 队列执行 MM/GBSA
  - [ ] `POST /api/v1/affinity/md` → 入 Celery 队列执行 MD 模拟
  - [ ] 结果写入 `candidate_metric_values`（metric_name=mmgbsa_score）
  - [ ] 与正交重打分流程对接

---

## 阶段五：前端完善（P2 — 用户体验）

> 目标：让前端各 workflow 页面不再是静态占位，能与后端真实交互。

### 5.1 前端 i18n 硬编码修复
- **审查编号**: #S
- **文件**: `frontend/src/app/database/page.tsx`, `frontend/src/lib/i18n/translations.ts`
- **依赖**: 无
- **任务**:
  - [x] 详情面板中文标签移入 `translations.ts`（"分子名称"、"分子式"等）
  - [x] 使用 `t()` 函数替代硬编码字符串
  - [x] 验证中英文切换后详情面板正确显示

### 5.2 靶点管理页面实现
- **文件**: `frontend/src/app/workflow/target-prep/page.tsx`
- **依赖**: 2.1
- **任务**:
  - [ ] 靶点列表展示（从 `apiClient.listTargets()` 获取）
  - [ ] 创建靶点表单（PDB ID 输入 / FASTA 序列上传）
  - [ ] PDB 下载按钮
  - [ ] 口袋检测结果显示
  - [ ] 预处理状态展示

### 5.3 分子库管理页面实现
- **文件**: `frontend/src/app/workflow/library-build/page.tsx`
- **依赖**: 2.2
- **任务**:
  - [ ] 分子库列表（从 `apiClient.listLibraries()` 获取）
  - [ ] 创建分子库表单
  - [ ] SDF/CSV 文件上传
  - [ ] 库过滤条件设置（Lipinski、QED 等）

### 5.4 虚拟筛选页面实现
- **文件**: `frontend/src/app/workflow/virtual-screening/page.tsx`
- **依赖**: 2.3, 4.2
- **任务**:
  - [ ] 筛选任务队列展示（Queued / Running / Completed）
  - [ ] 启动筛选表单（选择靶点 + 分子库 + 工具）
  - [ ] 进度条实时更新（轮询 `screening_progress`）
  - [ ] 筛选结果表格展示

### 5.5 ADMET 过滤页面实现
- **文件**: `frontend/src/app/workflow/admet-filter/page.tsx`
- **依赖**: 4.5
- **任务**:
  - [ ] 从静态展示改为交互式表单
  - [ ] 选择候选分子批次
  - [ ] 设置 ADMET 过滤规则（Lipinski violations, hERG risk 等）
  - [ ] 过滤结果展示 + 通过/不通过标记

### 5.6 亲和力评估页面实现
- **文件**: `frontend/src/app/workflow/affinity-eval/page.tsx`
- **依赖**: 4.6
- **任务**:
  - [ ] 选择评估方法（MM/GBSA, MD simulation）
  - [ ] 任务队列展示
  - [ ] 评估结果表格（binding energy, stability）
  - [ ] 与正交排序结果联动

### 5.7 候选排序页面实现
- **文件**: `frontend/src/app/workflow/candidate-rank/page.tsx`
- **依赖**: 3.1
- **任务**:
  - [ ] 选择 primary metric + orthogonal metric
  - [ ] 调用 `apiClient.orthogonalRescore()`
  - [ ] 排名结果表格（含 artifact 标记高亮）
  - [ ] desirability 可视化（柱状图或雷达图）
  - [ ] 导出排名结果（CSV/JSON）

### 5.8 api-client 扩展
- **文件**: `frontend/src/lib/api-client.ts`
- **依赖**: 阶段二、四的后端路由
- **任务**:
  - [x] 补充 `startScreening` 方法 + 类型
  - [x] 补充 `getScreeningProgress` 方法 + 类型
  - [x] 补充 `predictAdmet` 方法 + 类型
  - [x] 补充 `filterAdmet` 方法 + 类型
  - [x] 补充 `optimizeAffinity` 方法 + 类型
  - [x] 补充 `mmgbsa` 方法 + 类型
  - [x] 补充 `runMd` 方法 + 类型
  - [x] 补充 `listTasks` 方法 + 类型
  - [x] 补充 `getTask` 方法 + 类型
  - [x] 补充 `cancelTask` 方法 + 类型
  - [x] 补充 `retryTask` 方法 + 类型

---

## 阶段六：数据工程与迁移（P3 — 可维护性）

> 目标：让 schema 变更可管理，外部 API 客户端不再空壳。

### 6.1 Alembic 初始化
- **审查编号**: #R
- **文件**: `backend/alembic.ini`, `backend/alembic/`
- **依赖**: 无
- **任务**:
  - [x] `alembic init alembic`
  - [x] 配置 `sqlalchemy.url` 从 settings 读取
  - [x] 生成初始 migration：`alembic revision --autogenerate -m "init"`
  - [x] 将 `database/init.sql` 作为 baseline 参考
  - [ ] 更新 `.env.example` 添加 alembic 相关说明

### 6.2 外部 API 客户端实现
- **审查编号**: #P
- **文件**: `backend/app/api/integrations/`
- **依赖**: 无
- **任务**:
  - [ ] `SchrodingerClient` 添加核心方法（或删除空壳）
  - [ ] `DrugClipClient` 添加核心方法（或删除空壳）
  - [ ] `DiffDynamicClient` 添加核心方法（或删除空壳）

### 6.3 API 端点集成测试
- **文件**: `backend/tests/test_api/`
- **依赖**: 1.1, 2.4
- **任务**:
  - [ ] `test_health_check` — GET /health 返回 200
  - [ ] `test_molecule_crud` — 创建/查询/删除分子
  - [ ] `test_molecule_filter` — 分子过滤 + 分页
  - [ ] `test_sync_trigger` — 触发同步并验证结果
  - [ ] `test_orthogonal_rescore_api` — 端到端正交重打分
  - [ ] `test_tame_vs_status` — TAME-VS 状态检查（mock WSL）
  - [ ] 全部测试通过

---

## 阶段七：TAME-VS 管道完善（P2 — 已有基础，需增强）

> 目标：让 TAME-VS 管道能端到端跑通虚拟筛选。

### 7.1 TAME-VS prepare-library 端到端验证
- **文件**: `backend/app/services/tame_vs_docker.py`, `backend/app/api/routes/tame_vs.py`
- **依赖**: 无
- **任务**:
  - [ ] 验证 smoke test 完整流程：CSV → fingerprint → SDF → DB sync
  - [ ] 处理 WSL 路径中的空格和特殊字符
  - [ ] 添加重试机制（WSL Docker 偶发连接失败）
  - [ ] 日志增强：记录每个步骤的耗时

### 7.2 TAME-VS 筛选结果与正交排序对接
- **依赖**: 3.1, 7.1
- **任务**:
  - [ ] TAME-VS fingerprint CSV 解析为 `candidate_metric_values`
  - [ ] 预测分数写入数据库
  - [ ] 与 docking score 组成正交排序对
  - [ ] 端到端验证：TAME-VS → 正交排序 → 排名输出

---

## 阶段八：前端测试与质量（P3）

### 8.1 前端组件测试
- **文件**: `frontend/src/__tests__/`
- **依赖**: 5.1
- **任务**:
  - [ ] 数据库页面：验证过滤、排序、分页交互
  - [ ] API client：验证请求格式和错误处理
  - [ ] i18n：验证语言切换

### 8.2 前端类型安全检查
- **依赖**: 无
- **任务**:
  - [ ] 运行 `npm run typecheck` 修复所有类型错误
  - [ ] 运行 `npm run lint` 修复 lint 问题
  - [ ] 确保 `npm run build` 无警告

---

## 执行顺序总览

```
阶段一 (P0 阻塞)     阶段二 (核心路由)     阶段三 (科学质量)
1.1 DB Session ──────→ 2.1 靶点 CRUD ──────→ 3.1 正交调优
1.2 SDF 同步 ────────→ 2.2 分子库 CRUD       3.2 正交测试
1.3 SDF 扫描优化      2.3 combined_routes    3.3 SDF 解析测试
1.4 配置宽松化 ──────→ 2.4 序列化统一         3.4 SDF 同步测试
                       2.5 count 优化         3.5 csv_to_sdf 测试
                                                3.6 空文件修复

阶段四 (工具集成)     阶段五 (前端)          阶段六 (数据工程)
4.1 异步 execute ───→ 5.1 i18n 修复 ───────→ 6.1 Alembic
4.2 Vina Worker ────→ 5.2 靶点页面           6.2 API 客户端
4.3 Celery 延迟 ────→ 5.3 分子库页面         6.3 集成测试
4.4 Fpocket ────────→ 5.4 筛选页面
4.5 ADMET ──────────→ 5.5 ADMET 页面
4.6 MM/GBSA ────────→ 5.6 亲和力页面
                       5.7 排序页面
                       5.8 api-client

阶段七 (TAME-VS)     阶段八 (前端质量)
7.1 E2E 验证 ───────→ 8.1 组件测试
7.2 对接正交排序      8.2 typecheck + lint
```

**推荐启动顺序**: 1.1 → 1.2 → 1.4 → 2.1 → 2.2 → 2.4 → 3.2 → 3.3
