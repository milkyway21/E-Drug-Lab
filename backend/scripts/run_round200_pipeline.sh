#!/usr/bin/env bash
# round_200 VAV1 10000 分子生产流水线（单卡驱动）
# 链路：DiffGUI 生成(batch_size=8) → convert_diffgui_pt_to_eval → evaluate_pt_with_correct_reconstruct(exhaustiveness=8, dock)
#
# 用法: run_round200_pipeline.sh <GPU_ID> <CONFIG> <GEN_OUTDIR>
#   GPU_ID    物理卡号 (1 或 2)
#   CONFIG    sample config (sample_vav1_gpu1.yml / sample_vav1_gpu2.yml)
#   GEN_OUTDIR 生成输出目录 (round_200/gpu1 或 round_200/gpu2)
#
# 完全脱离 session：用 setsid nohup 启动本脚本即可。

set -uo pipefail

GPU_ID="${1:?usage: $0 <GPU_ID> <CONFIG> <GEN_OUTDIR>}"
CONFIG="${2:?}"
GEN_OUTDIR="${3:?}"

ROUND_DIR="/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200"
GPU_TAG="gpu${GPU_ID}"
LOGDIR="${ROUND_DIR}/logs"
mkdir -p "${LOGDIR}"

GEN_LOG="${LOGDIR}/${GPU_TAG}_gen.log"
CONV_LOG="${LOGDIR}/${GPU_TAG}_convert.log"
EVAL_LOG="${LOGDIR}/${GPU_TAG}_eval.log"
STATUS_FILE="${LOGDIR}/${GPU_TAG}_status.txt"

CONVERTED_PT="${ROUND_DIR}/converted/${GPU_TAG}.pt"
EVAL_OUT="${ROUND_DIR}/eval/${GPU_TAG}"

DIFFGUI_ROOT="/data/ye/diffgui"
DIFFDYN_ROOT="/data/ye/DiffDynamic"
CONVERTER="/data/ye/e-drug-lab/backend/scripts/convert_diffgui_pt_to_eval.py"
VAV1_DIR="/data/ye/e-drug-lab/data/VAV1_degron"

NUM_MOLS=5000
BATCH_SIZE=8
MOLS_PER_RUN=50   # 100 run × 50 = 5000 分子/卡 = 100 个 seed（对应"各负责100个随机数"）
EXHAUSTIVENESS=8
VINA_TIMEOUT=180
EVAL_WORKERS=12

echo_status() { echo "[$(date '+%F %T')] $*" | tee -a "${STATUS_FILE}"; }

echo_status "=== round_200 ${GPU_TAG} pipeline START (GPU_ID=${GPU_ID}, config=${CONFIG}) ==="

# ---------- Stage 1: DiffGUI 生成 ----------
echo_status "[1/3] 生成开始: num_mols=${NUM_MOLS} batch_size=${BATCH_SIZE} mols_per_run=${MOLS_PER_RUN}"
cd "${DIFFGUI_ROOT}"
CUDA_VISIBLE_DEVICES="${GPU_ID}" PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  conda run -n diffgui_new --no-capture-output python3 scripts/generate_batch.py \
    --config "configs/sample/${CONFIG}" \
    --outdir "${GEN_OUTDIR}" \
    --total_mols "${NUM_MOLS}" --batch_size "${BATCH_SIZE}" --mols_per_run "${MOLS_PER_RUN}" \
    --device cuda:0 \
    > "${GEN_LOG}" 2>&1
GEN_RC=$?
echo_status "[1/3] 生成结束 rc=${GEN_RC}"

# 收集所有 samples_*.pt
PT_FILES=$(find "${GEN_OUTDIR}" -name "samples_*.pt" 2>/dev/null | wc -l)
echo_status "[1/3] 生成 samples_*.pt 文件数: ${PT_FILES}"
if [ "${PT_FILES}" -eq 0 ]; then
  echo_status "[1/3] ❌ 无 samples_*.pt，流水线中止（查 ${GEN_LOG}）"
  exit 1
fi

# ---------- Stage 2: 转换 ----------
echo_status "[2/3] 转换开始: ${GEN_OUTDIR} → ${CONVERTED_PT}"
cd "${DIFFDYN_ROOT}"
PYTHONPATH="${DIFFDYN_ROOT}" \
  conda run -n diffdynamic --no-capture-output python3 "${CONVERTER}" \
    --input_dir "${GEN_OUTDIR}" \
    --output "${CONVERTED_PT}" \
    --protein_filename 9nfr.pdb \
    --ligand_filename N/A \
    --atom_mode add_aromatic \
    > "${CONV_LOG}" 2>&1
CONV_RC=$?
echo_status "[2/3] 转换结束 rc=${CONV_RC} (输出 ${CONVERTED_PT})"
if [ "${CONV_RC}" -ne 0 ] || [ ! -f "${CONVERTED_PT}" ]; then
  echo_status "[2/3] ❌ 转换失败（查 ${CONV_LOG}）"
  exit 1
fi

# ---------- Stage 3: correct-reconstruct 评估 ----------
echo_status "[3/3] 评估开始: exhaustiveness=${EXHAUSTIVENESS} vina-modes=dock timeout=${VINA_TIMEOUT}s workers=${EVAL_WORKERS}"
cd "${DIFFDYN_ROOT}"
EVAL_PARALLEL_WORKERS="${EVAL_WORKERS}" \
  conda run -n diffdynamic --no-capture-output python3 evaluate_pt_with_correct_reconstruct.py \
    "${CONVERTED_PT}" \
    --protein_root "${VAV1_DIR}" \
    --receptor_pdb "${VAV1_DIR}/9nfr.pdb" \
    --output_dir "${EVAL_OUT}" \
    --atom_mode add_aromatic \
    --exhaustiveness "${EXHAUSTIVENESS}" \
    --vina-modes dock \
    --vina-timeout-seconds "${VINA_TIMEOUT}" \
    --save_intermediate_interval 32 \
    > "${EVAL_LOG}" 2>&1
EVAL_RC=$?
echo_status "[3/3] 评估结束 rc=${EVAL_RC} (输出 ${EVAL_OUT})"
if [ "${EVAL_RC}" -ne 0 ]; then
  echo_status "[3/3] ⚠️ 评估非0退出（个别 Vina 超时属正常，查 ${EVAL_LOG}）"
fi

echo_status "=== round_200 ${GPU_TAG} pipeline DONE ==="
