# ALLIN 多模态持续学习 — 代码审计冻结（对照修复方案 docx）

> **日期**：2026-08-03  
> **范围**：代码准备阶段（新持续学习 Glide SP **未齐**，不做对接实跑）  
> **真源运行时**：`/data/ye/diffgui/third_party/GLARE/model.py`（`glare_gnn_cli` 的 `GLARE_ROOT`）  
> **镜像**：`/data/ye/ALLIN/rl/third_party_GLARE/model.py`  
> **编排**：`e-drug-lab/backend/app/pipelines/vav1_rl/` + `scripts/run_allin_pc_gl_progressive.py`

## 1. 真实数据流（修复前）

```
SMILES → CRBN strip（图/FP/101D）→ GIN + ECFP 残差
       → PhysChem 101（磁盘 scaler）残差 β=0.1
       → Glide 16（mask）残差 β=0.1
       → MD 47（仅 ginl_pc_gl_md；mask + md_adv_eta）
       → log_softmax → NLL +「GRPO 风格」分类辅助项
```

## 2. 缺口对照（docx → 现状）

| docx 要求 | 修复前现状 | 优先级 |
|-----------|------------|--------|
| R1+ anchor = 上一轮权重 | `__init__` 锚定随机初始化；load prev 后不刷新 | P0 |
| checkpoint 加载失败必显式报错 | `except Exception: pass` + `strict=False` | P0 |
| feature_schema 进 ckpt；query 用 ckpt scaler | 仅 `state/args/encoder_type`；外部路径 scaler | P0 |
| 模态覆盖率审计 | 无 | P0 |
| learnable_gate 残差（保留 fixed_residual） | 仅 fixed β | P1 |
| MD 进 progressive 主线 | `ARCH` 锁死 `ginl_pc_gl` | P1 |
| MD reward 仅 md_mask=1；防过采样 | 有 shaping，无采样上限/分项报告 | P1 |
| 区分 supervised / bandit / 真 GRPO | 一律称 grpo | P2 |
| 遗忘矩阵 / 蒸馏 / MD AL / 消融 | 缺或未接主链路 | P3（骨架可先） |
| 库1/2 新 SP | **等待数据** | Wait-SP |

## 3. 本阶段交付（代码准备）

- P0：`set_anchor_from_current_weights`、严格 load、schema、coverage 钩子  
- P1：`fusion_type`、MD CLI/progressive 参数化、mask 语义  
- 合成数据 pytest；**不**新跑 Glide、不覆盖 `allin_pc_gl_progressive/`

## 4. 相关文档

- [`project.md`](project.md) · [`ALLIN/docs/ALLIN_设计到测试完整报告.md`](/data/ye/ALLIN/docs/ALLIN_设计到测试完整报告.md) §4.5
