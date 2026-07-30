"""GLARE train / query / reinforce runner."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.config import GlareSettings
from app.services.conda_runner import conda_run
from app.services.rl_round_service import rounds_base_dir

logger = logging.getLogger(__name__)


class GlareRunner:
    def __init__(self, settings: GlareSettings):
        self.settings = settings
        self.root = Path(settings.root).resolve()

    def rl_rounds_root(self) -> Path:
        """RL 轮次输出根目录：优先配置 outputs_dir，否则复用规范 rl_rounds 路径。"""
        if self.settings.outputs_dir:
            base = Path(self.settings.outputs_dir)
            base.mkdir(parents=True, exist_ok=True)
            return base
        return rounds_base_dir()

    def status(self) -> dict[str, Any]:
        cfg = self.root / self.settings.config_path
        db = self.root / self.settings.db_path
        checkpoints = list(self._scan_checkpoints())
        return {
            "root": str(self.root),
            "config_path": str(cfg),
            "config_exists": cfg.is_file(),
            "db_path": str(db),
            "db_exists": db.is_file(),
            "seed_activity_file": str(self.root / self.settings.seed_activity_file),
            "rl_rounds_root": str(self.rl_rounds_root()),
            "checkpoints": checkpoints[:20],
            "checkpoint_count": len(checkpoints),
        }

    def _scan_checkpoints(self) -> list[str]:
        patterns = ["**/round_*_glare_trained_checkpoint.pt", "**/round_*_glare_reinforced_checkpoint.pt",
                    "**/round_*_glare_seed_reinforced_checkpoint.pt"]
        roots = [self.root, self.rl_rounds_root()]
        found: list[str] = []
        for root in roots:
            if not root.is_dir():
                continue
            for pat in patterns:
                found.extend(str(p) for p in root.glob(pat))
        return sorted(set(found), key=lambda p: Path(p).stat().st_mtime if Path(p).is_file() else 0, reverse=True)

    def round_glare_dir(self, round_id: int) -> Path:
        out = self.rl_rounds_root() / f"round_{round_id}" / "glare_results"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _run_script(self, script_rel: str, args: list[str], timeout: int = 3600) -> dict[str, Any]:
        cmd = ["python", script_rel, *args]
        proc = conda_run(self.settings.conda_env, cmd, cwd=self.root, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:] if proc.stdout else "",
            "stderr": proc.stderr[-4000:] if proc.stderr else "",
        }

    def run_seed_reinforce(self, *, evaluated_file: str, round_id: int, output_dir: Optional[str] = None) -> dict[str, Any]:
        out = output_dir or str(self.round_glare_dir(round_id))
        seed = str(self.root / self.settings.seed_activity_file)
        result = self._run_script("glare_selector/reinforce_glare_with_seed_data.py", [
            "--seed_file", seed,
            "--evaluated_file", evaluated_file,
            "--round_id", str(round_id),
            "--output_dir", out,
        ])
        ckpt = Path(out) / f"round_{round_id}_glare_seed_reinforced_checkpoint.pt"
        result["checkpoint"] = str(ckpt) if ckpt.is_file() else None
        result["output_dir"] = out
        return result

    def run_wetlab_reinforce(
        self,
        *,
        evaluated_file: str,
        round_id: int,
        wetlab_file: str,
        previous_checkpoint: Optional[str] = None,
        labeled_pool: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        out = output_dir or str(self.round_glare_dir(round_id))
        pool = labeled_pool or str(self.rl_rounds_root() / "labeled_pool_master.xlsx")
        import_args = [
            "--round_id", str(round_id),
            "--wetlab_file", wetlab_file,
            "--labeled_pool", pool,
        ]
        imp = self._run_script("glare_selector/import_wetlab_pdc50.py", import_args)
        if not imp["ok"]:
            return {**imp, "step": "import_wetlab"}

        prev = previous_checkpoint or str(Path(out) / f"round_{round_id}_glare_seed_reinforced_checkpoint.pt")
        result = self._run_script("glare_selector/reinforce_glare_with_wetlab.py", [
            "--round_id", str(round_id),
            "--labeled_pool", pool,
            "--wetlab_file", wetlab_file,
            "--evaluated_file", evaluated_file,
            "--output_dir", out,
            "--previous_checkpoint", prev,
        ])
        ckpt = Path(out) / f"round_{round_id}_glare_reinforced_checkpoint.pt"
        result["checkpoint"] = str(ckpt) if ckpt.is_file() else None
        result["output_dir"] = out
        return result

    def run_train(self, *, evaluated_file: str, round_id: int, output_dir: Optional[str] = None) -> dict[str, Any]:
        out = output_dir or str(self.round_glare_dir(round_id))
        seed = str(self.root / self.settings.seed_activity_file)
        result = self._run_script("glare_selector/train_glare_policy.py", [
            "train",
            "--evaluated_file", evaluated_file,
            "--seed_file", seed,
            "--round_id", str(round_id),
            "--output_dir", out,
        ], timeout=7200)
        ckpt = Path(out) / f"round_{round_id}_glare_trained_checkpoint.pt"
        result["checkpoint"] = str(ckpt) if ckpt.is_file() else None
        result["output_dir"] = out
        return result

    def run_screen(
        self,
        *,
        evaluated_file: str,
        round_id: int,
        checkpoint: str,
        top_n: int = 200,
        wetlab_sample_count: int = 0,
        output_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        out = output_dir or str(self.round_glare_dir(round_id))
        result = self._run_script("glare_selector/train_glare_policy.py", [
            "query",
            "--evaluated_file", evaluated_file,
            "--checkpoint", checkpoint,
            "--round_id", str(round_id),
            "--output_dir", out,
            "--top_n", str(top_n),
            "--wetlab_sample_count", str(wetlab_sample_count),
        ], timeout=3600)
        csv_path = Path(out) / f"round_{round_id}_glare_ranked_all.csv"
        result["ranked_csv"] = str(csv_path) if csv_path.is_file() else None
        result["output_dir"] = out
        return result

    def latest_checkpoint(self, round_id: Optional[int] = None) -> Optional[str]:
        cands = self._scan_checkpoints()
        if round_id is not None:
            tag = f"round_{round_id}_"
            cands = [c for c in cands if tag in c]
        return cands[0] if cands else None
