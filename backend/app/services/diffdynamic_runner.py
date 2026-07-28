"""DiffDynamic 本地 conda 运行器。

包装 ``/data/ye/DiffDynamic`` 核心入口：

- ``batch_sampleandeval_parallel.py`` —— dynamic / 自定义口袋批量采样
- ``run_prudent_generations.py`` —— Prudent 累积式生成
- ``evaluate_pocket_quality.py`` —— 8 维口袋质量评估
- ``extract_pt_to_sdf_excel.py`` —— .pt → SDF + Excel

设计要点（见 CLAUDE.md）：
- **采样配置 sampling.yml 是唯一真相源**。本 runner 不改原文件，而是以它为模板，
  为每次运行生成一份副本（覆盖 mode / batch_size 等运行期参数），再传给入口脚本。
- 模型层 = 纯 IO 边界：runner 只负责"组参数 → 调 conda → 收输出"，不掺流程逻辑。

测试规则（CLAUDE.md）：生成 batch_size=5、评估 max_samples=5、vina 超时 20s、自动链式。
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config import DiffDynamicSettings
from app.services.tool_runner_base import CondaToolRunner

logger = logging.getLogger(__name__)

_DYNAMIC_SCRIPT = "batch_sampleandeval_parallel.py"
_PRUDENT_SCRIPT = "run_prudent_generations.py"
_EVAL_SCRIPT = "evaluate_pocket_quality.py"
_EVAL_RECONSTRUCT_SCRIPT = "evaluate_pt_with_correct_reconstruct.py"
_EXTRACT_SCRIPT = "extract_pt_to_sdf_excel.py"


class DiffDynamicRunner(CondaToolRunner):
    """DiffDynamic 本地 conda 调用。"""

    def __init__(self, settings: DiffDynamicSettings):
        super().__init__(settings.conda_env, settings.root)
        self.settings = settings
        self.sample_config = Path(settings.sampling_config)
        if not self.sample_config.is_absolute():
            self.sample_config = self.root / settings.sampling_config
        self.protein_root = Path(settings.protein_root)
        if not self.protein_root.is_absolute():
            self.protein_root = self.root / settings.protein_root

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        base = self.env_status()
        base.update(
            {
                "runtime": self.settings.runtime,
                "sampling_config": str(self.sample_config),
                "sampling_config_exists": self.sample_config.is_file(),
                "protein_root": str(self.protein_root),
                "protein_root_exists": self.protein_root.is_dir(),
                "scripts": {
                    "dynamic": (self.root / _DYNAMIC_SCRIPT).is_file(),
                    "prudent": (self.root / _PRUDENT_SCRIPT).is_file(),
                    "evaluate": (self.root / _EVAL_SCRIPT).is_file(),
                    "extract": (self.root / _EXTRACT_SCRIPT).is_file(),
                    "reconstruct": (self.root / _EVAL_RECONSTRUCT_SCRIPT).is_file(),
                },
                "device": self.settings.default_device,
            }
        )
        return base

    # ------------------------------------------------------- 采样配置副本生成
    def _render_run_config(
        self,
        *,
        mode: str,
        batch_size: int,
        output_dir: Path,
        extra_overrides: Optional[dict[str, Any]] = None,
    ) -> Path:
        """以 sampling.yml 为模板生成运行期配置副本。"""
        with self.sample_config.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        sample = cfg.setdefault("sample", {})
        sample["mode"] = mode
        if mode == "dynamic":
            dyn = sample.setdefault("dynamic", {})
            large = dyn.setdefault("large_step", {})
            large["batch_size"] = batch_size

        if extra_overrides:
            for path, value in extra_overrides.items():
                node = cfg
                keys = path.split(".")
                for k in keys[:-1]:
                    node = node.setdefault(k, {})
                node[keys[-1]] = value

        output_dir.mkdir(parents=True, exist_ok=True)
        run_cfg = output_dir / "sampling_run.yml"
        with run_cfg.open("w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
        return run_cfg

    def _run_output_dir(self, run_id: str) -> Path:
        base = Path(self.settings.outputs_dir)
        if not base.is_absolute():
            base = self.root / base
        out = base / run_id
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _gpu_arg(self) -> str:
        dev = self.settings.default_device or "cuda:0"
        if ":" in dev:
            return dev.split(":")[-1]
        return "0"

    @staticmethod
    def find_pt_files(directory: str | Path, *, extra_roots: Optional[list[Path]] = None) -> list[Path]:
        root = Path(directory)
        candidates: list[Path] = []
        if root.is_dir():
            candidates.extend(sorted(root.rglob("result_*.pt")))
            if not candidates:
                candidates.extend(sorted(root.rglob("*.pt")))
        for base in extra_roots or []:
            if base.is_dir():
                pts = sorted(base.glob("result_*.pt"))
                if not pts:
                    pts = sorted(base.glob("*.pt"))
                candidates.extend(pts)
        # 去重，按修改时间倒序（最新优先）
        seen: set[str] = set()
        unique: list[Path] = []
        for p in sorted(candidates, key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
            key = str(p.resolve())
            if key not in seen and p.is_file():
                seen.add(key)
                unique.append(p)
        return unique

    def _discover_pt(self, output_dir: Path, stdout: str = "") -> Optional[str]:
        """在输出目录、DiffDynamic 默认 outputs/pt 及 stdout 日志中定位 .pt。"""
        import re

        for pattern in (
            r"(/[^\s']+result[_\w]*\.pt)",
            r"outputs/pt/(result[^\s']+\.pt)",
        ):
            for match in re.findall(pattern, stdout or ""):
                p = Path(match)
                if not p.is_absolute():
                    p = self.root / p
                if p.is_file():
                    return str(p.resolve())

        extra = [
            self.root / "outputs" / "pt",
            self.root / "outputs",
        ]
        pts = self.find_pt_files(output_dir, extra_roots=extra)
        return str(pts[0].resolve()) if pts else None

    @staticmethod
    def find_sdf_files(directory: str | Path) -> list[Path]:
        root = Path(directory)
        if not root.is_dir():
            return []
        recon = root / "reconstructed_molecules"
        if recon.is_dir():
            sdfs = sorted(recon.glob("*.sdf"))
            if sdfs:
                return sdfs
        return sorted(root.rglob("*.sdf"))

    @staticmethod
    def merge_sdf_files(sdf_files: list[Path], dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as out:
            for sdf in sdf_files:
                content = sdf.read_text(encoding="utf-8").rstrip()
                if not content:
                    continue
                out.write(content)
                if not content.endswith("$$$$"):
                    out.write("\n$$$$\n")
                else:
                    out.write("\n")
        return dest

    # ------------------------------------------------------------- dynamic 生成
    def run_dynamic(
        self,
        *,
        data_id: int,
        batch_size: int = 5,
        run_id: Optional[str] = None,
        sample_only: bool = True,
        gpus: Optional[str] = None,
    ) -> dict[str, Any]:
        """CrossDocked data_id 上的 dynamic 模式批量采样。"""
        run_id = run_id or f"dynamic_data{data_id}_{int(time.time())}"
        out = self._run_output_dir(run_id)
        run_cfg = self._render_run_config(
            mode="dynamic", batch_size=batch_size, output_dir=out
        )

        args = [
            "python", _DYNAMIC_SCRIPT,
            "--data_ids", str(data_id),
            "--config", str(run_cfg),
            "--output_dir", str(out),
            "--gpus", gpus or self._gpu_arg(),
        ]
        if sample_only:
            args.append("--sample-only")

        result = self._run(args, cwd=self.root, timeout=7200)
        pt_path = self._discover_pt(out, result.get("stdout") or "")
        result.update(
            {
                "run_id": run_id,
                "mode": "dynamic",
                "data_id": data_id,
                "batch_size": batch_size,
                "output_dir": str(out),
                "run_config": str(run_cfg),
                "pt_path": pt_path,
            }
        )
        return result

    # ------------------------------------------------------- 自定义口袋生成
    def run_custom(
        self,
        *,
        protein_path: str,
        ligand_path: Optional[str] = None,
        batch_size: int = 5,
        run_id: Optional[str] = None,
        sample_only: bool = True,
        gpus: Optional[str] = None,
        protein_root: Optional[str] = None,
    ) -> dict[str, Any]:
        """基于自定义蛋白/配体文件的 dynamic 采样。"""
        protein = Path(protein_path)
        if not protein.is_file():
            return {"ok": False, "error": f"Protein file not found: {protein_path}"}

        run_id = run_id or f"custom_{protein.stem}_{int(time.time())}"
        out = self._run_output_dir(run_id)
        run_cfg = self._render_run_config(
            mode="dynamic", batch_size=batch_size, output_dir=out
        )

        args = [
            "python", _DYNAMIC_SCRIPT,
            "--protein_path", str(protein.resolve()),
            "--config", str(run_cfg),
            "--output_dir", str(out),
            "--gpus", gpus or self._gpu_arg(),
            "--protein_root", str(Path(protein_root or self.protein_root).resolve()),
        ]
        if ligand_path:
            ligand = Path(ligand_path)
            if not ligand.is_file():
                return {"ok": False, "error": f"Ligand file not found: {ligand_path}"}
            args.extend(["--ligand_path", str(ligand.resolve())])
        if sample_only:
            args.append("--sample-only")

        result = self._run(args, cwd=self.root, timeout=7200)
        pt_path = self._discover_pt(out, result.get("stdout") or "")
        result.update(
            {
                "run_id": run_id,
                "mode": "custom",
                "protein_path": str(protein.resolve()),
                "ligand_path": str(Path(ligand_path).resolve()) if ligand_path else None,
                "batch_size": batch_size,
                "output_dir": str(out),
                "run_config": str(run_cfg),
                "pt_path": pt_path,
            }
        )
        return result

    def run_generate(
        self,
        *,
        mode: str = "dynamic",
        data_id: Optional[int] = None,
        protein_path: Optional[str] = None,
        ligand_path: Optional[str] = None,
        batch_size: int = 5,
        run_id: Optional[str] = None,
        sample_only: bool = True,
        gpus: Optional[str] = None,
    ) -> dict[str, Any]:
        """统一生成入口：优先自定义口袋，否则走 data_id / prudent。"""
        if protein_path:
            return self.run_custom(
                protein_path=protein_path,
                ligand_path=ligand_path,
                batch_size=batch_size,
                run_id=run_id,
                sample_only=sample_only,
                gpus=gpus,
            )
        if mode == "prudent":
            if data_id is None:
                return {"ok": False, "error": "prudent 模式需要 data_id"}
            return self.run_prudent(data_id=data_id, run_id=run_id, gpu=gpus)
        if data_id is None:
            data_id = 0
        return self.run_dynamic(
            data_id=data_id,
            batch_size=batch_size,
            run_id=run_id,
            sample_only=sample_only,
            gpus=gpus,
        )

    # ------------------------------------------------------------- prudent 生成
    def run_prudent(
        self,
        *,
        data_id: int,
        run_id: Optional[str] = None,
        gpu: Optional[str] = None,
        timeout: int = 7200,
    ) -> dict[str, Any]:
        """Prudent 累积式生成。"""
        run_id = run_id or f"prudent_data{data_id}_{int(time.time())}"
        out = self._run_output_dir(run_id)
        run_cfg = self._render_run_config(
            mode="prudent", batch_size=5, output_dir=out
        )

        args = [
            "python", _PRUDENT_SCRIPT,
            "--data_id", str(data_id),
            "--config", str(run_cfg),
            "--output_dir", str(out),
            "--gpu", gpu or self._gpu_arg(),
            "--timeout", str(timeout),
        ]
        result = self._run(args, cwd=self.root, timeout=timeout + 300)
        pt_path = self._discover_pt(out, result.get("stdout") or "")
        result.update(
            {
                "run_id": run_id,
                "mode": "prudent",
                "data_id": data_id,
                "output_dir": str(out),
                "run_config": str(run_cfg),
                "pt_path": pt_path,
            }
        )
        return result

    # ------------------------------------------------------------------ 评估
    def evaluate(
        self,
        *,
        pt_file: str,
        run_id: Optional[str] = None,
        gpus: Optional[str] = None,
        visualize: bool = False,
    ) -> dict[str, Any]:
        """8 维口袋质量评估（evaluate_pocket_quality.py）。"""
        run_id = run_id or f"eval_{Path(pt_file).stem}_{int(time.time())}"
        out = self._run_output_dir(run_id)

        args = [
            "python", _EVAL_SCRIPT,
            "--pt_file", str(pt_file),
            "--gpus", gpus or self._gpu_arg(),
        ]
        if visualize:
            args.append("--visualize")

        result = self._run(args, cwd=self.root, timeout=3600)
        result.update(
            {
                "run_id": run_id,
                "pt_file": str(pt_file),
                "output_dir": str(out),
            }
        )
        return result

    # -------------------------------------------------------------- pt → SDF
    def extract_pt(
        self,
        *,
        pt_file: str,
        output_dir: Optional[str] = None,
        protein_root: Optional[str] = None,
        remove_fragments: bool = True,
        max_samples: int = 5,
    ) -> dict[str, Any]:
        """从 .pt 提取 SDF（extract_pt_to_sdf_excel.py）。"""
        pt_path = Path(pt_file)
        if not pt_path.is_file():
            return {"ok": False, "error": f".pt 文件不存在: {pt_file}"}

        out = Path(output_dir) if output_dir else pt_path.parent / f"eval_{pt_path.stem}_{int(time.time())}"
        out.mkdir(parents=True, exist_ok=True)
        pr_root = Path(protein_root or self.protein_root)

        args = [
            "python", _EVAL_RECONSTRUCT_SCRIPT,
            str(pt_path.resolve()),
            "--protein_root", str(pr_root.resolve()),
            "--output_dir", str(out.resolve()),
            "--atom_mode", "add_aromatic",
            "--exhaustiveness", "8",
        ]
        if remove_fragments:
            args.append("--remove-fragments")

        extra_env = {
            "VINA_DOCK_TIMEOUT_SEC": str(self.settings.vina_timeout),
            "EVAL_SINGLE_MOL_TIMEOUT": str(max(self.settings.vina_timeout * max_samples, 120)),
        }
        result = self._run(
            args,
            cwd=self.root,
            timeout=3600,
            extra_env=extra_env,
        )
        sdf_files = self.find_sdf_files(out)
        merged_sdf = out / f"{pt_path.stem}_molecules.sdf"
        if sdf_files:
            self.merge_sdf_files(sdf_files, merged_sdf)

        result.update(
            {
                "pt_file": str(pt_path.resolve()),
                "eval_dir": str(out),
                "sdf_files": [str(p) for p in sdf_files],
                "sdf_path": str(merged_sdf) if merged_sdf.is_file() else (str(sdf_files[0]) if sdf_files else None),
            }
        )
        return result

    # ------------------------------------------------------- 自动链式（生成+提取）
    def auto_chain(
        self,
        *,
        data_id: Optional[int] = None,
        protein_path: Optional[str] = None,
        ligand_path: Optional[str] = None,
        batch_size: int = 5,
        mode: str = "dynamic",
        max_samples: int = 5,
        remove_fragments: bool = True,
    ) -> dict[str, Any]:
        """生成后自动提取 SDF（CLAUDE.md：auto_evaluate + auto_extract）。"""
        gen = self.run_generate(
            mode=mode,
            data_id=data_id,
            protein_path=protein_path,
            ligand_path=ligand_path,
            batch_size=batch_size,
            sample_only=True,
        )
        if not gen.get("ok"):
            return {"stage": "generate", "generate": gen, "ok": False}

        pt_file = gen.get("pt_path")
        if not pt_file:
            pt_file = self._discover_pt(Path(gen["output_dir"]), gen.get("stdout") or "")
        if not pt_file:
            gen["ok"] = False
            gen["error"] = "未找到生成的 .pt 文件"
            return {"stage": "generate", "generate": gen, "ok": False}

        extract = self.extract_pt(
            pt_file=pt_file,
            remove_fragments=remove_fragments,
            max_samples=max_samples,
        )
        return {
            "stage": "extract",
            "generate": gen,
            "extract": extract,
            "ok": extract.get("ok", False),
            "pt_path": pt_file,
            "sdf_path": extract.get("sdf_path"),
        }

    def round_output_dir(self, round_id: int) -> Path:
        return self._run_output_dir(f"round_{round_id}")
