#!/usr/bin/env bash
set -u

project_root="/home/user/Desktop/Ye/DiffDynamic/hsvpol/targetmol_t001/HSD17B13_MD"
log_file="$project_root/logs/phaseE_corrected_pose_four_hour_monitor.log"
interval_seconds=14400

while true; do
    {
        date '+%Y-%m-%dT%H:%M:%S %Z FOUR_HOUR_SNAPSHOT'
        /opt/schrodinger2023-3/jobcontrol -list | rg 'HSD17B13_E52C|JobId|running|failed|completed' || true
        nvidia-smi --query-gpu=index,utilization.gpu,memory.used,temperature.gpu --format=csv,noheader
        printf 'built_cms='
        find "$project_root/03_systems/phaseE_corrected_pose_all40_20260727" -name '*.cms' -size +1M | wc -l
        printf 'completed_output_cms='
        find "$project_root/04_trajectories/phaseE_corrected_pose_2_50_all40_20260727" -name '*_out.cms' -size +1M | wc -l
        pgrep -af '16_phaseE_corrected_all40_6gpu|15_build_corrected_pose_all40|17_phaseE_watchdog' || true
        printf '\n'
    } >> "$log_file" 2>&1
    sleep "$interval_seconds"
done
