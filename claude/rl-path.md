# 强化学习（RL）路径

> 2026-06-20 整理。e-drug-lab 的 GLARE 强化学习闭环链路。

## 链路全貌（已验证端到端可跑）

```
前端 rl-training 页面
  └─ apiClient.glareTrain / glareScreen / importWetlab  (frontend/src/lib/api-client.ts)
       └─ POST /api/v1/glare/train | /screen | /import-wetlab   (routes/glare.py)
            └─ GlareRunner.run_seed_reinforce / run_wetlab_reinforce / run_train / run_screen
                 └─ conda_run(diffgui_new) → /data/ye/diffgui/glare_selector/*.py
                      · reinforce_glare_with_seed_data.py  (seed 强化)
                      · reinforce_glare_with_wetlab.py     (湿实验强化)
                      · train_glare_policy.py train/query  (训练/查询)
                      · import_wetlab_pdc50.py             (湿实验导入)
```

## 状态管理

- **RL 轮次表**：`rl_rounds` + `rl_round_artifacts`（ORM，见 models.py）
- **服务**：`services/rl_round_service.py` —— `create_round/get_round/list_rounds/update_round/
  add_artifact/write_step_log/read_step_log/rounds_base_dir/round_dir`
- **规范输出根目录**：`rl_round_service.rounds_base_dir()` = `backend/outputs/rl_rounds/`
  （用 `Path(__file__).resolve().parents[2]` 定位，不依赖硬编码兄弟目录）
- **异步任务**：`job_store.create/update/get`，route 用 `asyncio.create_task` + `asyncio.to_thread`
  跑 conda 子进程，前端轮询 `/glare/jobs/{job_id}`

## Task 6 修复的硬编码路径问题（2026-06-20）

原 `glare_runner.py` / `diffgui_runner.py` 用 `self.root.parent / "e-drug-lab" / "backend"`
脆弱拼接 RL 输出路径（假设 diffgui 与 e-drug-lab 是兄弟目录）。已改为：

- `GlareRunner.rl_rounds_root()`：优先 `settings.glare.outputs_dir`，否则复用 `rounds_base_dir()`
- `GlareSettings` 新增 `outputs_dir`（可选，留空用规范路径）
- `DiffGuiRunner.round_output_dir()`：相对路径时解析到 `rounds_base_dir()`
- `routes/glare.py` import-wetlab 的 `labeled_pool` 路径改用 `runner.rl_rounds_root()`
- 全部去除 `"e-drug-lab"` / `"backend"` 硬编码拼接

## 端到端验证记录

- conda env `diffgui_new`（torch 2.4.1 cuda True）✅
- GLARE 脚本 `train_glare_policy.py` train/query 子命令 ✅
- RL round DB CRUD + step_log 读写 ✅（需先 `init_engine`，见 [[env-and-tool-runtime]] 的 DB 注入）
- **实跑 `run_seed_reinforce`（round_99）成功**：生成 checkpoint + reward/similarity 表 + 报告 ✅
- 历史 round_1/round_2 checkpoint 扫描无回归 ✅
- 前端 api-client 方法与后端路由齐全对齐 ✅

## DB session 注入注意

`db.py` 的 `init_engine()` 只在 FastAPI lifespan 里调用。直接用脚本测试 service 层时
必须先手动 `init_engine(settings.database.url)`，否则 `get_sessionmaker()` 返回 None。
运行时（uvicorn 启动）无此问题。

## 相关

- [[env-and-tool-runtime]] —— conda 环境、conda_runner、磁盘策略
- [[project-structure]] —— 整体架构
