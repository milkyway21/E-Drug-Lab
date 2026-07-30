"""DiffGUI batch generation runner."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.config import DiffGuiSettings
from app.services.conda_runner import conda_run
from app.services.rl_round_service import rounds_base_dir

logger = logging.getLogger(__name__)


class DiffGuiRunner:
    def __init__(self, settings: DiffGuiSettings):
        self.settings = settings
        self.root = Path(settings.root).resolve()

    def status(self) -> dict[str, Any]:
        sample_cfg = self.root / self.settings.sample_config
        generate_script = self.root / "scripts" / "run_batch_generate.py"
        return {
            "root": str(self.root),
            "root_exists": self.root.is_dir(),
            "conda_env": self.settings.conda_env,
            "sample_config": str(sample_cfg),
            "sample_config_exists": sample_cfg.is_file(),
            "generate_script_exists": generate_script.is_file(),
        }

    def round_output_dir(self, round_id: int) -> Path:
        base = Path(self.settings.outputs_dir)
        if not base.is_absolute():
            # 相对路径解析到规范 RL 轮次根目录（backend/outputs/rl_rounds）
            base = rounds_base_dir()
        out = base / f"round_{round_id}" / "generated"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def run_generate(
        self,
        *,
        protein_file: str,
        round_id: int,
        num_mols: int = 5,
        batch_size: int = 5,
        require_achiral: bool = True,
        pocket_file: Optional[str] = None,
        project_name: str = "vav1_molecular_glue",
        target_name: str = "VAV1",
        device: Optional[str] = None,
        config: Optional[str] = None,
    ) -> dict[str, Any]:
        output_dir = self.round_output_dir(round_id)
        protein_path = Path(protein_file)
        if not protein_path.is_file():
            return {"ok": False, "error": f"Protein file not found: {protein_file}"}

        cmd = [
            "python",
            "scripts/run_batch_generate.py",
            "--project_name", project_name,
            "--target_name", target_name,
            "--protein_file", str(protein_path.resolve()),
            "--num_mols", str(num_mols),
            "--batch_size", str(batch_size),
            "--round_id", str(round_id),
            "--require_achiral", "true" if require_achiral else "false",
            "--output_dir", str(output_dir),
            "--config", config or self.settings.sample_config,
            "--device", device or self.settings.default_device,
        ]
        if pocket_file:
            cmd.extend(["--pocket_file", pocket_file])

        logger.info("DiffGUI generate: %s", " ".join(cmd))
        proc = conda_run(self.settings.conda_env, cmd, cwd=self.root, timeout=7200)
        sdf = output_dir / f"round_{round_id}_all.sdf"
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:] if proc.stdout else "",
            "stderr": proc.stderr[-4000:] if proc.stderr else "",
            "output_dir": str(output_dir),
            "sdf_path": str(sdf) if sdf.is_file() else None,
            "pt_path": str(output_dir / f"round_{round_id}_all.pt"),
        }
