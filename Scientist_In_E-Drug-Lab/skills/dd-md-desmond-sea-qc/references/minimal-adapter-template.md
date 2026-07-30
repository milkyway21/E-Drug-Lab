# SEA 最小适配模板（符号链接 + Shell Wrapper）

当目录布局与 `09_sea_extract_b200.py` 不同时，用这个模式做最小路径适配。
不要重写 process_one，不要写 Python 脚本封装，不要自写分析逻辑。

## 文件布局约定

```
campaign/
├── md/short_h5/
│   ├── T5S0661/
│   │   └── HSD17B13_T5S0661_10ns_h5_6/        ← 生产 stage 目录
│   │       ├── HSD17B13_T5S0661_10ns_h5_6-in.cms  ← 生产阶段输入 CMS
│   │       └── HSD17B13_T5S0661_10ns_h5_6_trj/
│   │           └── clickme.dtr
│   ├── T83721/
│   │   └── ... (同上)
│   └── run_single_sea.sh                     ← 见下方模板
```

## Step 1: 确认生产阶段目录

找编号最大的 stage 目录（umbrella mode 下最后一个 = production）：

```bash
ls -d HSD17B13_${MID}_10ns_h5_*/ | sort -t_ -k2 -n | tail -1
```

5 个 simulate 块 → 6 个 stage（`_1` 是 setup/desmond:auto，`_2`–`_6` 是 5 个 simulate），`_6` 是 production。

## Step 2: 写独立 Shell Wrapper

**必须**写成独立文件，不能内联多行命令。命名 `run_single_sea.sh`：

```bash
#!/bin/bash
# Run full SEA for one molecule in its OUT_DIR (correct cwd)
# Usage: run_single_sea.sh <MOL_ID>
set -e

MID=$1
if [ -z "$MID" ]; then
    echo "Usage: $0 <MOL_ID>"
    exit 1
fi

export SCHRODINGER=/opt/schrodinger2023-3
export CUDA_VISIBLE_DEVICES=
export SCHRODINGER_CUDA_VISIBLE_DEVICES=
export MPLBACKEND=Agg
export QT_QPA_PLATFORM=offscreen

BASE=/path/to/campaign/md/short_h5
OUT_DIR=${BASE}/${MID}/qc/sea
DATA_DIR=${OUT_DIR}/data

# Production stage CMS + trajectory (stage 6)
CMS=${BASE}/${MID}/HSD17B13_${MID}_10ns_h5_6/HSD17B13_${MID}_10ns_h5_6-in.cms
TRJ=${BASE}/${MID}/HSD17B13_${MID}_10ns_h5_6/HSD17B13_${MID}_10ns_h5_6_trj
BASE_NAME=${MID}_h5_sea

mkdir -p "$OUT_DIR" "$DATA_DIR"

# === CRITICAL: cd to OUT_DIR before running anything ===
cd "$OUT_DIR"

# Step 1: event_analysis.py analyze → in.eaf
if [ ! -f "${BASE_NAME}-in.eaf" ]; then
    echo "Step 1/3: event_analysis analyze"
    "$SCHRODINGER/run" event_analysis.py analyze \
        "$CMS" \
        -prot "(protein)" \
        -lig "res.ptype UNK" \
        -out "$BASE_NAME" \
        > 01_gen_eaf.log 2>&1
fi

# Step 2: analyze_simulation.py → out.eaf (CPU, may take minutes)
if [ ! -f "${BASE_NAME}-out.eaf" ]; then
    echo "Step 2/3: analyze_simulation"
    nice -n 10 "$SCHRODINGER/run" analyze_simulation.py \
        -LOCAL -WAIT \
        -JOBNAME "SEA_${MID}" \
        "$CMS" "$TRJ" \
        "${BASE_NAME}-out.eaf" "${BASE_NAME}-in.eaf" \
        > 02_analyze_sim.log 2>&1
fi

# Step 3: event_analysis.py report -pdf -data -plots
if [ ! -f "data/PL_RMSD.dat" ] || [ ! -f "data/${BASE_NAME}-out.pdf" ]; then
    echo "Step 3/3: event_analysis report"
    "$SCHRODINGER/run" event_analysis.py report \
        "${BASE_NAME}-out.eaf" \
        -pdf "data/${BASE_NAME}-out.pdf" \
        -data -plots \
        -data_dir data/ \
        > 03_report.log 2>&1
fi

# Verify
if [ ! -f "data/PL_RMSD.dat" ]; then
    echo "ERROR: PL_RMSD.dat missing"
    exit 1
fi

date -Iseconds > SEA_DONE.flag
echo "DONE"
```

## Step 3: 运行

```bash
chmod +x run_single_sea.sh
./run_single_sea.sh T5S0661
./run_single_sea.sh T83721
```

多条并行时用 `nohup` + 后台：

```bash
nohup ./run_single_sea.sh T5S0661 > /dev/null 2>&1 &
nohup ./run_single_sea.sh T83721 > /dev/null 2>&1 &
```

## 失败修复（不重算原则）

### EAF 写到了错误目录（path bug）

症状：Step 3 报错找不到 EAF，`01_gen_eaf.log` 里有输出但文件不在 OUT_DIR。

修复：

```bash
# 找到散落的 EAF 文件（通常在脚本启动目录）
find /path/to/md -name "*-in.eaf" -o -name "*-out.eaf"

# 移到正确位置
mv T5S0661_h5_sea-in.eaf T5S0661/qc/sea/
mv T5S0661_h5_sea-out.eaf T5S0661/qc/sea/

# 重新从 Step 3 开始
cd T5S0661/qc/sea
"$SCHRODINGER/run" event_analysis.py report \
    T5S0661_h5_sea-out.eaf \
    -pdf data/T5S0661_h5_sea-out.pdf \
    -data -plots -data_dir data/
```

**绝不要**因为路径错了就重跑 analyze_simulation——那是最费时间的一步。

### Combined report 失败

症状：Step 3 一次跑 -data -plots -pdf 失败。

修复：分开跑（顺序来自 09_sea_extract_b200.py 的 retry 逻辑）：

```bash
# 1. Data only
"$SCHRODINGER/run" event_analysis.py report out.eaf -data -data_dir data/

# 2. Plots only
"$SCHRODINGER/run" event_analysis.py report out.eaf -plots -data_dir data/

# 3. PDF only
"$SCHRODINGER/run" event_analysis.py report out.eaf -pdf report.pdf
```

## 产出验证清单

每个分子 `qc/sea/data/` 下必须非空：

- [ ] `PL_RMSD.dat` — ~5 KB，52 行数据（含表头 53 行）
- [ ] `PL-RMSD.png` — ~200 KB
- [ ] `<mol>_h5_sea-out.pdf` — 完整 SEA 报告，几 MB 级
- [ ] `PL-Contacts_HBond.dat` — H 键接触事件表
- [ ] `PL-Contacts_Hydrophobic.dat` — 疏水接触事件表
- [ ] `L_RMSF.dat` — 配体 RMSF
- [ ] `L-Properties.dat` — 配体性质

`SEA_DONE.flag` 旗标写在 `qc/sea/` 下。
