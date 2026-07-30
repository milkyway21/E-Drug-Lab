#!/usr/bin/env bash
# round_200 流水线进度查询（随时运行）
# 统计：各卡生成 samples_*.pt 数、已完成分子数、当前 run、阶段状态、GPU 占用
ROUND_DIR=/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200
PYTHON=/home/user/anaconda3/envs/diffdynamic/bin/python3

echo "===== round_200 进度  $(date '+%F %T') ====="
echo "--- GPU 占用 ---"
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader | awk -F', ' '{printf "  GPU%s: %s/%s MiB  util %s%%\n",$1,$2,$3,$4}'

for GPU in gpu1 gpu2; do
  STATUS="${ROUND_DIR}/logs/${GPU}_status.txt"
  GENLOG="${ROUND_DIR}/logs/${GPU}_gen.log"
  echo "--- ${GPU} ---"
  if [ -f "${STATUS}" ]; then tail -3 "${STATUS}" | sed 's/^/  /'; else echo "  (无 status 文件)"; fi
  # 当前 run 与步数
  if [ -f "${GENLOG}" ]; then
    LASTRUN=$(grep -oE "Run [0-9]+" "${GENLOG}" | tail -1)
    LASTSTEP=$(grep -oE "[0-9]+/1000" "${GENLOG}" | tail -1)
    echo "  当前: ${LASTRUN:-?}  步: ${LASTSTEP:-?}"
  fi
  # samples_*.pt 数与累计 finished 分子数
  PT_COUNT=$(find "${ROUND_DIR}/${GPU}" -name "samples_*.pt" 2>/dev/null | wc -l)
  if [ "${PT_COUNT}" -gt 0 ] && [ -x "${PYTHON}" ]; then
    FINISHED=$("${PYTHON}" - <<PY 2>/dev/null
import glob, torch
n=0
for f in glob.glob("${ROUND_DIR}/${GPU}/**/samples_*.pt", recursive=True):
    try:
        d=torch.load(f,map_location='cpu')
        n+=len(d.get('finished',[]))
    except Exception as e:
        pass
print(n)
PY
)
    echo "  samples_*.pt: ${PT_COUNT} 个 | 累计 finished 分子: ${FINISHED:-?}"
  else
    echo "  samples_*.pt: ${PT_COUNT} 个"
  fi
done

echo "--- 转换/评估产物 ---"
ls -la "${ROUND_DIR}/converted/"*.pt 2>/dev/null | sed 's/^/  /'
for GPU in gpu1 gpu2; do
  if [ -d "${ROUND_DIR}/eval/${GPU}" ]; then echo "  eval/${GPU}: $(find ${ROUND_DIR}/eval/${GPU} -name '*.xlsx' 2>/dev/null | wc -l) xlsx"; fi
done
