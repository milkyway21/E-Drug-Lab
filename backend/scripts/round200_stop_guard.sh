#!/usr/bin/env bash
# round_200 停止守护：等当前 run 跑完即杀生成，保留 pipeline 脚本让其自动进 convert+eval
# GPU1 等到 run_010 出 samples_*.pt；GPU2 等到 run_009 出 samples_*.pt
ROUND_DIR=/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200
LOG="${ROUND_DIR}/logs/stop_guard.log"
echo "$(date '+%F %T') stop guard 启动，等待当前 run 完成" >> "${LOG}"

stop_gpu() {
  local GPU=$1 RUN=$2 CFG=$3
  echo "$(date '+%F %T') [${GPU}] 等待 ${RUN} 的 samples_*.pt 出现..." >> "${LOG}"
  until [ -n "$(find ${ROUND_DIR}/${GPU}/${RUN} -name 'samples_*.pt' 2>/dev/null)" ]; do
    sleep 15
  done
  echo "$(date '+%F %T') [${GPU}] ${RUN} 完成，等 8s 让 sample.py 退出后杀生成" >> "${LOG}"
  sleep 8
  pkill -f "generate_batch.py.*${CFG}"
  sleep 2
  pkill -f "sample.py.*round_200/${GPU}"
  echo "$(date '+%F %T') [${GPU}] 已停止生成（${RUN} 为最后一个完整 run）" >> "${LOG}"
}

stop_gpu gpu1 run_010 sample_vav1_gpu1.yml &
stop_gpu gpu2 run_009 sample_vav1_gpu2.yml &
wait
echo "$(date '+%F %T') 两卡均已停止生成，pipeline 将自动进入转换+评估" >> "${LOG}"
