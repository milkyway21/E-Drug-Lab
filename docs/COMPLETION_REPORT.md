# e-drug lab 恢复状态报告

本报告替换了原先全 0 字节的 `COMPLETION_REPORT.md`，记录当前仓库可确认的完成度。

## 已恢复

- 前端 `package.json`、Next.js 配置、Tailwind 配置和主要页面源码。
- 根目录 `database/init.sql`，与 SQLAlchemy 模型保持一致。
- `molecules/sdf/aspirin.sdf` 与 `molecules/sdf/ibuprofen.sdf` 示例数据。
- 前端中的导航、工作流、分子库、模型、记录和文档页面。

## 当前可用

- FastAPI 后端 Python 源码可以通过语法编译。
- 前端恢复为可构建的 Next.js 应用骨架。
- 数据库 schema 可以作为 PostgreSQL 初始化脚本使用。
- SDF 示例文件可供 RDKit 解析服务测试。

## 仍需完成

- 后端真实数据库 session 初始化。
- `combined_routes.py` 的变量命名修复和主应用注册。
- docking worker 的 AutoDock Vina 真实调用。
- ADMET、亲和力评估、分子生成和候选排序的真实后端逻辑。
- 前端与完整后端任务状态的端到端联调。
