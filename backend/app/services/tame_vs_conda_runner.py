"""TAME-VS 2.0 本地 conda 运行器。

对应官方仓库 ``bymgood/TAME-VS-2.0``（本地 ``tools/Target-driven-ML-enabled-VS``），
通过 conda 环境 ``TAME_VS2``（Python 3.9 + PyTorch 2.4.1 cu118 + torch_geometric）
直接运行 7 阶段流水线脚本，不再依赖 Docker/WSL。

七阶段（见 ``Starting_point_1.sh``）：
1. Target_expansion          —— 靶点扩展（uniprot ID → 同源靶点列表）
2. Compound_retrieving       —— 化合物检索（查 ChEMBL SQLite，actives/inactives）
3. Vectorization             —— 分子指纹 + GNN 图向量化
4. ML/GNN_modeling_training  —— 训练 MLP/RF 与 GNN 模型
5. Virtural_screening        —— 虚拟筛选（50K/4M 等库）
6. Post_VS_analysis          —— 筛选后分析
7. Data_processing           —— 数据处理 + 药效团/t-SNE

设计要点（见 CLAUDE.md）：
- 模型层 = 纯 IO 边界：runner 只组参数 → 调 conda → 收输出，不掺流程逻辑。
- ChEMBL SQLite 路径由配置传入（``chembl_db``），默认数据盘 ``/data/ye/tame-vs-data/chembl/chembl_35.db``。
- 与 ``tame_vs_docker.py`` 方法签名对齐，route 层按 ``runtime`` 选择。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.config import TameVSSettings
from app.services.tool_runner_base import CondaToolRunner

logger = logging.getLogger(__name__)

# 各阶段脚本相对 repo 根目录的路径
_STAGE_SCRIPTS = {
    "target_expansion_1": "1_Target_expansion/Target_expansion.py",
    "target_expansion_2": "1_Target_expansion/Target_expansion2.py",
    "compound_retrieving": "2_Compound_retrieving/Compound_retrieving.py",
    "vectorization": "3_Vectorization/Vectorization.py",
    "gnn_data_split": "3_Vectorization/GNN_data_split.py",
    "gnn_vectorization": "3_Vectorization/GNN_Vectorization.py",
    "ml_training": "4_ML_modeling_training/ML_model_training.py",
    "gnn_training": "4_GNN_modeling_training/GNN_modeling_training.py",
    "virtual_screening": "5_Virtural_screening/Virtual_screening.py",
    "gnn_virtual_screening": "5_Virtural_screening/GNN_Virtual_screening.py",
    "library_preparation": "5_Virtural_screening/Library_preparation.py",
    "gnn_data_preparation": "5_Virtural_screening/GNN_data_preparation.py",
    "post_vs_analysis": "6_Post_VS_analysis/Post_VS_analysis.py",
    "data_processing": "7_Data_processing/Data_processing.py",
}

# Enamine 等库选项（对应 Starting_point_1.sh 的 database_choice）
LIBRARIES = {
    "50K": "Enamine_diversity_50K",
    "4M": "Enamine_Screening_Collection_4M",
    "drugbank": "Drugbank_screening_library",
    "fragment": "Enamine_Fragment_Collection",
    "covalent": "Enamine_Covalent_Compounds",
    "macrocycles": "Enamine_Macrocycles_Collection",
}


class TameVSCondaRunner(CondaToolRunner):
    """TAME-VS 本地 conda 调用。"""

    def __init__(self, settings: TameVSSettings, project_root: Path):
        super().__init__(settings.conda_env, settings.repo_path)
        self.settings = settings
        self.project_root = Path(project_root)

        # 解析相对路径
        repo = Path(settings.repo_path)
        if not repo.is_absolute():
            repo = (self.project_root / repo).resolve()
        self.root = repo

        out = Path(settings.output_dir)
        self.output_dir = out if out.is_absolute() else (self.project_root / out).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # ChEMBL SQLite 路径（配置项，默认数据盘）
        self.chembl_db = settings.chembl_db

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        base = self.env_status()
        base.update(
            {
                "runtime": "conda",
                "repo_path": str(self.root),
                "repo_exists": self.root.is_dir(),
                "chembl_db": self.chembl_db,
                "chembl_db_exists": Path(self.chembl_db).is_file(),
                "output_dir": str(self.output_dir),
                "stages_present": {
                    name: (self.root / script).is_file()
                    for name, script in _STAGE_SCRIPTS.items()
                },
            }
        )
        return base

    # ---------------------------------------------------- 容器概念的 conda 等价物
    def build_image(self) -> dict[str, Any]:
        """conda 模式无需构建镜像；返回环境就绪状态。"""
        st = self.status()
        return {
            "returncode": 0 if (st["conda_env_exists"] and st["repo_exists"]) else 1,
            "stdout": "",
            "stderr": "" if st["conda_env_exists"] else f"conda 环境 {self.conda_env} 不存在",
            "message": "conda 模式无需构建镜像，环境已就绪" if st["conda_env_exists"] else "环境未就绪",
        }

    def start_service(self) -> dict[str, Any]:
        """conda 模式无需启动服务容器。"""
        return {"returncode": 0, "stdout": "conda 模式按需直接运行脚本，无需常驻服务", "stderr": ""}

    def stop_service(self) -> dict[str, Any]:
        return {"returncode": 0, "stdout": "conda 模式无服务可停", "stderr": ""}

    def restart_service(self) -> dict[str, Any]:
        return self.stop_service()

    # -------------------------------------------------------------- 内部执行
    def _run_stage(self, stage: str, args: list[str], *, timeout: int = 3600) -> dict[str, Any]:
        script = _STAGE_SCRIPTS.get(stage)
        if not script:
            return {"ok": False, "returncode": -1, "stdout": "", "stderr": f"未知阶段: {stage}"}
        if not (self.root / script).is_file():
            return {"ok": False, "returncode": -1, "stdout": "", "stderr": f"脚本不存在: {script}"}
        # 工作目录设为脚本所在目录（脚本间用相对路径互引）
        work_dir = (self.root / script).parent
        return self._run(["python", Path(script).name, *args], cwd=work_dir, timeout=timeout)

    # -------------------------------------------------- Module 5: 库准备
    def run_library_preparation(
        self,
        input_csv: str,
        output_name: str,
        smiles_col: int = 1,
        compound_id_col: int = 2,
    ) -> dict[str, Any]:
        """分子指纹准备：CSV → morgan 1024 FP CSV（Module 5 的 Library_preparation.py）。"""
        args = [
            "-i", input_csv,
            "-s", str(smiles_col),
            "-c", str(compound_id_col),
            "-f", output_name,
        ]
        return self._run_stage("library_preparation", args, timeout=1800)

    # -------------------------------------------------- Module 5: GNN 图准备
    def run_gnn_data_preparation(
        self,
        input_csv: str,
        smiles_col: int = 1,
        compound_id_col: int = 2,
        output_name: Optional[str] = None,
    ) -> dict[str, Any]:
        args = ["-i", input_csv, "-s", str(smiles_col), "-c", str(compound_id_col)]
        if output_name:
            args += ["-f", output_name]
        return self._run_stage("gnn_data_preparation", args, timeout=1800)

    # -------------------------------------------------- Module 1-7: 全流程
    def run_full_screen(
        self,
        *,
        uniprot_id: str,
        library: str = "50K",
        top_percent: float = 1.0,
        identity_threshold: float = 0.4,
        work_dir: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> dict[str, Any]:
        """从 uniprot ID 跑完整 7 阶段流水线（对应 Starting_point_1.sh）。

        长任务，应放 Celery 异步执行。此处提供同步实现，供 worker 调用。
        """
        lib_name = LIBRARIES.get(library, library)
        run_dir = Path(work_dir) if work_dir else (self.output_dir / f"{uniprot_id}_{library}")
        run_dir.mkdir(parents=True, exist_ok=True)

        stages_log: list[dict[str, Any]] = []

        def _log(stage: str, res: dict[str, Any]) -> None:
            stages_log.append({"stage": stage, "ok": res.get("ok"), "stderr_tail": (res.get("stderr") or "")[-300:]})

        # Module 1: 靶点扩展
        r = self._run_stage(
            "target_expansion_1",
            ["-i", uniprot_id, "-f", uniprot_id, "-p", str(identity_threshold)],
            timeout=1800,
        )
        _log("target_expansion_1", r)
        if not r["ok"]:
            return {"ok": False, "stage": "target_expansion_1", "stages": stages_log, "run_dir": str(run_dir)}

        r2 = self._run_stage("target_expansion_2", ["-i", uniprot_id, "-f", uniprot_id], timeout=1800)
        _log("target_expansion_2", r2)

        # Module 2: 化合物检索（需 ChEMBL db）
        if not Path(self.chembl_db).is_file():
            return {"ok": False, "stage": "compound_retrieving", "error": f"ChEMBL db 不存在: {self.chembl_db}", "stages": stages_log}
        r = self._run_stage(
            "compound_retrieving",
            ["-i", f"{uniprot_id}.csv", "-f", f"{uniprot_id}_compounds_collection", "-d", self.chembl_db],
            timeout=3600,
        )
        _log("compound_retrieving", r)

        # 注：Module 3-7 涉及大量文件名通配与 cp，完整编排较复杂；
        # 此处先实现到 Module 2，后续阶段按需补全（见 TODO）。
        return {
            "ok": r.get("ok", False),
            "stage": "compound_retrieving",
            "stages": stages_log,
            "run_dir": str(run_dir),
            "library": lib_name,
            "top_percent": top_percent,
            "note": "Module 3-7 编排待补全",
        }

    def run_full_50k_screen(
        self,
        top_percent: float = 1.0,
        target_pdb_id: Optional[str] = None,
        db: Optional[Any] = None,
    ) -> dict[str, Any]:
        """对齐 docker runner 的 50K 全库筛选接口。"""
        if not target_pdb_id:
            return {"ok": False, "error": "需要 target_pdb_id（uniprot ID）"}
        return self.run_full_screen(
            uniprot_id=target_pdb_id, library="50K", top_percent=top_percent, db=db
        )

    # -------------------------------------------------- 结果入库
    def ingest_result_csv(
        self,
        db: Optional[Any],
        result_csv: str,
        sdf_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """将 TAME-VS 筛选结果 CSV 转 SDF 并同步进分子库。

        复用既有 sdf_sync 流程（与 docker runner 行为一致）。
        """
        from app.services.sdf_sync import sync_sdf_library  # 延迟导入，避免循环

        if db is None:
            return {"ok": False, "error": "缺少数据库 session"}

        try:
            from rdkit import Chem
        except ImportError:
            return {"ok": False, "error": "rdkit 未安装（backend 环境需 rdkit）"}

        # CSV → SDF
        import csv as _csv

        csv_path = Path(result_csv)
        if not csv_path.is_file():
            return {"ok": False, "error": f"结果 CSV 不存在: {result_csv}"}

        sdf_path = csv_path.with_suffix(".sdf") if sdf_name is None else csv_path.parent / f"{sdf_name}.sdf"
        w = Chem.SDWriter(str(sdf_path))
        count = 0
        with csv_path.open(encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                smiles = row.get("SMILES") or row.get("smiles") or row.get("canonical_smiles")
                if not smiles:
                    continue
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    continue
                for k, v in row.items():
                    if k and v is not None:
                        mol.SetProp(k, str(v))
                w.write(mol)
                count += 1
        w.close()

        sync_sdf_library(db, str(sdf_path))
        return {"ok": True, "sdf_path": str(sdf_path), "molecule_count": count}
