# HSD17B13 Reference Script Index

All paths below are relative to `scripts/hsd17b13_reference/`. These files preserve the complete campaign implementation and its historical phase names. They contain HSD17B13-specific roots, ASLs, candidate IDs, and host names; port them through a new campaign configuration before using them on another target.

## Setup And Early Campaign

| Script | Purpose |
|---|---|
| `04_loadtest_6gpu.sh` | Six-GPU Desmond load test |
| `05_gpu_queue_runner.py` | Initial generic job runner |
| `05_phaseA_6gpu_queue.py` | Phase A six-GPU screening queue |
| `06_sea_extract_completed.py` | SEA extraction for completed early jobs |
| `06b_export_dat_from_eaf.py` | Recover SEA data tables from EAF |
| `06c_export_data_only.py` | Data-only SEA report export |
| `06d_export_plots_only.py` | Plot-only SEA report export |
| `07_analyze_md12.py` | Initial 12-molecule RMSD/contact analysis |
| `07_phaseB200_top6_6gpu.py` | Early 200 ns queue |
| `08_build_md27_canvas.py` | Interactive MD overview canvas |
| `08_phaseC_next13_6gpu.py` | Next-candidate queue |
| `09_sea_extract_b200.py` | Early 200 ns SEA extraction |
| `10_phaseD_new13_6gpu.py` | Additional-candidate queue |
| `11_md200_inventory.py` | 200 ns file and trajectory inventory |
| `12_analyze_md200.py` | Pocket/contact-aware 200 ns unified analysis |

## Corrected-Pose 2+50 ns Screening

| Script | Purpose |
|---|---|
| `corrected_pose_common.py` | Kabsch, PBC, topology, and corrected-pose helpers |
| `13_audit_initial_poses.py` | Detect docking/template coordinate-frame errors |
| `14_prepare_corrected_pose_all40.py` | Transform ligands into the MD template frame |
| `15_build_corrected_pose_all40.py` | Rebuild and hard-QC corrected full systems |
| `16_phaseE_corrected_all40_6gpu.py` | Resumable six-GPU 2+50 ns queue |
| `17_phaseE_watchdog.py` | Phase E watchdog |
| `18_phaseE_four_hour_monitor.sh` | Periodic Phase E monitor |
| `19_sea_extract_phaseE.py` | Phase E SEA extraction |
| `20_plot_phaseE_rmsd.py` | Publication-style short-MD RMSD figures |
| `21_phaseE_auto_analysis.py` | Automated Phase E analysis |
| `22_collect_phaseE_schrodinger_reports.py` | Collect official reports |
| `23_analyze_phaseE_pocket_geometry.py` | Pocket geometry, contacts, convergence, and clustering |

## Medoid 2+200 ns Campaign

| Script | Purpose |
|---|---|
| `phaseF_common.py` | Phase F paths, candidates, PBC, and validation helpers |
| `24_prepare_phaseF_medoid_top16.py` | Full-system medoid extraction and input QC |
| `25_phaseF_200ns_4gpu.py` | Four-GPU dynamic queue, retries, and hard validation |
| `26_phaseF_sea.py` | Validated-trajectory SEA |
| `27_phaseF_post_analysis.py` | SEA, official reports, and unified analysis orchestration |
| `28_phaseF_watchdog.py` | Queue and post-analysis watchdog |
| `29_phaseF_burst_last2_gpu01.py` | Temporary GPU0/1 burst assignment |
| `30_phaseF_burst_last4_3_gpu01.py` | Temporary last-job reassignment |
| `31_prepare_phaseF_extra2_gpu01.py` | First two supplemental medoid inputs |
| `32_phaseF_extra2_gpu01_queue.py` | Supplemental GPU0/1 queue |
| `33_phaseF_extra2_watchdog.py` | Supplemental GPU0/1 watchdog |
| `34_prepare_phaseF_extra34_gpu25.py` | Final two supplemental medoid inputs |
| `35_phaseF_extra34_gpu25_queue.py` | Supplemental GPU2/5 queue |
| `36_phaseF_extra34_watchdog.py` | Supplemental GPU2/5 watchdog |
| `37_plot_phaseF_md200_5x4.py` | Portrait-A4 5-by-4 RMSD plate |
| `38_phaseF_extra2_post_analysis.py` | Incremental SEA, analysis, merge, and plotting |
| `39_plot_phaseE_md50_10x4.py` | Portrait-A4 10-by-4 plate for all 40 corrected-pose 50 ns trajectories |
| `40_export_phaseE_tables_only.py` | Flat CSV-only export for 40-molecule RMSD, RMSF, residue-contact heatmaps, pocket geometry, and QC |
| `41_phaseF_full20_post_analysis.py` | Incremental final-two SEA and analysis, full-20 merge, plate, and tables-only orchestration |
| `42_export_phaseF_full20_tables_only.py` | Full-20 CSV-only export for decisions, dynamics, RMSF, residue-contact heatmaps, transitions, and validation |
| `43_phaseF_full20_analysis_watchdog.py` | Persistent hard-validation gate that launches the full-20 analysis without using GPUs |

## Protocols And Utility Shells

`protocols/` contains the membrane build, 1 ns load test, 2+50 ns, and 2+200 ns MSJ files. `build_missing_cms.sh`, `build_phaseD_cms.sh`, and `start_phaseA_when_ready.sh` preserve the corresponding setup automation. `30_phaseE_wps_resume_upload.py` preserves report upload/resume logic.
