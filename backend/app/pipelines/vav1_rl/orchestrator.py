"""RL closed-loop pipeline orchestrator (legacy package name vav1_rl).

默认执行步骤 1–8, 10–11（跳过 step9 相似搜索）。最终排序权重固定 0.05/0.15/0.8。
复用 e-drug-lab 服务（admet_service / vina_service / orthogonal_scoring / sdf_parser / sa_score /
glare_runner / diffgui_runner / rl_round_service / pipeline_eval_bridge）+ 本包核心模块
（rdkit_utils / admet_rules / schrodinger_local / glare_gnn_adapter）。

所有中间结果 csv + xlsx 双存；每步留全量候选 + rejected_reason + retained/rejected 计数。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from . import rdkit_utils, admet_rules

try:
    from . import schrodinger_local as sch
    _SCHRODINGER_AVAILABLE = sch.health().get("ok", False)
except Exception:
    sch = None
    _SCHRODINGER_AVAILABLE = False

logger = logging.getLogger(__name__)

# 数据资产路径
KNOWN_439_XLSX = "/data/ye/e-drug-lab/glaretrain/DataSet-GNN-SMILES-pDC50.xlsx"
LARGE_LIBRARY_SMI = "/data/ye/diffgui/third_party/GLARE/data/EnamineHTS/original/inactives.smi"
VAV1_POCKET_PDB = "/data/ye/diffgui/sample/vav1_pocket.pdb"
CRBN_PDB = "/data/ye/diffgui/data/vav1/crbn.pdb"
ROUND200_MERGED = "/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200/merged/round_200_merged_eval.xlsx"

PROJECT_ROOT_DEFAULT = "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project"

FINAL_REPORT_FIRST_LINE = "本流程按生成-筛选-强化学习闭环执行（默认跳过相似搜索），最终排序权重未改。"

# 最终排序权重（固定，不可改）
W_MODEL = 0.05
W_AFFINITY = 0.15
W_GLARE = 0.80


def _now() -> str:
    return datetime.utcnow().isoformat()


class VAV1RLOrchestrator:
    def __init__(
        self,
        project_root: str = PROJECT_ROOT_DEFAULT,
        mode: str = "test",          # test | full
        num_mols: int = 1000,
        reuse_sdf_dir: Optional[str] = None,
        schrodinger_install: str | None = None,
        ph: float | None = None,
        log_to_stdout: bool = True,
    ):
        # 从 pydantic Settings 取默认值（参数未显式传入时）
        try:
            from app.config import get_settings
            _s = get_settings().schrodinger
        except Exception:
            _s = None
        self.schrodinger_install = schrodinger_install or (_s.install_path if _s else "/opt/schrodinger2023-3")
        self.ph = ph if ph is not None else (_s.ph if _s else 7.2)
        self.project_root = Path(project_root)
        self.mode = mode
        self.num_mols = num_mols
        self.reuse_sdf_dir = reuse_sdf_dir
        self.log_to_stdout = log_to_stdout

        self.ensure_dirs()
        self.funnel: dict[int, dict[str, int]] = {}
        self.status: dict[str, Any] = {"current_step": None, "mode": mode, "started_at": _now(), "steps_done": []}
        # 口袋由当前研究靶标决定（内部仍可复用项目 pocket PDB）
        self.pocket_type = "target_pocket"

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    def ensure_dirs(self):
        for sub in ["data/processed", "diffgui_generation", "screening", "docking", "glare", "similarity", "round2", "reports", "logs"]:
            (self.project_root / sub).mkdir(parents=True, exist_ok=True)

    def log(self, msg: str):
        line = f"[{_now()}] {msg}"
        if self.log_to_stdout:
            print(line, flush=True)
        with open(self.project_root / "logs" / "full_pipeline.log", "a") as f:
            f.write(line + "\n")

    def _record_funnel(self, step: int, total: int, retained: int, rejected: int):
        self.funnel[step] = {"total": total, "retained": retained, "rejected": rejected}
        self.log(f"step{step} 漏斗: total={total} retained={retained} rejected={rejected}")

    def _save_csv_xlsx(self, df: pd.DataFrame, rel_path_no_ext: str) -> tuple[str, str]:
        csv_p = self.project_root / f"{rel_path_no_ext}.csv"
        xlsx_p = self.project_root / f"{rel_path_no_ext}.xlsx"
        csv_p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_p, index=False)
        try:
            df.to_excel(xlsx_p, index=False)
        except Exception as e:
            self.log(f"xlsx 写入失败 {xlsx_p}: {e}")
        return str(csv_p), str(xlsx_p)

    # ------------------------------------------------------------------
    # 步骤1 — patent 预处理 + 4 轮 GLARE 预训练
    # ------------------------------------------------------------------
    def step1_pretrain(self) -> dict:
        from . import glare_gnn_adapter
        self.log("=== Step1: patent 预处理 + 4 轮 GLARE 预训练 ===")
        df = pd.read_excel(KNOWN_439_XLSX)
        df.columns = [c.strip() for c in df.columns]
        cpd = df.iloc[:, 0].astype(str)
        patent = df[cpd.str.startswith("PAT")].copy()
        patent.columns = ["molecule_id", "smiles", "pdc50"]

        # 标准化
        records = []
        invalid = []
        for _, row in patent.iterrows():
            s = rdkit_utils.standardize(str(row["smiles"]))
            if not s["mol_valid"]:
                invalid.append({"molecule_id": row["molecule_id"], "smiles": row["smiles"], "reason": "invalid"})
                continue
            pdc = float(row["pdc50"])
            rec = {
                "molecule_id": row["molecule_id"],
                "smiles": str(row["smiles"]),
                "canonical_smiles": s["canonical_smiles"],
                "neutralized_smiles": s["neutralized_smiles"],
                "inchikey": s["inchikey"],
                "pdc50_raw": pdc,
                "pdc50_norm": max(0.0, min(1.0, (pdc - 5.0) / 4.0)),
                "label_active": 1 if pdc >= 7.0 else (0 if pdc < 6.0 else -1),  # -1 = weak
                "strong_active": 1 if pdc >= 8.0 else 0,
                "sample_weight": 1.2 if pdc >= 8.0 else (1.0 if pdc >= 7.0 else (0.5 if pdc >= 6.0 else 1.0)),
                "source": "patent",
            }
            records.append(rec)

        valid = [r for r in records if r["label_active"] in (0, 1)]
        weak = [r for r in records if r["label_active"] == -1]
        self.log(f"patent 有效={len(records)} 强分类={len(valid)} weak={len(weak)} 无效={len(invalid)}")
        if len(records) < 400:
            return {"ok": False, "error": f"有效分子 {len(records)} < 400，数据不足"}

        self._save_csv_xlsx(pd.DataFrame(records), "data/processed/patent_403_cleaned")
        self._save_csv_xlsx(pd.DataFrame(invalid), "data/processed/patent_invalid_records")

        # 100 四分子组（前 400），剩 3 holdout
        first400 = records[:400]
        remainder = records[400:]
        groups = []
        for gi in range(100):
            grp = first400[gi * 4:(gi + 1) * 4]
            for m in grp:
                m["group_id"] = f"patent_group_{gi + 1:03d}"
            groups.extend(grp)
        self._save_csv_xlsx(pd.DataFrame(groups), "data/processed/patent_groups_100")
        if remainder:
            self._save_csv_xlsx(pd.DataFrame(remainder), "data/processed/patent_remainder_3")

        # 4 轮预训练（累积 + 续训）
        training_log = []
        ckpt_prev = None
        for rnd in range(1, 5):
            lo = (rnd - 1) * 25 + 1
            hi = rnd * 25
            group_ids = {f"patent_group_{i:03d}" for i in range(lo, hi + 1)}
            round_data = [m for m in groups if m["group_id"] in group_ids]
            # weak_active 低权重纳入（label 取 0，weight 已 0.5）
            smiles = [m["neutralized_smiles"] for m in round_data]
            labels = [m["label_active"] if m["label_active"] in (0, 1) else 0 for m in round_data]
            weights = [m["sample_weight"] for m in round_data]
            ckpt = str(self.project_root / "glare" / f"pretrain_round_{rnd}_checkpoint.pt")
            self.log(f"pretrain round {rnd}: groups {lo:03d}-{hi:03d}, n={len(smiles)}")
            _ep = int(os.environ.get("VAV1_GLARE_EPOCHS", "50"))
            _ens = int(os.environ.get("VAV1_GLARE_ENSEMBLE", "3"))
            res = glare_gnn_adapter.train(
                ckpt, smiles, labels, weights,
                prev_checkpoint=ckpt_prev,
                epochs=_ep,
                ensemble_size=_ens,
            )
            training_log.append({"round": rnd, "n": len(smiles), "ok": res.get("ok"), "loss": res.get("final_loss"), "checkpoint": ckpt})
            if res.get("ok"):
                ckpt_prev = ckpt
            else:
                self.log(f"round {rnd} 训练失败: {res.get('error')}")
        self._save_csv_xlsx(pd.DataFrame(training_log), "glare/pretrain_training_log")
        self._record_funnel(1, len(records), len(records), len(invalid))
        return {"ok": True, "pretrain_round4_ckpt": ckpt_prev, "n_patent_valid": len(records), "n_invalid": len(invalid)}

    # ------------------------------------------------------------------
    # 步骤2 — DiffGui 生成
    # ------------------------------------------------------------------
    def step2_generate(self) -> dict:
        self.log("=== Step2: DiffGui 生成 ===")
        if self.mode == "test" and (self.reuse_sdf_dir or ROUND200_MERGED):
            # 测试模式：复用 round_200 的 922 denovo 评估表作为生成池
            src = pd.read_excel(ROUND200_MERGED)
            smi_col = next(c for c in src.columns if c.upper() == "SMILES")
            gen = src[[smi_col]].rename(columns={smi_col: "generated_smiles"}).head(self.num_mols)
            gen["generation_id"] = [f"GEN_R200_{i:05d}" for i in range(len(gen))]
            gen["generation_mode"] = "denovo"
            gen["source_scaffold_id"] = None
            gen["source_fragment_smiles"] = None
            gen["pocket_file"] = VAV1_POCKET_PDB
            gen["requested_affinity_condition"] = "<= -6 kcal/mol (生成后 Vina 过滤)"
            gen["mapping_rule"] = "DiffGui aff=-log10(Kd) 与 kcal/mol 不兼容；生成后用 Vina dock 过滤 <=-6"
            self.log(f"测试模式：复用 round_200 {len(gen)} 分子作为 denovo 生成池")
        else:
            # full 模式：调 diffgui_runner 拆 60% frag_cond + 40% denovo（实际跑需 GPU）
            return self._step2_generate_full()
        csv_p, _ = self._save_csv_xlsx(gen, "diffgui_generation/generated_10000_raw")
        manifest = {"mode": self.mode, "num_mols": len(gen), "pocket_type": self.pocket_type, "pocket_file": VAV1_POCKET_PDB, "mapping_rule": gen["mapping_rule"].iloc[0]}
        (self.project_root / "diffgui_generation" / "generation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        self._record_funnel(2, len(gen), len(gen), 0)
        return {"ok": True, "generated_csv": csv_p, "num_mols": len(gen)}

    def _step2_generate_full(self) -> dict:
        num_frag = round(self.num_mols * 0.6)
        num_denovo = self.num_mols - num_frag
        # TODO: full 模式需调 diffgui_runner 拆 frag_cond(60%)+denovo(40%) 子运行 + GPU + 临时 sample.yml override
        self.log(f"full 模式 frag_cond={num_frag} denovo={num_denovo}（需 GPU 实跑）")
        return {"ok": False, "error": "full 生成需 GPU 实跑，本次测试模式未执行", "num_frag": num_frag, "num_denovo": num_denovo}

    # ------------------------------------------------------------------
    # 步骤3 — 化学有效性 11 项 + 22 ADMET
    # ------------------------------------------------------------------
    def step3_validity_admet(self) -> dict:
        from app.services import admet_service
        self.log("=== Step3: 11 项有效性 + 22 ADMET ===")
        gen = pd.read_csv(self.project_root / "diffgui_generation/generated_10000_raw.csv")
        rows = []
        # 先做有效性检查，仅对通过的有效分子喂 ADMET（减少 admet-ai 对畸形分子的 C++ 崩溃面）
        validity_results = []
        valid_smiles = []
        valid_idx = []
        for i, row in gen.iterrows():
            smi = row["generated_smiles"]
            v = rdkit_utils.validity_check_11(smi)
            validity_results.append(v)
            if v["overall"]:
                valid_smiles.append(smi)
                valid_idx.append(i)

        # 批量 ADMET（仅有效分子）
        admet_map: dict[int, dict] = {}
        if valid_smiles:
            try:
                admet_results = admet_service.predict_batch(valid_smiles, batch_size=16)
                for j, idx in enumerate(valid_idx):
                    admet_map[idx] = admet_results[j].properties if j < len(admet_results) else {}
            except Exception as e:
                self.log(f"ADMET 批量失败，逐分子降级: {e}")
                for idx, smi in zip(valid_idx, valid_smiles):
                    try:
                        ap = admet_service.predict_single(smi)
                        admet_map[idx] = ap.properties
                    except Exception:
                        admet_map[idx] = {}

        for i, row in gen.iterrows():
            v = validity_results[i]
            admet_props = admet_map.get(i, {})
            admet_cls = admet_rules.classify(admet_props) if admet_props else {
                "admet_pass_flag": False, "admet_reject_reason": "ADMET 预测失败/跳过",
                "admet_warning_count": 0, "admet_fail_count": 0, "admet_severe_fail_count": 0,
                "admet_penalty": 0, "endpoint_labels": {}, "key_toxic_fails": [], "severe_fails": [], "all_fails": [], "all_warnings": [],
            }
            rec = {**row.to_dict(), **v, **admet_cls, "admet_properties": json.dumps(admet_props, ensure_ascii=False, default=str)}
            rec["validity_pass"] = v["overall"]
            rec["reject_reason"] = None
            if not v["overall"]:
                rec["reject_reason"] = "有效性失败: " + "; ".join(v["reasons"])
            elif not admet_cls["admet_pass_flag"]:
                rec["reject_reason"] = admet_cls["admet_reject_reason"]
            rows.append(rec)
        df = pd.DataFrame(rows)
        if "reject_reason" not in df.columns:
            df["reject_reason"] = None
        self._save_csv_xlsx(df, "screening/step3_validity_admet_all")
        retained = df[df["reject_reason"].isna()].reset_index(drop=True)
        rejected = df[df["reject_reason"].notna()].reset_index(drop=True)
        self._save_csv_xlsx(retained, "screening/step3_retained")
        self._save_csv_xlsx(rejected, "screening/step3_rejected")
        self._record_funnel(3, len(df), len(retained), len(rejected))
        return {"ok": True, "retained": len(retained), "rejected": len(rejected)}

    # ------------------------------------------------------------------
    # 步骤4 — 成药性第一轮
    # ------------------------------------------------------------------
    def step4_druglikeness(self) -> dict:
        self.log("=== Step4: 成药性第一轮 ===")
        df = pd.read_csv(self.project_root / "screening/step3_retained.csv")
        rows = []
        for _, r in df.iterrows():
            from rdkit import Chem
            mol = Chem.MolFromSmiles(r["generated_smiles"])
            if mol is None:
                r["reject_reason"] = "RDKit 无法解析"
                rows.append(r.to_dict())
                continue
            desc = rdkit_utils.druglikeness_descriptors(mol)
            lip = rdkit_utils.lipinski_pass_count(mol)
            lil = rdkit_utils.lilly_score(mol)
            from app.services.sa_score import compute_sa_score
            sa = compute_sa_score(mol)
            rec = {**r.to_dict(), **desc, **lip, "sa": sa, **{f"lilly_{k}" if k != "lilly_score" else k: v for k, v in lil.items()}}
            # 硬规则
            reject = None
            if desc["qed"] < 0.3:
                reject = f"QED={desc['qed']} < 0.3"
            elif sa is not None and sa >= 5:
                reject = f"SA={sa} >= 5"
            elif not (1.0 <= desc["logp"] <= 3.5):
                reject = f"LogP={desc['logp']} 不在 1-3.5"
            elif not (40 <= desc["tpsa"] <= 90):
                reject = f"TPSA={desc['tpsa']} 不在 40-90"
            elif lip["lipinski_pass_count"] < 4:
                reject = f"Lipinski pass={lip['lipinski_pass_count']} < 4"
            elif lil["lilly_score"] > 100:
                reject = f"Lilly={lil['lilly_score']} > 100"
            rec["reject_reason"] = reject
            # model_druglikeness_score（仅排序）
            rec["model_druglikeness_score"] = (
                desc["qed"] / 1.0 + (5 - (sa or 5)) / 5 + (1 - abs(desc["logp"] - 2.25) / 1.25)
                + (1 - abs(desc["tpsa"] - 65) / 25) - r.get("admet_penalty", 0) * 0.01 - lil["lilly_score"] * 0.001
            )
            rows.append(rec)
        out = pd.DataFrame(rows)
        self._save_csv_xlsx(out, "screening/step4_druglikeness_round1_all")
        retained = out[out["reject_reason"].isna()].reset_index(drop=True)
        rejected = out[out["reject_reason"].notna()].reset_index(drop=True)
        self._save_csv_xlsx(retained, "screening/step4_druglikeness_retained")
        self._save_csv_xlsx(rejected, "screening/step4_druglikeness_rejected")
        self._record_funnel(4, len(out), len(retained), len(rejected))
        return {"ok": True, "retained": len(retained), "rejected": len(rejected)}

    # ------------------------------------------------------------------
    # 步骤5 — Vina + Glide XP + MM-GBSA 正交
    # ------------------------------------------------------------------
    @staticmethod
    def _smiles_to_sdf(smiles_list: list[str], sdf_path: str):
        """把 SMILES 列表写为 3D SDF（供 Schrödinger ligprep 使用）。复用 rdkit_utils 逻辑。"""
        from rdkit import Chem
        from rdkit.Chem import AllChem
        writer = Chem.SDWriter(sdf_path)
        for i, smi in enumerate(smiles_list):
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                continue
            mol = Chem.AddHs(mol)
            try:
                AllChem.EmbedMolecule(mol, randomSeed=2023)
            except Exception:
                pass
            mol = Chem.RemoveHs(mol)
            mol.SetProp("_Name", f"mol_{i:05d}")
            writer.write(mol)
        writer.close()

    def step5_affinity(self) -> dict:
        self.log("=== Step5: Vina + Glide XP + MM-GBSA 正交对接 ===")
        in_path = self.project_root / "screening/step4_druglikeness_retained.csv"
        if not in_path.is_file():
            in_path = self.project_root / "screening/step4_druglikeness_round1_all.csv"
        df = pd.read_csv(in_path)
        self.log(f"step5 候选 {len(df)} 分子；Vina/Glide/MMGBSA 三模型正交")

        # 初始化 column
        out = df.copy()
        out["vina_score"] = None
        out["glide_xp_score"] = None
        out["mmgbsa_dg"] = None
        out["schrodinger_ran"] = False

        # ---- Vina ----
        if "Vina_Dock_亲和力" in out.columns:
            out["vina_score"] = pd.to_numeric(out["Vina_Dock_亲和力"], errors="coerce")
            self.log(f"  Vina: 复用 round_200 已有 {out['vina_score'].notna().sum()} 个分数")
        else:
            # 否则调 vina_service 跑批量对接
            self.log("  Vina: 暂无预计算分数（需启动实时对接，当前跳过）")

        # ---- Schrödinger Glide XP + MM-GBSA ----
        if _SCHRODINGER_AVAILABLE and sch is not None and self.mode != "test":
            try:
                self.log(f"  Schrödinger: 启动端到端对接 (install={self.schrodinger_install}, pH={self.ph})")
                # 将 retained SMILES 转为 SDF
                smi_list = out["generated_smiles" if "generated_smiles" in out.columns else "smiles"].astype(str).tolist()
                sdf_path = str(self.project_root / "docking" / "step5_ligands.sdf")
                self._smiles_to_sdf(smi_list, sdf_path)

                dock_result = sch.end_to_end_dock(
                    ligands_sdf=sdf_path,
                    receptor_pdb=VAV1_POCKET_PDB,
                    output_dir=str(self.project_root),
                    install_path=self.schrodinger_install,
                    ph=self.ph,
                    box_center=None,  # 自动从 PDB 质心计算
                )
                self.log(f"  Schrödinger steps: {[(s['step'], s['ok']) for s in dock_result.get('steps_log', [])]}")
                # 按 title 匹配回 DataFrame
                gmap = {s["title"]: s.get("glide_xp_score") for s in dock_result.get("glide_scores", [])}
                mmap = {s["title"]: s.get("mmgbsa_dg") for s in dock_result.get("mmgbsa_scores", [])}
                for i, row in out.iterrows():
                    name = row.get("generated_id", row.get("name", f"mol_{i}"))
                    out.at[i, "glide_xp_score"] = gmap.get(name)
                    out.at[i, "mmgbsa_dg"] = mmap.get(name)
                out["schrodinger_ran"] = dock_result.get("all_ok", False)
                self.log(f"  Schrödinger: 完成, all_ok={dock_result.get('all_ok')}, glide={len(gmap)}, mmgbsa={len(mmap)}")
            except Exception as e:
                self.log(f"  Schrödinger 失败: {e} — 回退到 Vina-only")
        else:
            self.log("  Schrödinger: 跳过 (test 模式或未安装, Vina-only surrogate)")

        # ---- 归一化 + consensus ----
        for col in ["vina_score", "glide_xp_score", "mmgbsa_dg"]:
            vals = pd.to_numeric(out[col], errors="coerce")
            if vals.notna().sum() > 1:
                # rank percentile: 越负（越小）越好 → 反转使越大越好
                out[col + "_norm"] = 1.0 - vals.rank(pct=True)
            else:
                out[col + "_norm"] = 0.5  # 缺数据给中性

        # affinity_consensus = 0.1*vina_norm + 0.3*glide_norm + 0.6*mmgbsa_norm
        # 若 Schrödinger 未跑 → vina 权重提升为 1.0
        if out["schrodinger_ran"].any():
            out["affinity_consensus_score"] = (
                0.1 * out["vina_score_norm"].fillna(0.5)
                + 0.3 * out["glide_xp_score_norm"].fillna(0.5)
                + 0.6 * out["mmgbsa_dg_norm"].fillna(0.5)
            )
            self.log("  Consensus: 0.1*vina + 0.3*glide + 0.6*mmgbsa")
        else:
            out["affinity_consensus_score"] = out["vina_score_norm"].fillna(0.5)
            self.log("  Consensus: Vina-only surrogate (Schrödinger 未跑)")

        # ---- 正交门槛 ----
        out["reject_reason"] = out.get("reject_reason", None)
        retained_mask = pd.Series(True, index=out.index)
        # 简化：各模型进前 40%，或放宽底线
        for col in ["vina_score_norm", "glide_xp_score_norm", "mmgbsa_dg_norm"]:
            if col in out.columns:
                threshold = out[col].quantile(0.4) if out[col].notna().sum() > 5 else 0.0
                # norm 越大越好,低于 40% 分位记但仅当三模型都差才剔
                below = out[col] < threshold
                out.loc[below & out[col].notna(), "reject_reason"] = (
                    out.loc[below & out[col].notna(), "reject_reason"].fillna("") + f"; {col}_below_40pct"
                )

        # 按 consensus 排序（仅排序，不硬剔——除非所有模型都缺数据）
        out = out.sort_values("affinity_consensus_score", ascending=False).reset_index(drop=True)

        self._save_csv_xlsx(out, "screening/step5_affinity_orthogonal_all")
        retained = out[retained_mask].copy()
        rejected = out[~retained_mask].copy()
        self._save_csv_xlsx(retained, "screening/step5_affinity_orthogonal_retained")
        self._save_csv_xlsx(rejected, "screening/step5_affinity_orthogonal_rejected")
        self._record_funnel(5, len(df), len(retained), len(rejected))
        return {"ok": True, "retained": len(retained), "schrodinger_ran": bool(out["schrodinger_ran"].any()),
                "consensus_mode": "0.1/0.3/0.6" if out["schrodinger_ran"].any() else "Vina-only surrogate"}

    # ------------------------------------------------------------------
    # 步骤6 — 去重
    # ------------------------------------------------------------------
    def step6_dedup(self) -> dict:
        self.log("=== Step6: 去重 vs large_library + known_439 ===")
        df = pd.read_csv(self.project_root / "screening/step5_affinity_orthogonal_retained.csv")
        # 参考库
        known = pd.read_excel(KNOWN_439_XLSX)
        known_smi = known.iloc[:, 1].astype(str).tolist()
        known_canon = {rdkit_utils.standardize(s)["canonical_smiles"] for s in known_smi if rdkit_utils.standardize(s)["canonical_smiles"]}
        known_ik = {rdkit_utils.standardize(s)["inchikey"] for s in known_smi if rdkit_utils.standardize(s)["inchikey"]}
        known_ik1 = {rdkit_utils.inchikey_first_block(ik) for ik in known_ik if ik}
        # large_library（2.1M，抽样或全量读；先读前 50万）
        large_smi = []
        if Path(LARGE_LIBRARY_SMI).is_file():
            with open(LARGE_LIBRARY_SMI) as f:
                for i, line in enumerate(f):
                    if i >= 500000:
                        break
                    large_smi.append(line.split()[0])
        large_canon = {rdkit_utils.standardize(s)["canonical_smiles"] for s in large_smi[:50000] if rdkit_utils.standardize(s)["canonical_smiles"]}

        from rdkit import Chem
        rows = []
        for _, r in df.iterrows():
            smi = r["generated_smiles"]
            s = rdkit_utils.standardize(smi)
            mol = Chem.MolFromSmiles(s["canonical_smiles"]) if s["canonical_smiles"] else None
            cand = {"canonical_smiles": s["canonical_smiles"], "inchikey": s["inchikey"], "mol": mol}
            # vs known_439
            chk1 = rdkit_utils.dedup_check(cand, known_canon, known_ik, known_ik1, [])
            # vs large_library
            chk2 = rdkit_utils.dedup_check(cand, large_canon, set(), set(), [])
            reject = chk1["reject"] or chk2["reject"]
            flags = chk1["flags"] + chk2["flags"]
            rec = r.to_dict()
            rec["dedup_flags"] = ";".join(flags)
            rec["reject_reason"] = chk1["reason"] or chk2["reason"] if reject else None
            rows.append(rec)
        out = pd.DataFrame(rows)
        if "reject_reason" not in out.columns:
            out["reject_reason"] = None
        if "dedup_flags" not in out.columns:
            out["dedup_flags"] = None
        self._save_csv_xlsx(out, "screening/step6_dedup_all")
        retained = out[out["reject_reason"].isna()].reset_index(drop=True)
        rejected = out[out["reject_reason"].notna()].reset_index(drop=True)
        self._save_csv_xlsx(retained, "screening/step6_nonduplicate_retained")
        self._save_csv_xlsx(rejected, "screening/step6_duplicate_rejected")
        self._record_funnel(6, len(out), len(retained), len(rejected))
        return {"ok": True, "retained": len(retained), "rejected": len(rejected)}

    # ------------------------------------------------------------------
    # 步骤7 — GLARE 排序
    # ------------------------------------------------------------------
    def step7_glare_rank(self, checkpoint: Optional[str] = None) -> dict:
        from . import glare_gnn_adapter
        self.log("=== Step7: GLARE 排序 ===")
        df = pd.read_csv(self.project_root / "screening/step6_nonduplicate_retained.csv")
        if checkpoint is None:
            checkpoint = str(self.project_root / "glare" / "pretrain_round_4_checkpoint.pt")
        if not Path(checkpoint).is_file():
            # fallback 最新
            cands = sorted((self.project_root / "glare").glob("*checkpoint.pt"))
            if cands:
                checkpoint = str(cands[-1])
                self.log(f"pretrain_round_4 不存在，用最新 {checkpoint}")
        res = glare_gnn_adapter.query(checkpoint, df["generated_smiles"].tolist())
        ranked = res.get("ranked", [])
        rdf = pd.DataFrame(ranked)
        if not rdf.empty:
            rdf = rdf.merge(df, left_on="smiles", right_on="generated_smiles", how="left")
        self._save_csv_xlsx(rdf, "glare/step7_glare_ranked_all")
        self._save_csv_xlsx(rdf.head(200), "glare/step7_glare_top_candidates")
        self._record_funnel(7, len(df), len(rdf), 0)
        return {"ok": res.get("ok"), "checkpoint": checkpoint, "n_ranked": len(rdf)}

    # ------------------------------------------------------------------
    # 步骤8 — 最终排序 0.05/0.15/0.8
    # ------------------------------------------------------------------
    def step8_final_rank(self) -> dict:
        self.log("=== Step8: 最终排序 0.05/0.15/0.8 ===")
        df = pd.read_csv(self.project_root / "glare/step7_glare_ranked_all.csv")
        # 归一化
        def norm(col):
            v = pd.to_numeric(df[col], errors="coerce")
            return (v - v.min()) / (v.max() - v.min() + 1e-9)
        df["model_score_norm"] = norm("model_druglikeness_score") if "model_druglikeness_score" in df else 0.5
        df["affinity_consensus_score_norm"] = norm("affinity_consensus_score") if "affinity_consensus_score" in df else 0.5
        df["glare_score_norm"] = norm("glare_select_prob")
        df["final_score"] = (
            W_MODEL * df["model_score_norm"]
            + W_AFFINITY * df["affinity_consensus_score_norm"]
            + W_GLARE * df["glare_score_norm"]
        )
        df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
        self._save_csv_xlsx(df, "screening/step8_final_ranked_all")
        self._save_csv_xlsx(df.head(100), "screening/step8_final_top100")
        self._save_csv_xlsx(df.head(50), "screening/step8_final_top50")
        self._save_csv_xlsx(df.head(20), "screening/step8_final_top20")
        self.log(f"权重: model={W_MODEL} affinity={W_AFFINITY} glare={W_GLARE}")
        return {"ok": True, "n": len(df), "weights": {"model": W_MODEL, "affinity": W_AFFINITY, "glare": W_GLARE}}

    # ------------------------------------------------------------------
    # 步骤9 — 相似搜索已移除（保留方法供显式调用时 no-op）
    # ------------------------------------------------------------------
    def step9_similarity(self) -> dict:
        self.log("=== Step9: skipped — similarity search removed ===")
        return {"ok": True, "skipped": True, "reason": "similarity removed"}

    # ------------------------------------------------------------------
    # 步骤10 — 排序集 RL 训练（基于 step8 最终排序，不依赖 step9）
    # ------------------------------------------------------------------
    def step10_rl_train(self) -> dict:
        from . import glare_gnn_adapter
        self.log("=== Step10: 排序集 RL 训练 ===")
        known = pd.read_excel(KNOWN_439_XLSX)
        cpd = known.iloc[:, 0].astype(str)
        patent = known[cpd.str.startswith("PAT")]
        selfs = known[~cpd.str.startswith("PAT")]

        final_candidates = [
            self.project_root / "screening/step8_final_top20.csv",
            self.project_root / "screening/step8_final_top50.csv",
            self.project_root / "screening/step8_final_top100.csv",
            self.project_root / "screening/step8_final_ranked_all.csv",
        ]
        final_path = next((p for p in final_candidates if p.is_file()), None)
        if final_path is None:
            raise FileNotFoundError("step8 final ranked CSV not found; run step8 first")
        final = pd.read_csv(final_path)
        # 用全量排序定阈值（若只有 top-N 文件则用其自身分位数）
        all_path = self.project_root / "screening/step8_final_ranked_all.csv"
        score_ref = pd.read_csv(all_path) if all_path.is_file() else final
        top20_pct_threshold = score_ref["final_score"].quantile(0.8)

        rows = []
        # 自合成：真实 pDC50, weight=1.5, label_source=wetlab
        for _, r in selfs.iterrows():
            pdc = float(r["pDC50"])
            rows.append({
                "canonical_smiles": rdkit_utils.standardize(str(r.iloc[1]))["canonical_smiles"],
                "label": 1 if pdc >= 7.0 else 0, "pdc50_raw": pdc, "weight": 1.5,
                "label_source": "wetlab", "source": "self_synth",
            })
        # 专利：真实 pDC50, weight=1.0
        for _, r in patent.iterrows():
            pdc = float(r["pDC50"])
            rows.append({
                "canonical_smiles": rdkit_utils.standardize(str(r.iloc[1]))["canonical_smiles"],
                "label": 1 if pdc >= 7.0 else 0, "pdc50_raw": pdc, "weight": 1.0,
                "label_source": "patent", "source": "patent",
            })
        # step8 最终排序分子（top-N）：pseudo_final_rank, weight=0.3
        smiles_col = "generated_smiles" if "generated_smiles" in final.columns else None
        if smiles_col is None:
            for c in final.columns:
                if "smiles" in c.lower():
                    smiles_col = c
                    break
        if smiles_col is None:
            raise ValueError("No SMILES column in step8 final ranked CSV")
        top_n = min(20, len(final))
        for _, r in final.head(top_n).iterrows():
            canon = rdkit_utils.standardize(str(r[smiles_col]))["canonical_smiles"]
            if not canon:
                continue
            fs = float(r["final_score"]) if "final_score" in final.columns and pd.notna(r.get("final_score")) else 0.0
            rows.append({
                "canonical_smiles": canon,
                "label": 1 if fs >= top20_pct_threshold else 0,
                "pdc50_raw": None,
                "pseudo_reward": fs,
                "weight": 0.3,
                "label_source": "pseudo_final_rank",
                "source": "generated",
            })
        ds = pd.DataFrame(rows)
        self._save_csv_xlsx(ds, "glare/round1_rl_dataset")

        smiles = ds["canonical_smiles"].tolist()
        labels = ds["label"].astype(int).tolist()
        weights = ds["weight"].astype(float).tolist()
        ckpt = str(self.project_root / "glare" / "round1_rl_checkpoint.pt")
        prev = str(self.project_root / "glare" / "pretrain_round_4_checkpoint.pt")
        _ens = int(os.environ.get("VAV1_GLARE_ENSEMBLE", "3"))
        _ep = int(os.environ.get("VAV1_GLARE_EPOCHS", "50"))
        res = glare_gnn_adapter.train(ckpt, smiles, labels, weights, prev_checkpoint=prev, ensemble_size=_ens, epochs=_ep)
        self._save_csv_xlsx(pd.DataFrame([{"ok": res.get("ok"), "loss": res.get("final_loss"), "n": len(ds)}]), "glare/round1_rl_training_log")
        # 兼容旧路径名（step11 可回退读取）
        legacy_ckpt = self.project_root / "glare" / "round1_similarity_rl_checkpoint.pt"
        try:
            import shutil
            if Path(ckpt).is_file():
                shutil.copy2(ckpt, legacy_ckpt)
        except Exception:
            pass
        return {"ok": res.get("ok"), "checkpoint": ckpt, "n": len(ds), "rank_source": str(final_path)}

    # ------------------------------------------------------------------
    # 步骤11 — 第二轮生成+筛选+验证
    # ------------------------------------------------------------------
    def step11_round2(self) -> dict:
        self.log("=== Step11: 第二轮生成+筛选+验证 ===")
        r2_ckpt_candidates = [
            self.project_root / "glare" / "round1_rl_checkpoint.pt",
            self.project_root / "glare" / "round1_similarity_rl_checkpoint.pt",
        ]
        r2_ckpt = next((str(p) for p in r2_ckpt_candidates if p.is_file()), str(r2_ckpt_candidates[0]))
        self.log(f"round2 GLARE 用 {r2_ckpt}；权重 0.05/0.15/0.8 不变")
        # 核心路径：round1 RL ckpt + step8 最终排序集（不再依赖 step9 相似数据集）
        rank_candidates = [
            self.project_root / "screening/step8_final_top20.csv",
            self.project_root / "screening/step8_final_top50.csv",
            self.project_root / "screening/step8_final_ranked_all.csv",
        ]
        r1_path = next((p for p in rank_candidates if p.is_file()), None)
        r1 = pd.read_csv(r1_path) if r1_path else pd.DataFrame()
        verdict = "FAIL"
        reasons = ["round2 全流程需 GPU 实跑后才能验收；本次测试模式未执行第二轮生成"]
        report = {"verdict": verdict, "reasons": reasons, "r1_n": len(r1), "rank_source": str(r1_path) if r1_path else None, "ckpt": r2_ckpt}
        (self.project_root / "reports" / "round2_rl_validation_report.md").write_text(
            f"# Round2 RL 验证报告\n\n判定: {verdict}\n\n原因:\n- " + "\n- ".join(reasons) + "\n"
        )
        return report

    # ------------------------------------------------------------------
    # 最终报告
    # ------------------------------------------------------------------
    def write_final_report(self) -> str:
        self.log("=== 写最终报告 ===")
        lines = [FINAL_REPORT_FIRST_LINE, ""]
        lines.append("# RL Pipeline 执行报告")
        lines.append(f"\n模式: {self.mode} | pocket_type: {self.pocket_type} | 生成时间: {_now()}\n")
        lines.append("## 数据概况")
        lines.append("- 先验 / known 活性集来自 DataSet-GNN-SMILES-pDC50.xlsx")
        lines.append("## 漏斗")
        for step in sorted(self.funnel):
            f = self.funnel[step]
            lines.append(f"- step{step}: total={f['total']} retained={f['retained']} rejected={f['rejected']}")
        lines.append("\n## 最终排序权重")
        lines.append(f"- model_score: {W_MODEL} / affinity_consensus: {W_AFFINITY} / glare: {W_GLARE}")
        report_path = self.project_root / "reports" / "final_project_plan_execution_report.md"
        report_path.write_text("\n".join(lines))
        return str(report_path)

    # ------------------------------------------------------------------
    # 全流程（默认跳过 step9 相似搜索）
    # ------------------------------------------------------------------
    def run_all(self, steps: Optional[list[int]] = None) -> dict:
        all_steps = steps or [1, 2, 3, 4, 5, 6, 7, 8, 10, 11]
        results = {}
        step_map = {
            1: self.step1_pretrain, 2: self.step2_generate, 3: self.step3_validity_admet,
            4: self.step4_druglikeness, 5: self.step5_affinity, 6: self.step6_dedup,
            7: self.step7_glare_rank, 8: self.step8_final_rank, 9: self.step9_similarity,
            10: self.step10_rl_train, 11: self.step11_round2,
        }
        for s in all_steps:
            self.status["current_step"] = s
            try:
                results[s] = step_map[s]()
                self.status["steps_done"].append(s)
            except Exception as e:
                self.log(f"step{s} 异常: {e}")
                results[s] = {"ok": False, "error": str(e)}
                import traceback
                self.log(traceback.format_exc())
                break
        self.write_final_report()
        self.status["finished_at"] = _now()
        return results
