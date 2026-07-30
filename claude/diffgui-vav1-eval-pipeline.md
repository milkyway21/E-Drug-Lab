# DiffGUI 生成 + correct-reconstruct 评估链路（VAV1, 2026-06-20）

> 端到端跑通：DiffGUI 在 GPU5 生成 11 个 VAV1 分子胶候选 → 转换 .pt → evaluate_pt_with_correct_reconstruct 评估 5 个，全部成功。

## 链路

```
9nfr.pdb + 9nfrligand.pdb  (VAV1_degron/)
   │
   ├─ extract_pockets.py --protein 9nfr.pdb --ligand 9nfrligand.sdf --radius 10
   │   → vav1_pocket.pdb (40 残基/350 原子)
   │
   ├─ DiffGUI 生成 (GPU5, diffgui_new env, sample_vav1.yml)
   │   run_batch_generate.py --num_mols 10 --batch_size 5 --device cuda:0 (CUDA_VISIBLE_DEVICES=5)
   │   → samples_vav1.pt  (pool.finished=[{element, atom_pos, smiles, rdmol, vina_score,...}])
   │
   ├─ convert_diffgui_pt_to_eval.py  (diffdynamic env, PYTHONPATH=/data/ye/DiffDynamic)
   │   DiffGUI {finished:[{element(原子序数),atom_pos}]} → TargetDiff {pred_ligand_pos,pred_ligand_v(索引),data}
   │   add_aromatic 反映射；--ligand_filename N/A（避开受体命名冲突）
   │   → converted_for_eval.pt
   │
   └─ evaluate_pt_with_correct_reconstruct.py  (diffdynamic env)
       --receptor_pdb 9nfr.pdb --protein_root VAV1_degron --atom_mode add_aromatic
       --vina-timeout-seconds 20 --max_samples 5
       → evaluation_results.xlsx + report + reconstructed_molecules/*.sdf
```

## 关键文件

- 生成入口：`/data/ye/diffgui/scripts/run_batch_generate.py`（`--protein_file` 只进 metadata，真正 target 由 sample.yml 的 `model.target` 决定）
- VAV1 config：`/data/ye/diffgui/configs/sample/sample_vav1.yml`（target: sample/vav1_pocket.pdb, batch_size 5, ligand_atom_mode aromatic）
- 转换器：`/data/ye/e-drug-lab/backend/scripts/convert_diffgui_pt_to_eval.py`
- 评估器：`/data/ye/DiffDynamic/evaluate_pt_with_correct_reconstruct.py`
- 权重：`/data/ye/diffgui/ckpt/{trained.pt(98M), bond_trained.pt(82M)}`（从 gdrive 1pQk1FASCnCLjYRd7yc17WfctoHR50s2r 经 7890 代理下载）
- 项目数据：`/data/ye/e-drug-lab/data/VAV1_degron/{9nfr.pdb, 9nfrligand.sdf, vav1_pocket.pdb}`
- round_100 输出：`/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_100/`

## 跑通此链路修掉的 bug（vendored repo 补丁）

### /data/ye/diffgui （diffgui_new env, numpy 1.26 / meeko 0.4.0）
1. `utils/parser.py` + `utils/data.py`：`np.long→np.int64, np.bool→np.bool_, np.int→np.int64`（numpy 弃用别名）
2. protobuf 降级 3.20.3（tensorboard 导入冲突）
3. 装 `pdb2pqr30` 3.6.2（PrepProt.addH 受体质子化必需）
4. `utils/evaluation/docking_vina.py` PrepLig.get_pdbqt：meeko 0.4 不再接受 OBMol，改用 `mp.prepare(rdkit_mol) + mp.write_pdbqt_string()`（OBMol→RDKit 经 sdf block）

### /data/ye/DiffDynamic （diffdynamic env, meeko 0.1.dev3）
5. `utils/reconstruct.py` make_obmol：`atom.SetVector(float(x),float(y),float(z))` + `int(t)`（SWIG 拒绝 numpy 标量，否则对接前 reconstruct 全失败）
6. `evaluate_pt_with_correct_reconstruct.py` dock_reference_ligand：meeko 0.1.dev3 仅接受 OBMol，改用 `PrepLig(sdf).get_pdbqt()`（原代码传 RDKit Mol 报 NumAtoms 错）
7. **受体命名冲突**：`9nfrligand.pdb`（配体 PDB）存在时，resolve_receptor_pdb_for_docking 按 CrossDocked 约定（ligand stem→protein pdb）误把它当受体。解决：把 `9nfrligand.pdb` 改名 `9nfrligand_orig.pdb` + 转换器设 `--ligand_filename N/A`，强制走 explicit protein_path=9nfr.pdb

### e-drug-lab backend
8. `services/diffgui_runner.py` + `routes/diffgui.py`：run_generate / GenerateRequest 加 `device` + `config` 形参（支持 cuda:5）

## 评估结果（round_100, 5 分子）

| # | Vina_dock | score_only | QED | SA | logP | Lipinski | PAINS | Lilly | 综合分 |
|---|-----------|-----------|------|------|------|------|-------|-------|-------|
| 0 | -12.56 | -11.22 | 0.74 | 0.70 | 2.43 | 5/5 | 无 | 通过 | 77.5 |
| 1 | -9.36 | -8.60 | 0.85 | 0.88 | 4.86 | 5/5 | 无 | 未过 | 78.7 |
| 2 | -12.79 | -11.48 | 0.84 | 0.63 | 3.33 | 5/5 | 无 | 通过 | 87.7 |
| 3 | -11.18 | -9.44 | 0.56 | 0.61 | 2.27 | 5/5 | 无 | 通过 | 69.1 |
| 4 | -12.18 | -10.71 | 0.78 | 0.65 | 1.88 | 5/5 | 无 | 通过 | 86.4 |

综合分公式：100×(0.4×亲和力归一 + 0.3×QED + 0.2×SA + 0.1×Lipinski)×PAINS惩罚×稳定性惩罚

## 已知遗留

- DiffGUI 后处理 `run_batch_generate.py` 因 sample.py 不写 `SMILES.txt` 报"无有效分子"退出码非0，但 `samples_*.pt` 已正常生成（不影响评估链路；仅影响 DiffGUI 自带入库）
- `evaluate_pt_with_correct_reconstruct.py` 评估不含 ADMET（ADMET 是 e-drug-lab 独立 admet_service，22+ 项，需另接）
- `sampling_history.xlsx` 读取报损坏（无关紧要的历史记录文件）

## 相关
- [[workflow-diffgui-glare-wetlab]] —— 整体闭环
- [[rl-path]] —— GLARE 强化学习
- [[env-and-tool-runtime]] —— conda 环境
