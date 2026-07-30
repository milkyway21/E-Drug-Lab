# SEA 命令速查 & 陷阱手册

完整工作流脚本参考：`HSD17B13_MD/scripts/09_sea_extract_b200.py`（process_one）
报告模式参考：`HSD17B13_MD/scripts/27_phaseF_post_analysis.py`（official_reports）

## 三条核心命令（copy-paste 可用）

```bash
export SCHRODINGER=/opt/schrodinger2023-3
export CUDA_VISIBLE_DEVICES=""
export SCHRODINGER_CUDA_VISIBLE_DEVICES=""
export MPLBACKEND=Agg
export QT_QPA_PLATFORM=offscreen

MID=T5S0661
CMS=/path/to/production-in.cms
TRJ=/path/to/trajectory_trj
OUT_DIR=/path/to/<mol>/qc/sea
BASE_NAME=${MID}_h5_sea

mkdir -p "$OUT_DIR/data"
cd "$OUT_DIR"  # ⚠️ 必须 cd 到 OUT_DIR，否则 EAF 写到错误位置

# 1. 生成 in.eaf（定义分析事件）
"$SCHRODINGER/run" event_analysis.py analyze \
    "$CMS" \
    -prot "(protein)" \
    -lig "res.ptype UNK" \
    -out "$BASE_NAME" \
    > 01_gen_eaf.log 2>&1

# 2. 运行 SEA（CPU，可 nice）
nice -n 10 "$SCHRODINGER/run" analyze_simulation.py \
    -LOCAL -WAIT \
    -JOBNAME "SEA_${MID}" \
    "$CMS" "$TRJ" \
    "${BASE_NAME}-out.eaf" "${BASE_NAME}-in.eaf" \
    > 02_analyze_sim.log 2>&1

# 3. 生成报告（数据 + 图 + PDF）
"$SCHRODINGER/run" event_analysis.py report \
    "${BASE_NAME}-out.eaf" \
    -pdf "data/${BASE_NAME}-out.pdf" \
    -data -plots \
    -data_dir data/ \
    > 03_report.log 2>&1
```

## ⚠️ 致命陷阱：工作目录（cwd）必须是 OUT_DIR

`event_analysis.py analyze -out <base>` 把 EAF 写到**当前工作目录**，不是 CMS 所在目录，也不是 -out 参数指定路径的目录。

**踩坑实录**：脚本 cwd 在 `md/short_h5/` 根目录，Step 1 写 `T5S0661_h5_sea-in.eaf` 到根目录，Step 2 也在根目录跑所以能读到（暂时没挂），Step 3 从 `qc/sea/` 读 EAF 直接失败——因为 EAF 在根目录不在 OUT_DIR。

**正确模式**：cd 到 OUT_DIR 后再跑所有三步，三条命令的输入输出都在 OUT_DIR 内。

**已踩坑后的恢复**（不要重算）：
1. 找到散落的 `-in.eaf` / `-out.eaf` 文件（它们被写到了当时的 cwd）
2. `mv` 到正确的 OUT_DIR 目录
3. 从 Step 3 (report) 继续即可，**不要重跑 Step 2**（analyze_simulation 是最费时间的一步）

## 输出清单

| 文件 | 说明 |
|------|------|
| `data/PL_RMSD.dat` | 蛋白-配体 RMSD 数据（时间序列，见下方列说明） |
| `data/PL-RMSD.png` | RMSD 曲线图 |
| `data/<base>-out.pdf` | 完整 SEA 报告（含接触分析） |
| `data/PL-Contacts_*.dat` | 氢键、疏水、盐桥等接触数据 |
| `data/PL-Contacts_Histogram.png` | 接触直方图 |
| `data/L-RMSF.*` | 配体 RMSF |
| `data/L-Torsions.*` | 配体扭转角 |
| `data/LP-Contacts_2d-Summary.png` | 2D 接触总结图 |
| `data/L-Properties.*` | 配体性质（SASA 等） |

## PL_RMSD.dat 列详解

```
# frame#    Prot_CA   Prot_Backbone  Prot_Sidechain  Prot_All_Heavy Lig_wrt_Protein  Lig_wrt_Ligand
```

| 列名 | 含义 | 用途 |
|------|------|------|
| `Prot_CA` | 蛋白 Cα RMSD (Å) | 蛋白稳定性主指标 |
| `Prot_Backbone` | 蛋白骨架 RMSD (Å) | 蛋白稳定性次指标 |
| `Prot_Sidechain` | 蛋白侧链 RMSD (Å) | 侧链波动 |
| `Prot_All_Heavy` | 蛋白全重原子 RMSD (Å) | 总波动 |
| `Lig_wrt_Protein` | 配体在蛋白拟合后的 RMSD (Å) | **结合姿态稳定性** 主指标 |
| `Lig_wrt_Ligand` | 配体内在 RMSD (Å) | 配体自身构象变化 |

## 常见 ASL

```
蛋白:        (protein)
配体:        res.ptype UNK
蛋白骨架:    protein and backbone
蛋白Cα:      protein and atom.name CA
配体重原子:  ligand and not atom.ele H
```

## 轨迹阶段对应（umbrella mode 下的 multisim）

以 5 个 simulate 块的 msj 为例（1 Brownian + 2 NPT restrained + 1 NPT unrestrained + 1 production）：

| stage 目录 | 阶段 | 时长 | 用于 SEA |
|-----------|------|------|---------|
| `*_1/` | desmond:auto (setup) | — | 否 |
| `*_2/` | Brownian NVT 10K | 100 ps | 否 |
| `*_3/` | NPT restraints (heavy) | 500 ps | 否 |
| `*_4/` | NPT weaker restraints | 500 ps | 否 |
| `*_5/` | NPT unrestrained eq | 1000 ps | 否 |
| `*_6/` | **Production NPT** | 10/50/200 ns | **是** |

**铁律：只对编号最大的 stage（生产阶段）做 SEA。绝不用平衡阶段轨迹。**

## 稳定性启发式判据（HSD17B13 膜体系参考）

| 指标 | Stable | Borderline | Unstable |
|------|--------|------------|----------|
| 蛋白 Cα RMSD (最终) | < 3 Å | 3–5 Å | > 5 Å |
| 配体 RMSD (wrt protein, 最终) | < 3 Å | 3–5 Å | > 5 Å |
| 配体 RMSD (全程最大值) | < 5 Å | 5–8 Å | > 8 Å |

⚠️ 以上为初筛启发式，最终结论需结合接触分析（氢键保持率、疏水接触分数等）。

## 失败排查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| in.eaf 生成失败 | ASL 匹配不到原子 | 检查配体残基名（不一定是 UNK） |
| analyze_simulation 极慢 | 轨迹太大或内存不足 | nice + 检查内存，必要时减少分析事件 |
| report 失败但 out.eaf 存在 | combined 模式出图问题 | 分开跑：先 `-data` 再 `-plots` 再 `-pdf` |
| PL_RMSD.dat 不存在 | report 完全失败 | 查 03_report.log，看具体报错 |
| EAF 在根目录不在 OUT_DIR | 没 cd 就跑 Step 1 | mv 到正确目录，从 Step 3 继续 |
| 结果为空/全 0 | 配体 ASL 不对 | 检查 CMS 中配体残基名（HSD17B13 通常是 UNK） |

## 最小路径适配：符号链接 staging 模式

当目录布局与 09 脚本不同时，**不要重写 process_one**，也不要写 Python 脚本重排流程。
最小代价方案：创建 staging 目录，用符号链接把 CMS 和 trajectory 命名成 09 期望的格式，然后直接跑同样的 3 条命令。

```bash
STAGING=/path/to/sea_staging/trajectories
mkdir -p "$STAGING/$MID"

# CMS: 命名成 09 期望的 <mid>_202ns-out.cms
ln -s /abs/path/to/production-in.cms "$STAGING/$MID/${MID}_202ns-out.cms"

# Trajectory: 命名成 HSD17B13_B200_<mid>_6_trj/ (09 的 ensure_traj 期望的名字)
ln -s /abs/path/to/trajectory_trj "$STAGING/$MID/HSD17B13_B200_${MID}_6_trj"

# 然后 cd 到 OUT_DIR，用上面三条命令跑就行
# CMS = $STAGING/$MID/${MID}_202ns-out.cms
# TRJ = $STAGING/$MID/HSD17B13_B200_${MID}_6_trj
```

为什么是 `_202ns-out.cms` 和 `B200_<mid>_6_trj`？因为这是 09 脚本 Phase B 200 ns 体系的命名约定。
名字只是符号链接的标签，内容才是真实的 10 ns 轨迹。命令序列和参数完全不变。

## HSD17B13 体系验证过的参数

- 力场: OPLS4
- 膜: POPC (约 177–178 个)
- 水: SPC (约 16700 个)
- 盐: 0.15 M NaCl
- 温度: 310.15 K
- 配体残基名: UNK
- 蛋白链: A + B（二聚体，各 284 aa）
- 辅酶: NAD × 2
- 总原子数: ~83,000
