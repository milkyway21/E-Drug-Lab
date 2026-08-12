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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from . import rdkit_utils, admet_rules
from .target_profile import TargetProfile, load_or_infer_profile
from .target_generation import run_target_generator

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
    return datetime.now(timezone.utc).isoformat()


def _read_table(path: Path | str) -> pd.DataFrame:
    """Read the small tabular inputs used by the orchestrator."""
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"input table not found: {source}")
    if source.suffix.lower() in {".csv", ".tsv"}:
        return pd.read_csv(source, sep="\t" if source.suffix.lower() == ".tsv" else ",")
    return pd.read_excel(source)


class TargetRLOrchestrator:
    def __init__(
        self,
        project_root: str = PROJECT_ROOT_DEFAULT,
        mode: str = "test",          # test | full
        num_mols: int = 1000,
        reuse_sdf_dir: Optional[str] = None,
        schrodinger_install: str | None = None,
        ph: float | None = None,
        log_to_stdout: bool = True,
        target_profile: TargetProfile | str | dict[str, Any] | None = None,
        target_id: str = "vav1",
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
        self.target_profile = load_or_infer_profile(
            target_profile,
            target_id=target_id if target_profile is None else None,
        )
        profile_path = target_profile if isinstance(target_profile, str) else None
        if self.target_profile is None:
            # Backward-compatible VAV1 default; all new target runs should
            # provide a generated profile.
            self.target_profile = TargetProfile(
                target_id=target_id,
                receptor_pdb=Path(VAV1_POCKET_PDB) if target_id == "vav1" else None,
            )
        self.target_id = self.target_profile.target_id
        self.activity_table = self.target_profile.activity_table or (
            Path(KNOWN_439_XLSX) if self.target_id == "vav1" else None
        )
        self.generation_source = self.target_profile.generation_source or (
            Path(ROUND200_MERGED) if self.target_id == "vav1" else None
        )
        self.reference_library = self.target_profile.reference_library or (
            Path(LARGE_LIBRARY_SMI) if self.target_id == "vav1" else None
        )
        self.prepared_receptor = self.target_profile.prepared_receptor
        self.grid_file = self.target_profile.grid_file
        self.pocket_file = self.target_profile.receptor_pdb or (
            Path(VAV1_POCKET_PDB) if self.target_id == "vav1" else None
        )
        if profile_path:
            self.target_profile_path = str(Path(profile_path).expanduser().resolve())
        elif target_profile is not None:
            path = self.project_root / "target" / f"{self.target_id}.json"
            self.target_profile_path = str(self.target_profile.save(path))
        else:
            self.target_profile_path = None

        self.ensure_dirs()
        self.funnel: dict[int, dict[str, int]] = {}
        self.status: dict[str, Any] = {"current_step": None, "mode": mode, "started_at": _now(), "steps_done": []}
        # 口袋由当前研究靶标决定（内部仍可复用项目 pocket PDB）
        self.pocket_type = f"{self.target_id}_pocket"

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

    def _load_activity_records(self) -> list[dict[str, Any]]:
        """Load target activity data through a small, explicit column contract."""
        if self.activity_table is None:
            raise ValueError(
                f"target '{self.target_id}' requires profile.activity_table for pretraining"
            )
        frame = _read_table(self.activity_table)
        frame.columns = [str(column).strip() for column in frame.columns]
        lower = {str(column).lower(): str(column) for column in frame.columns}

        def find(*names: str, contains: str | None = None) -> str | None:
            for name in names:
                if name in lower:
                    return lower[name]
            if contains:
                return next((column for column in frame.columns if contains in column.lower()), None)
            return None

        id_column = find("molecule_id", "mol_id", "id", "compound_id") or str(frame.columns[0])
        smiles_column = find("smiles", "canonical_smiles", contains="smiles")
        label_column = find(
            "label_active", "activity_label", "label", "active", "is_active"
        )
        configured_metric = self.target_profile.activity_metric
        value_names = [
            name.lower()
            for name in (
                configured_metric,
                "pdc50",
                "pic50",
                "ic50",
                "kd",
                "ki",
                "activity",
                "affinity",
                "activity_value",
            )
            if name
        ]
        value_column = find(*value_names)
        if smiles_column is None:
            raise ValueError(f"activity table for target '{self.target_id}' requires a SMILES column")
        if label_column is None and value_column is None:
            raise ValueError(
                f"activity table for target '{self.target_id}' requires label_active/label "
                "or an activity value column"
            )

        thresholds = (
            self.target_profile.active_threshold,
            self.target_profile.weak_threshold,
            self.target_profile.strong_threshold,
        )
        thresholds_configured = all(value is not None for value in thresholds)
        if label_column is None and any(value is None for value in thresholds):
            raise ValueError(
                "activity-value inputs require active_threshold, weak_threshold and "
                "strong_threshold in the target profile"
            )
        direction = self.target_profile.activity_direction
        if label_column is None and self.target_id != "vav1" and not self.target_profile.activity_metric:
            raise ValueError(
                f"target '{self.target_id}' activity values require profile.activity_metric"
            )
        active_threshold, weak_threshold, strong_threshold = thresholds
        active_threshold = 7.0 if active_threshold is None else float(active_threshold)
        weak_threshold = 6.0 if weak_threshold is None else float(weak_threshold)
        strong_threshold = 8.0 if strong_threshold is None else float(strong_threshold)
        if direction == "greater_is_active":
            valid_threshold_order = weak_threshold < active_threshold <= strong_threshold
        else:
            valid_threshold_order = strong_threshold <= active_threshold < weak_threshold
        if label_column is None and not valid_threshold_order:
            raise ValueError(
                f"activity thresholds are inconsistent with {direction}: "
                f"weak={weak_threshold}, active={active_threshold}, strong={strong_threshold}"
            )

        records: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            raw_smiles = str(row.get(smiles_column, "") or "").strip()
            if not raw_smiles or raw_smiles.lower() == "nan":
                continue
            raw_id = row.get(id_column, "")
            molecule_id = "" if raw_id is None or pd.isna(raw_id) else str(raw_id).strip()
            if self.target_id == "vav1" and label_column is None and not molecule_id.startswith("PAT"):
                continue
            raw_value = row.get(value_column) if value_column else None
            try:
                activity_value = float(raw_value) if raw_value is not None and not pd.isna(raw_value) else None
            except (TypeError, ValueError):
                activity_value = None

            label: int | None = None
            if label_column is not None:
                raw_label = row.get(label_column)
                try:
                    parsed = float(raw_label)
                    label = int(parsed) if parsed in (-1, 0, 1) else None
                except (TypeError, ValueError):
                    label_text = str(raw_label).strip().lower()
                    label = 1 if label_text in {"active", "true", "yes", "positive"} else (
                        0 if label_text in {"inactive", "false", "no", "negative"} else None
                    )
            elif activity_value is not None:
                if direction == "greater_is_active":
                    label = 1 if activity_value >= active_threshold else (
                        0 if activity_value < weak_threshold else -1
                    )
                else:
                    label = 1 if activity_value <= active_threshold else (
                        0 if activity_value > weak_threshold else -1
                    )
            if label not in (-1, 0, 1):
                continue
            if activity_value is not None and (label_column is None or thresholds_configured):
                if direction == "greater_is_active":
                    strong = int(activity_value >= strong_threshold)
                    activity_norm = (
                        activity_value - weak_threshold
                    ) / max(strong_threshold - weak_threshold, 1e-8)
                else:
                    strong = int(activity_value <= strong_threshold)
                    activity_norm = (
                        weak_threshold - activity_value
                    ) / max(weak_threshold - strong_threshold, 1e-8)
                activity_norm = max(0.0, min(1.0, activity_norm))
            else:
                strong = int(label == 1)
                activity_norm = float(label == 1)
            records.append(
                {
                    "molecule_id": molecule_id,
                    "smiles": raw_smiles,
                    "activity_raw": activity_value,
                    "activity_norm": activity_norm,
                    "activity_metric": self.target_profile.activity_metric,
                    "activity_direction": direction,
                    "label_active": label,
                    "strong_active": strong,
                    "sample_weight": 1.2 if strong else (0.5 if label == -1 else 1.0),
                    "source": "activity",
                }
            )
        return records

    # ------------------------------------------------------------------
    # 步骤1 — patent 预处理 + 4 轮 GLARE 预训练
    # ------------------------------------------------------------------
    def step1_pretrain(self) -> dict:
        from . import glare_gnn_adapter
        self.log("=== Step1: patent 预处理 + 4 轮 GLARE 预训练 ===")
        records = []
        invalid = []
        for row in self._load_activity_records():
            s = rdkit_utils.standardize(str(row["smiles"]))
            if not s["mol_valid"]:
                invalid.append({"molecule_id": row["molecule_id"], "smiles": row["smiles"], "reason": "invalid"})
                continue
            rec = {
                "molecule_id": row["molecule_id"],
                "smiles": str(row["smiles"]),
                "canonical_smiles": s["canonical_smiles"],
                "neutralized_smiles": s["neutralized_smiles"],
                "inchikey": s["inchikey"],
                "pdc50_raw": row["activity_raw"],
                "pdc50_norm": row["activity_norm"],
                "label_active": row["label_active"],
                "strong_active": row["strong_active"],
                "sample_weight": row["sample_weight"],
                "source": row["source"],
            }
            records.append(rec)

        valid = [r for r in records if r["label_active"] in (0, 1)]
        weak = [r for r in records if r["label_active"] == -1]
        self.log(f"patent 有效={len(records)} 强分类={len(valid)} weak={len(weak)} 无效={len(invalid)}")
        if len(records) < 10:
            return {"ok": False, "error": f"有效分子 {len(records)} < 10，数据不足"}

        prefix = "patent" if self.target_id == "vav1" else self.target_id
        self._save_csv_xlsx(pd.DataFrame(records), f"data/processed/{prefix}_activity_cleaned")
        self._save_csv_xlsx(pd.DataFrame(invalid), f"data/processed/{prefix}_invalid_records")

        # 四分子组，最多四轮；小型新靶点数据集也能完成可验证的首轮训练。
        groups = []
        for gi in range((len(records) + 3) // 4):
            grp = records[gi * 4:(gi + 1) * 4]
            for m in grp:
                m["group_id"] = f"patent_group_{gi + 1:03d}"
            groups.extend(grp)
        self._save_csv_xlsx(pd.DataFrame(groups), f"data/processed/{prefix}_groups")

        # 4 轮预训练（累积 + 续训）
        training_log = []
        ckpt_prev = None
        for rnd in range(1, 5):
            lo = (rnd - 1) * 25 + 1
            hi = rnd * 25
            group_ids = {f"patent_group_{i:03d}" for i in range(lo, hi + 1)}
            round_data = [m for m in groups if m["group_id"] in group_ids]
            # weak_active 低权重纳入（label 取 0，weight 已 0.5）
            train_records = [
                {
                    "smiles": m["neutralized_smiles"],
                    "label": m["label_active"] if m["label_active"] in (0, 1) else 0,
                    "weight": m["sample_weight"],
                    "molecule_id": m["molecule_id"],
                }
                for m in round_data
            ]
            smiles = [m["smiles"] for m in train_records]
            ckpt = str(self.project_root / "glare" / f"pretrain_round_{rnd}_checkpoint.pt")
            self.log(f"pretrain round {rnd}: groups {lo:03d}-{hi:03d}, n={len(smiles)}")
            _ep = int(os.environ.get("GLARE_EPOCHS", os.environ.get("VAV1_GLARE_EPOCHS", "50")))
            _ens = int(os.environ.get("GLARE_ENSEMBLE", os.environ.get("VAV1_GLARE_ENSEMBLE", "3")))
            res = glare_gnn_adapter.train(
                ckpt,
                records=train_records,
                prev_checkpoint=ckpt_prev,
                epochs=_ep,
                ensemble_size=_ens,
                target_profile=self.target_profile_path,
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
        source_path = (
            Path(self.reuse_sdf_dir)
            if self.reuse_sdf_dir and Path(self.reuse_sdf_dir).is_file()
            else self.generation_source
        )
        if self.mode == "test" and source_path is not None and source_path.is_file():
            # 测试模式：复用 target profile 指定的生成池。
            src = _read_table(source_path)
            smi_col = next((c for c in src.columns if "smiles" in str(c).lower()), None)
            if smi_col is None:
                raise ValueError(f"generation source has no SMILES column: {source_path}")
            id_col = next(
                (
                    column for column in src.columns
                    if str(column).strip().lower() in {"molecule_id", "generated_id", "mol_id", "id"}
                ),
                None,
            )
            source_columns = [smi_col] + ([id_col] if id_col else [])
            gen = src[source_columns].rename(columns={smi_col: "generated_smiles"}).head(self.num_mols)
            gen["generation_id"] = [
                f"GEN_{self.target_id}_{i:05d}" for i in range(len(gen))
            ]
            if id_col:
                gen["molecule_id"] = gen[id_col].astype(str)
            else:
                gen["molecule_id"] = gen["generation_id"]
            gen["generation_mode"] = "denovo"
            gen["source_scaffold_id"] = None
            gen["source_fragment_smiles"] = None
            gen["pocket_file"] = str(self.pocket_file) if self.pocket_file else None
            gen["requested_affinity_condition"] = "profile-defined; affinity filtering follows generation"
            gen["mapping_rule"] = "test generation source contract"
            self.log(f"测试模式：复用 profile generation source 的 {len(gen)} 个分子")
        else:
            # full 模式：调 diffgui_runner 拆 60% frag_cond + 40% denovo（实际跑需 GPU）
            return self._step2_generate_full()
        csv_p, _ = self._save_csv_xlsx(gen, "diffgui_generation/generated_10000_raw")
        manifest = {
            "mode": self.mode,
            "target_id": self.target_id,
            "num_mols": len(gen),
            "pocket_type": self.pocket_type,
            "pocket_file": str(self.pocket_file) if self.pocket_file else None,
            "mapping_rule": gen["mapping_rule"].iloc[0] if len(gen) else None,
        }
        (self.project_root / "diffgui_generation" / "generation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        self._record_funnel(2, len(gen), len(gen), 0)
        return {"ok": True, "generated_csv": csv_p, "num_mols": len(gen)}

    def _step2_generate_full(self) -> dict:
        result = run_target_generator(
            self.target_profile,
            output_dir=self.project_root / "diffgui_generation",
            project_root=self.project_root,
            pocket_file=self.pocket_file,
            num_mols=self.num_mols,
        )
        gen = result["frame"]
        gen["requested_affinity_condition"] = "profile-defined; affinity filtering follows generation"
        gen["mapping_rule"] = "target generator profile contract"
        csv_p, _ = self._save_csv_xlsx(gen, "diffgui_generation/generated_10000_raw")
        manifest = {
            "mode": self.mode,
            "target_id": self.target_id,
            "num_mols": len(gen),
            "requested_num_mols": self.num_mols,
            "num_frag": result["num_frag"],
            "num_denovo": result["num_denovo"],
            "pocket_type": self.pocket_type,
            "pocket_file": str(self.pocket_file) if self.pocket_file else None,
            "request_json": result["request_json"],
            "raw_output_csv": result["raw_output_csv"],
            "command": result["command"],
            "mapping_rule": "target generator profile contract",
        }
        (self.project_root / "diffgui_generation" / "generation_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        self.log(
            f"full 模式生成完成: frag_cond={result['num_frag']} "
            f"denovo={result['num_denovo']} output={csv_p}"
        )
        self._record_funnel(2, len(gen), len(gen), 0)
        return {
            "ok": True,
            "generated_csv": csv_p,
            "num_mols": len(gen),
            "num_frag": result["num_frag"],
            "num_denovo": result["num_denovo"],
        }

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
        if self.mode != "test" and not (
            self.pocket_file or self.prepared_receptor or self.grid_file
        ):
            raise ValueError(
                f"target '{self.target_id}' requires receptor_pdb, prepared_receptor or "
                "grid_file for full docking"
            )
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
                    receptor_pdb=str(self.pocket_file) if self.pocket_file else None,
                    output_dir=str(self.project_root),
                    install_path=self.schrodinger_install,
                    ph=self.ph,
                    box_center=None,  # 自动从 PDB 质心计算
                    prepared_receptor=str(self.prepared_receptor) if self.prepared_receptor else None,
                    grid_file=str(self.grid_file) if self.grid_file else None,
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
        score_columns = [
            column for column in ("vina_score", "glide_xp_score", "mmgbsa_dg")
            if column in out.columns
        ]
        out["affinity_observed"] = out[score_columns].notna().any(axis=1)
        out.loc[~out["affinity_observed"], "reject_reason"] = (
            out.loc[~out["affinity_observed"], "reject_reason"].fillna("")
            + "; all_affinity_scores_missing"
        ).str.strip("; ")
        # 简化：各模型进前 40%，或放宽底线
        for col in ["vina_score_norm", "glide_xp_score_norm", "mmgbsa_dg_norm"]:
            if col in out.columns:
                threshold = out[col].quantile(0.4) if out[col].notna().sum() > 5 else 0.0
                # norm 越大越好,低于 40% 分位记但仅当三模型都差才剔
                below = out[col] < threshold
                out.loc[below & out[col].notna(), "reject_reason"] = (
                    out.loc[below & out[col].notna(), "reject_reason"].fillna("") + f"; {col}_below_40pct"
                )

        # 低于单模型分位线只留下标记；完全没有任何亲和力观测值才剔除。
        out = out.sort_values("affinity_consensus_score", ascending=False).reset_index(drop=True)

        self._save_csv_xlsx(out, "screening/step5_affinity_orthogonal_all")
        retained = out[out["affinity_observed"]].copy()
        rejected = out[~out["affinity_observed"]].copy()
        self._save_csv_xlsx(retained, "screening/step5_affinity_orthogonal_retained")
        self._save_csv_xlsx(rejected, "screening/step5_affinity_orthogonal_rejected")
        self._record_funnel(5, len(df), len(retained), len(rejected))
        return {"ok": True, "retained": len(retained), "schrodinger_ran": bool(out["schrodinger_ran"].any()),
                "consensus_mode": "0.1/0.3/0.6" if out["schrodinger_ran"].any() else "Vina-only surrogate"}

    # ------------------------------------------------------------------
    # 步骤6 — 去重
    # ------------------------------------------------------------------
    def step6_dedup(self) -> dict:
        self.log(f"=== Step6: 去重 vs reference library + {self.target_id} activity set ===")
        df = pd.read_csv(self.project_root / "screening/step5_affinity_orthogonal_retained.csv")
        # 参考库
        known_records = self._load_activity_records()
        known_smi = [str(record["smiles"]) for record in known_records]
        known_canon = {rdkit_utils.standardize(s)["canonical_smiles"] for s in known_smi if rdkit_utils.standardize(s)["canonical_smiles"]}
        known_ik = {rdkit_utils.standardize(s)["inchikey"] for s in known_smi if rdkit_utils.standardize(s)["inchikey"]}
        known_ik1 = {rdkit_utils.inchikey_first_block(ik) for ik in known_ik if ik}
        # large_library（2.1M，抽样或全量读；先读前 50万）
        large_smi = []
        if self.reference_library and self.reference_library.is_file():
            with open(self.reference_library) as f:
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
        if not Path(checkpoint).is_file():
            raise FileNotFoundError(f"GLARE checkpoint not found for target '{self.target_id}': {checkpoint}")
        query_records = []
        for _, row in df.iterrows():
            smiles = row.get("generated_smiles", row.get("smiles"))
            if smiles is None or pd.isna(smiles):
                continue
            record = {"smiles": str(smiles)}
            for key in ("molecule_id", "generated_id", "compound_id", "mol_id", "id"):
                value = row.get(key)
                if value is not None and not pd.isna(value) and str(value).strip():
                    record["molecule_id"] = str(value).strip()
                    break
            query_records.append(record)
        res = glare_gnn_adapter.query(
            checkpoint,
            records=query_records,
            target_profile=self.target_profile_path,
        )
        ranked = res.get("ranked", [])
        rdf = pd.DataFrame(ranked)
        if not rdf.empty:
            if "molecule_id" in rdf.columns and "molecule_id" in df.columns:
                rdf = rdf.merge(df, on="molecule_id", how="left")
            else:
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
        activity_records = self._load_activity_records()

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
        # Activity labels are target-profile data, never an implicit VAV1 table.
        for record in activity_records:
            canonical = rdkit_utils.standardize(str(record["smiles"]))["canonical_smiles"]
            if not canonical:
                continue
            rows.append({
                "canonical_smiles": canonical,
                "molecule_id": record.get("molecule_id") or canonical,
                "label": 1 if record["label_active"] == 1 else 0,
                "pdc50_raw": record["activity_raw"],
                "weight": record["sample_weight"],
                "label_source": "target_activity",
                "source": "target_activity",
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
                "molecule_id": r.get("molecule_id") or r.get("generation_id") or canon,
                "label": 1 if fs >= top20_pct_threshold else 0,
                "pdc50_raw": None,
                "pseudo_reward": fs,
                "weight": 0.3,
                "label_source": "pseudo_final_rank",
                "source": "generated",
            })
        ds = pd.DataFrame(rows)
        self._save_csv_xlsx(ds, "glare/round1_rl_dataset")

        train_records = [
            {
                "smiles": row["canonical_smiles"],
                "label": int(row["label"]),
                "weight": float(row["weight"]),
                "molecule_id": str(row["molecule_id"]),
            }
            for _, row in ds.iterrows()
        ]
        ckpt = str(self.project_root / "glare" / "round1_rl_checkpoint.pt")
        pretrain_candidates = sorted((self.project_root / "glare").glob("pretrain_round_*_checkpoint.pt"))
        prev = str(pretrain_candidates[-1]) if pretrain_candidates else None
        _ens = int(os.environ.get("GLARE_ENSEMBLE", os.environ.get("VAV1_GLARE_ENSEMBLE", "3")))
        _ep = int(os.environ.get("GLARE_EPOCHS", os.environ.get("VAV1_GLARE_EPOCHS", "50")))
        res = glare_gnn_adapter.train(
            ckpt,
            records=train_records,
            prev_checkpoint=prev,
            ensemble_size=_ens,
            epochs=_ep,
            target_profile=self.target_profile_path,
        )
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
        lines.append(
            f"\n模式: {self.mode} | target_id: {self.target_id} | "
            f"pocket_type: {self.pocket_type} | 生成时间: {_now()}\n"
        )
        lines.append("## 数据概况")
        lines.append(f"- target activity table: {self.activity_table}")
        lines.append(f"- Glide table: {self.target_profile.glide_table}")
        lines.append(f"- MD features: {self.target_profile.md_dir or 'disabled'}")
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


# Public compatibility name retained for existing VAV1 callers.
VAV1RLOrchestrator = TargetRLOrchestrator
