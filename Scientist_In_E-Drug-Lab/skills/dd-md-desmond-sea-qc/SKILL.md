---
name: "dd-md-desmond-sea-qc"
description: "Schrödinger Desmond 官方 SEA QC 工作流（event_analysis + analyze_simulation），含三步法、ASL 速查、失败重试、数值摘要。Invoke for SEA analysis、RMSD 计算、接触分析、MD 后 QC。"
---

# Desmond MD — 官方 SEA QC 工作流

**⚠ 铁律：禁止自写 QC 脚本。** 自写 trj_analysis、手写 RMSD、自定义 contact 逻辑统统废弃。必须复用 Schrödinger 官方工具链（event_analysis.py + analyze_simulation.py）。

来源模式：`HSD17B13_MD/scripts/09_sea_extract_b200.py` (process_one) + `27_phaseF_post_analysis.py` (official_reports) + `20_plot_phaseE_rmsd.py` (plotting format)。

## 三步法（与 09 的 process_one 完全一致）

### Step 1: event_analysis.py analyze → in.eaf

```bash
"$SCHRODINGER/run" event_analysis.py analyze \
  <cms_file> \
  -prot "(protein)" \
  -lig "res.ptype UNK" \
  -out <base_name>
```

输出：`<base_name>-in.eaf`（事件定义文件，定义分析什么）。

### Step 2: analyze_simulation.py → out.eaf

```bash
nice -n 10 "$SCHRODINGER/run" analyze_simulation.py \
  -LOCAL -WAIT \
  -JOBNAME <job_name> \
  <cms_file> <trj_dir> \
  <base_name>-out.eaf <base_name>-in.eaf
```

CPU 运行，nice 降优先级。10 ns 轨迹约几分钟到几十分钟。
输出：`<base_name>-out.eaf`（实际分析结果）。

### Step 3: event_analysis.py report → 数据 + 图 + PDF

```bash
"$SCHRODINGER/run" event_analysis.py report \
  <base_name>-out.eaf \
  -pdf <output.pdf> \
  -data -plots \
  -data_dir <data_dir>
```

输出（在 data_dir 中）：
- `PL_RMSD.dat` — 蛋白-配体 RMSD 数据
- `PL-RMSD.png` — RMSD 图
- 蛋白/配体单独 RMSD 文件
- 接触/氢键/相互作用数据表
- `<base_name>-out.pdf` — 完整 Schrödinger SEA 报告 PDF

### 失败重试模式（从 09 抄）

如果 combined report 失败，分开跑：
1. 先 `-data -data_dir <dir>`
2. 再 `-plots -data_dir <dir>`
3. 最后 `-pdf <pdf>`

### ⚠️ 致命陷阱：工作目录（cwd）必须是 OUT_DIR

`event_analysis.py analyze -out <base>` 把 EAF 写到**当前工作目录**，不是 CMS 所在目录，也不是你以为的路径。

**错误模式**（踩过坑）：脚本 cwd 在 `md/short_h5/` 根目录，Step 1 写 `T5S0661_h5_sea-in.eaf` 到根目录，Step 2 也在根目录跑所以能读到（暂时没挂），Step 3 从 `qc/sea/` 读 EAF 直接失败，因为 EAF 在根目录不在 OUT_DIR。

**正确模式**：cd 到 OUT_DIR 后再跑所有三步，三条命令的输入输出都在 OUT_DIR 内。

```bash
OUT_DIR=/path/to/<mol>/qc/sea
mkdir -p "$OUT_DIR/data"
cd "$OUT_DIR"

# 现在所有 EAF、日志、data/ 都在 OUT_DIR 下
"$SCHRODINGER/run" event_analysis.py analyze "$CMS" -prot "(protein)" -lig "res.ptype UNK" -out "${MID}_h5_sea"
nice -n 10 "$SCHRODINGER/run" analyze_simulation.py -LOCAL -WAIT -JOBNAME "SEA_${MID}" "$CMS" "$TRJ" "${MID}_h5_sea-out.eaf" "${MID}_h5_sea-in.eaf"
"$SCHRODINGER/run" event_analysis.py report "${MID}_h5_sea-out.eaf" -pdf "data/${MID}_h5_sea-out.pdf" -data -plots -data_dir data/
```

如果已经踩坑（EAF 写到了错误目录）：**不要重算**，把已生成的 `-in.eaf` / `-out.eaf` 文件 mv 到正确的 OUT_DIR，然后从 Step 3 (report) 继续即可。analyze_simulation 是最费时间的一步，能复用绝不重跑。

## 最小路径适配策略

当目录布局与 09 脚本不同时，**不要重写 process_one**，也不要写新的 Python 脚本重排三步流程。最小路径只有一个正确答案：

1. **符号链接桥接**：staging 目录下创建 CMS 和 trajectory 的符号链接，命名成 09 期望的格式（见参考文件「符号链接 staging 模式」）
2. **直接调用 3 条官方命令**：命令序列、参数、标志位与 09 完全一致
3. **只改路径变量**：cms_path / trj_path / out_dir / base_name，不改流程

❌ 错误做法（踩过坑，被纠正过两次）：
- 自写 `trj_analysis.py` 脚本算 RMSD → 废弃，非官方
- 新建 `h5_sea_extract.py` 重写 `process_one` 函数 → 废弃，完全没必要
- 在 shell 脚本根目录跑 Step 1/2 然后从子目录跑 Step 3 → EAF 路径不一致，必挂

✅ 正确做法：写一个极薄的 shell wrapper，cd 到 OUT_DIR 后依次跑 3 条命令，仅此而已。

## ASL 速查

| 组分 | ASL 表达式 | 说明 |
|------|-----------|------|
| 蛋白 | `(protein)` | 标准蛋白选择 |
| 配体 | `res.ptype UNK` | HSD17B13 体系配体为 UNK 残基 |
| 蛋白骨架 | `protein and backbone` | RMSD 计算常用 |
| 蛋白 Cα | `protein and ca` | Cα RMSD |
| 配体重原子 | `ligand and not atom.ele H` | 配体 RMSD 常用 |

## 环境变量（SEA 专用）

- `CUDA_VISIBLE_DEVICES=""` — SEA 是 CPU 任务，别占 GPU
- `SCHRODINGER_CUDA_VISIBLE_DEVICES=""`
- `MPLBACKEND=Agg` — 无头出图
- `QT_QPA_PLATFORM=offscreen`

## 轨迹阶段对应（umbrella mode 下的 multisim）

以 5 个 simulate 块的 msj 为例（1 Brownian + 2 NPT restrained + 1 NPT unrestrained + 1 production）：

| stage 目录 | 阶段 | 是否用于 SEA |
|-----------|------|-------------|
| `*_1/` | desmond:auto (setup) | 否 |
| `*_2/` | Brownian NVT 10K (100 ps) | 否 |
| `*_3/` | NPT restraints (500 ps) | 否 |
| `*_4/` | NPT weaker restraints (500 ps) | 否 |
| `*_5/` | NPT unrestrained eq (1000 ps) | 否 |
| `*_6/` | **Production** | **是** |

**规则：只对编号最大的 stage（生产阶段）做 SEA。** 绝不用平衡阶段轨迹。

## 数值摘要判断

### PL_RMSD.dat 数据字典

空格分隔，第 1 行为 `#` 开头的表头注释行。列顺序（从左到右，1-indexed）：

| 列 | 列名 | 含义 | 单位 |
|----|------|------|------|
| 1 | Frame# | 帧号（从 0 开始，0 = 参考结构/初始帧） | — |
| 2 | Prot_CA | 蛋白 Cα RMSD | Å |
| 3 | Prot_Backbone | 蛋白骨架 RMSD | Å |
| 4 | Prot_Sidechain | 蛋白侧链 RMSD | Å |
| 5 | Prot_All_Heavy | 蛋白全重原子 RMSD | Å |
| 6 | Lig_wrt_Protein | 配体叠合到蛋白后的 RMSD | Å |
| 7 | Lig_wrt_Ligand | 配体自身叠合 RMSD | Å |

### 统计口径（极易出错，必须严格遵守）

- **总帧数** = 52（frame 0–51，含参考帧）。10 ns × 200 ps 间隔 + 初始帧 = 51 生产帧 + 1 参考帧 = 52 行数据
- **整体均值/极值**：**排除 frame 0**，n = 51（参考帧全为 0，会拉低均值）
- **后 20% (late)**：最后 10 帧，即 frame 42–51（两端都包含）。10 ns 的 20% = 2 ns = 10 帧（200 ps/帧）
- **绝不能**用 `awk '{sum+=$2}'` 把表头算进去；必须 `NR>2` 或判断第一列是数字

### PL-Contacts_HBond.dat 数据字典

每行 = **一个 H 键接触事件** = 特定帧 × 特定残基 × 特定原子对。不是"每帧有多少个 H 键"。

列顺序：

| 列 | 列名 | 含义 |
|----|------|------|
| 1 | Frame# | 帧号 |
| 2 | Residue# | 蛋白残基号 |
| 3 | Chain | 链名 |
| 4 | ResName | 残基名 |
| 5 | AtomName | 蛋白原子名（H 键供体或受体） |
| 6 | LigandFragment | 配体片段（通常 L-FRAG_0/1） |
| 7 | LigandAtomName | 配体原子名 |

### H 键统计口径（踩过坑，必须去重）

| 指标 | 正确算法 | 错误做法 |
|------|---------|---------|
| 总事件数 | 数据行数 | = 每帧平均接触数 |
| H 键覆盖率 | `awk 'NR>1 {print $1}' \| sort -un \| wc -l` ÷ 52 | 事件数 ÷ 51 或直接 awk 求列均值 |
| 某残基 H 键帧数 | 对该残基按 Frame# 去重后的数量 | 事件数（同一帧两个原子对算两事件但同残基只算一帧有接触） |
| 某残基占有率 | 去重帧数 ÷ 总帧数 (52) | 事件数 ÷ 总帧数 |

**常见陷阱**：PHE220 主链 H 可以交替结合配体两个 O 原子（O9191 + O9210），这是两个不同的 H 键对，加总事件数会是 48，但去重后也是 48 帧（因为一帧里不会同时出现两对）。正确表述："PHE220 参与 H 键共 48 帧（O9210: 28 帧 + O9191: 20 帧）"。

### 稳定性判据参考

- 蛋白 stable: Cα RMSD 均值 < 3 Å 且 max < 4 Å
- 配体 stable: Lig_wrt_Protein 均值 < 3 Å
- 配体可接受: max < 5 Å（short MD 初筛用）
- Late mean > 整体均值 → 有漂移趋势，需注意
- 以上仅供初筛，最终结论需结合接触分析

## 操作规范

### 不要内联多行命令

**禁止**把 5 行以上的命令折叠进 `terminal()` 的单行调用。反斜杠被当实参、cd 后缺分隔符、文件名手滑打错——这些问题一个不落都踩过。

正确做法：**写独立 launcher shell 脚本**，`chmod +x`，然后单行调用。

```bash
# 错误 ❌
terminal(command='cd $dir && \\
  $SCHRODINGER/utilities/multisim -m build.msz ... \\
  -WAIT -LOCAL > log 2>&1')

# 正确 ✅
write_file(path='launch_build.sh', content=
  #!/bin/bash
  cd "$WD"
  "$SCHRODINGER/utilities/multisim" \
    -HOST localhost -maxjob 1 \
    -JOBNAME "$JOBNAME" -m build.msj "$COMPLEX" \
    -mode umbrella -WAIT -LOCAL >> log 2>&1
')
terminal(command='./launch_build.sh')
```

### MD 监控节奏

短程 MD（10–50 ns）跑起来后**每 ~300 秒检查一次**即可（用 `process(action=poll)` 或直接读 log tail）。不要短轮询（每 30 秒查一次）——既浪费迭代，也不会让 MD 变快。notify_on_complete 才是主力通知机制。

## 参考文件

- `references/sea-commands-cheatsheet.md` — 命令级速查表（更详细）
- `references/minimal-adapter-template.md` — 最小路径适配完整模板（符号链接 + shell wrapper + 失败修复）
