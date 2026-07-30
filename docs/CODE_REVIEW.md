# e-drug-lab 专业审查报告

> 审查视角：计算药物发现资深科学家 + 系统架构师
> 审查范围：backend/app/ 全部源码、frontend/src/lib/、frontend/src/app/database/
> 审查日期：2026-05-27

---

## 一、科学逻辑与事实正确性

### 1.1 正交重打分算法 — 核心逻辑基本正确，细节需修正

**位置**: `backend/app/services/orthogonal_scoring.py`

**优点**: 正交重打分的理念非常合理 — 利用独立方法（如 MM/GBSA）验证 docking 打分函数的可靠性，对 "scoring-function artifact" 做惩罚，这在计算药物化学中是成熟策略。选取观测值而非均值、desirability 变换等设计体现了良好理解。

**问题 A — desirability 方向翻转有误**

`robust_desirability` 在 `lower_is_better` 时返回 `1.0 - percentile`，但 percentile 的定义是 "有多少值比当前值小"。当 `lower_is_better` 时，值越小越好，一个值排在第 10 百分位（只有 10% 的值比它更小）应该是最高的 desirability，即 90th percentile of desirability。当前代码实际上：`percentile=0.1 → desirability=0.9 → 90`，这个恰好正确。但当 `percentile=0.9`（最差的 10%）→ `desirability=0.1 → 10`，也正确。

再验证一下：排序后 population 为 `[1, 2, 3, 4, 5]`，value=1（最好），below=0, equal=1, percentile=0.1, desirability=0.9 → 90。正确。

**结论**: 方向逻辑是对的。但 `lower_is_better` 时有个隐含假设：所有候选都有相同的 `direction`。如果同一 metric 下不同候选的 direction 不一致，会产生混乱。建议在 `select_representative_metric` 阶段校验 direction 一致性。

**问题 B — gap_threshold 默认值 35.0 缺少科学依据说明**

35% 的 desirability gap 作为 artifact 阈值是合理的经验值，但建议在 docstring 中注明来源或推荐调参范围。药物化学中，如果 docking score 和 MM/GBSA 的 percentile 排序差距超过 30-40%，确实高度提示 scoring artifact，这个值是可接受的。

**问题 C — penalty_weight = 0.65 的线性惩罚是否过于温和？**

```
penalty = max(0.0, gap - 35.0) * 0.65
final_score = max(0.0, orthogonal_desirability - penalty)
```

如果 gap=60（极端 artifact），penalty = 25 * 0.65 = 16.25。一个 orthogonal_desirability=50 的分子仍得 33.75 分。这可能让严重 artifact 分子排名仍然偏高。

**建议**: 考虑非线性惩罚（如二次函数），或在极端情况下直接归零。当前代码 `artifact_flag = gap > gap_threshold and primary_desirability >= 70.0` 标记了 artifact，但 `final_score` 并未对 flag 做额外处理。是否应该对 artifact_flag=True 的分子施加更强惩罚？

### 1.2 SDF 解析 — 科学上基本正确

**位置**: `backend/app/services/sdf_parser.py`

**优点**:
- 使用 `removeHs=False` 读取再 `RemoveHs` 生成 SMILES，保留了氢信息用于属性计算
- `AssignStereochemistry` 是必要的
- 属性计算选择了恰当的 RDKit 描述符

**问题 D — logp 计算可能返回不一致结果**

```python
result.logp = Descriptors.MolLogP(mol)  # 用的是含氢分子
result.tpsa = Descriptors.TPSA(mol)       # 用的是含氢分子
result.qed = QED.qed(mol)                 # 用的是含氢分子
```

但 SMILES 生成用的是 `mol_no_h = Chem.RemoveHs(mol)`。对于大多数分子这不影响 LogP/TPSA/QED（RDKit 内部会处理），但如果 SDF 文件中氢处理不一致（比如有些加了氢、有些没加），含氢 vs 不含氢的 RDKit Mol 对象可能给出不同的 Lipinski 描述符。

**风险**: 低 — RDKit 的 `MolLogP` 和 `TPSA` 实际上是基于原子贡献，对氢的处理是健壮的。但 `Lipinski.NumHDonors(mol)` 依赖于显式氢标记的正确性。

**建议**: 在文档中明确说明 SDF 解析对氢的处理策略。

**问题 E — 公式中 LogP 计算方式是 Wildman-Crippen，需确认是否适用**

`Descriptors.MolLogP` 使用 Wildman-Crippen 方法。对于药物分子通常足够，但如果后续需要更精确的 LogP（如 XLogP3），应在配置中暴露选择。

### 1.3 QED 阈值使用

**位置**: `frontend/src/app/database/page.tsx` (line 121)

前端使用 `val >= 0.7` 绿色、`val >= 0.4` 黄色的阈值划分。根据 Bickerton et al. (2012) 原始论文，QED 的参考值：celecoxib=0.914, aspirin=0.552, 大多数药物在 0.3-0.7。0.7 作为"好"的阈值偏严格，但作为排序筛选是合理的。

### 1.4 ADMET 页面 — 概念展示正确

**位置**: `frontend/src/app/workflow/admet-filter/page.tsx`

ADMET 五维分类（Absorption/Distribution/Metabolism/Excretion/Toxicity）及其子属性（Caco-2, HIA, PPB, BBB, CYP, hERG, Ames, hepatotoxicity）都是标准且正确的药物化学参数。

---

## 二、代码设计与模型效果

### 2.1 问题 F — 数据库 session 生命周期管理存在根本缺陷

**位置**: `backend/app/main.py` (lines 56-64)

```python
if db_url.startswith('sqlite'):
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.state.db_session = SessionLocal()  # 单一 session，永不关闭
```

**风险**: 非常严重。
- 单一 Session 被所有并发请求共享，会导致事务冲突和数据污染
- Session 在 lifespan yield 之后才创建，但没有在 yield 之后关闭
- 没有请求级别的 session 管理（没有 dependency injection）
- 一旦发生 rollback，该 session 不可复用

**建议**: 使用 FastAPI 标准的 `Depends(get_db)` 模式：

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

对于非 SQLite（如 PostgreSQL），应使用 `create_async_engine` + `AsyncSession`。

### 2.2 问题 G — SDF 同步的 hash 策略有逻辑缺陷

**位置**: `backend/app/services/sdf_sync.py` (lines 35-52)

```python
current_hashes = {f["file_hash"] for f in sdf_files}
existing_records = db.query(SDFMolecule).all()
existing_by_hash: dict[str, list[SDFMolecule]] = {}
for rec in existing_records:
    existing_by_hash.setdefault(rec.sdf_file_hash, []).append(rec)
```

hash 是文件内容的 SHA-256。如果一个 SDF 文件被修改（哪怕只改了一个分子的名称），整个文件的 hash 变化，旧记录被标记为 orphan 删除，然后重新插入所有构象。

**风险**: 中等。
- 文件内容的任何微小变化都会导致全量删除 + 重新插入，而不是增量更新
- orphan 删除是按 hash 而非按文件路径，如果两个文件内容相同（不同路径），只有一个会被保留

**建议**: 考虑基于 `(sdf_file_path, conformer_index)` 的 upsert 策略，而不是基于 hash 的删除重建。

### 2.3 问题 H — SDF 同步加载所有记录到内存

**位置**: `sdf_sync.py` line 36

```python
existing_records = db.query(SDFMolecule).all()
```

当分子数据库有数万条记录时，这会把所有 SDFMolecule 对象加载到内存。一个中等规模的虚拟筛选库可能包含 10^5 - 10^6 个分子。

**建议**: 使用 `db.query(SDFMolecule.sdf_file_hash).distinct().all()` 只加载 hash，或者直接用 SQL 做 hash 比对。

### 2.4 问题 I — molecule_db.py 中的重复序列化

**位置**: `backend/app/api/routes/molecule_db.py` (lines 72-85, 96-106)

`list_molecules` 和 `get_molecule` 手动将 ORM 对象转为 dict，且两个接口的字段完全一致。后续新增字段需要在两处同步修改。

**建议**: 使用 Pydantic `from_orm` 模式或在 SDFMolecule 模型上添加 `to_dict()` 方法。

### 2.5 问题 J — combined_routes.py 全是占位但已注册

**位置**: `backend/app/api/routes/combined_routes.py`, `backend/app/main.py` (lines 119-123)

这些路由返回硬编码数据（固定 UUID、`progress: 0.0`、空数组），但已注册到应用中。对前端开发者来说，调用这些接口会得到"成功但无意义"的响应，可能掩盖集成问题。

**建议**: 未实现的路由应返回 501 Not Implemented，或使用 `@router.post(..., include_in_schema=False)` 从 OpenAPI 文档中隐藏。

---

## 三、性能与复杂度

### 3.1 问题 K — list_molecules 有两个查询执行

**位置**: `molecule_db.py` lines 67-70

```python
total = query.count()       # 第一次查询
molecules = query.offset(...).limit(...).all()  # 第二次查询
```

这执行了两次相同的 filter + sort 查询。对于大数据集，`COUNT(*)` 本身就可能很慢。

**建议**: 考虑使用 `window function` 或接受近似计数，或在前端用 "load more" 模式替代分页。

### 3.2 问题 L — scan_sdf_directory 对每个文件计算 SHA-256

**位置**: `sdf_parser.py` line 139

```python
fhash = compute_file_hash(full_path)
```

每次同步都对所有 SDF 文件计算完整的 SHA-256。对于大型 SDF 文件（几百 MB），这是昂贵的 I/O 操作。

**建议**: 先比较文件大小 + 修改时间（mtime），仅在两者都匹配时才跳过 hash 计算。或者缓存 hash 到文件系统（如 `.sdf.sha256` sidecar 文件）。

### 3.3 问题 M — ToolManager 的 execute 使用 subprocess.run (同步阻塞)

**位置**: `backend/app/services/tool_manager.py` line 67

```python
return subprocess.run([tool.executable_path] + args, capture_output=True, ...)
```

在 FastAPI（async）框架中调用同步 `subprocess.run` 会阻塞事件循环。如果工具执行需要几分钟（如 AutoDock Vina），整个服务在此期间无法处理其他请求。

**建议**: 使用 `asyncio.create_subprocess_exec` 或将耗时工具调用移到 Celery worker 中。

### 3.4 问题 N — csv_to_sdf 中 SDWriter 未正确处理异常

**位置**: `tame_vs_docker.py` lines 185-212

```python
writer = Chem.SDWriter(str(sdf_path))
try:
    ...
finally:
    writer.close()
```

如果 `csv.DictReader` 阶段就失败（比如编码问题），writer 已经创建但没写入任何内容，会生成一个空的 SDF 文件。

**建议**: 先验证 CSV 可读性，再创建 SDWriter。或者在写入前检查 `converted > 0`，不写空文件。

---

## 四、可维护性与架构

### 4.1 问题 O — 配置系统过于严格

**位置**: `backend/app/config.py`

`SchrodingerSettings.api_key`、`DrugClipSettings.api_key`、`DiffDynamicSettings.api_key`、`ToolPathsSettings.autodock_vina` 等都是必填字段 (`...`)。

**风险**: 如果开发者只想测试 SDF 解析功能，仍需填写所有外部 API key 和工具路径才能启动应用。这降低了开发体验。

**建议**: 将非核心配置设为 `Optional[str] = None`，在实际使用时检查可用性（lazy validation），而不是启动时 fail-fast。

### 4.2 问题 P — API 客户端骨架完全无用（暂无实际调用）

**位置**: `backend/app/api/integrations/`

Schrodinger、DrugClip、DiffDynamic 三个客户端只有 `get_client()` 和 `close()` 方法，没有任何业务方法。TAME-VS 有本地 Docker 执行能力，但 HTTP API 客户端也是空壳。

**建议**: 要么删除这些骨架文件（未来需要时再写），要么至少添加一个核心方法（如 `predict()`、`screen()`），表明调用约定。

### 4.3 问题 Q — Celery 配置在 import 时执行

**位置**: `backend/app/workers/celery_app.py`

```python
settings = get_settings()
```

模块级调用 `get_settings()` 意味着任何 import 该模块的代码（包括测试）都必须有有效的 `.env`。这使得单元测试变得困难。

**建议**: 使用 lazy initialization 或 factory pattern。

### 4.4 问题 R — 无 Alembic 迁移

`database/init.sql` 存在但 Alembic 未配置。当前使用 `Base.metadata.create_all()` 只能创建新表，无法处理 schema 变更。

**建议**: 初始化 Alembic，将 `init.sql` 作为 baseline。

### 4.5 问题 S — 前端 molecule 详情面板有中文硬编码

**位置**: `frontend/src/app/database/page.tsx` (lines 356-370)

详情面板的标签使用了硬编码中文（"分子名称"、"分子式"、"重原子数"等），而页面其他部分使用 i18n。这导致切换语言时详情面板不跟随变化。

---

## 五、测试完整性

当前项目**没有任何测试代码**。没有 pytest 测试文件，没有 Jest/React Testing Library 测试。

对于一个计算药物发现平台，以下测试至关重要：

1. **orthogonal_scoring 单元测试** — 验证 desirability 方向、artifact 检测、edge case（单个候选、所有候选都是 artifact）
2. **sdf_parser 集成测试** — 用已知分子验证 LogP、TPSA、QED 计算精度
3. **sdf_sync 单元测试** — 验证 hash 变化检测、orphan 清理、增量同步
4. **API 端点测试** — 验证 molecule_db CRUD、分页、过滤
5. **TAME-VS csv_to_sdf 测试** — 验证 SMILES → SDF 转换正确性

---

## 六、优点总结

1. **正交重打分算法设计优秀** — 体现了扎实的计算药物化学理解，"never average model outputs" 的原则是正确的
2. **SDF 解析覆盖了关键描述符** — SMILES, InChI, InChIKey, MW, LogP, TPSA, QED, Lipinski 参数，是药物化学标准集
3. **数据模型设计合理** — `candidate_metric_values` 支持多模型多指标，`orthogonal_scores` 独立存储排序结果，解耦清晰
4. **错误体系分层清晰** — `AppError` → 具体错误类 → 全局处理器，RFC 9457 风格
5. **前端数据库页面功能完整** — 过滤、排序、分页、统计、同步、详情展示，UX 设计合理
6. **TAME-VS Docker 集成务实** — WSL 路径转换、smoke test、自动 ingest 都是实际可用的实现

---

## 七、总体结论

**是否可合入**: 当前代码作为 **原型骨架** 可以合入，但有三个阻塞性问题必须在合入前修复：

| 优先级 | 问题 | 影响 |
|--------|------|------|
| **P0** | 数据库 session 生命周期管理 (#F) | 并发请求数据污染 |
| **P0** | SDF 同步全量加载 + hash 策略 (#G, #H) | 大库场景内存溢出、逻辑缺陷 |
| **P1** | 无任何测试 | 无法验证科学计算正确性 |

建议修改后合入的问题：

| 优先级 | 问题 |
|--------|------|
| P1 | 正交重打分 penalty 策略调优 (#C) |
| P2 | subprocess 阻塞事件循环 (#M) |
| P2 | 配置过于严格 (#O) |
| P2 | 前端 i18n 硬编码 (#S) |
| P3 | API 客户端骨架清理 (#P) |
| P3 | Alembic 迁移 (#R) |
