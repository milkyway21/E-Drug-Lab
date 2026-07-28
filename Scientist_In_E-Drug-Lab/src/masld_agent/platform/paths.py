"""Platform path defaults (overridable via env)."""
from __future__ import annotations

import os
from pathlib import Path

from masld_agent.config import PKG_ROOT

CATALOG_PATH = PKG_ROOT / "config" / "platform" / "catalog.yaml"
PLATFORM_MD = PKG_ROOT / "config" / "platform" / "PLATFORM.md"

DIFFDYNAMIC_ROOT = Path(
    os.environ.get("MASLD_DIFFDYNAMIC_ROOT", "/data/ye/DiffDynamic")
)
DIFFDYNAMIC_CONDA = Path(
    os.environ.get(
        "MASLD_DIFFDYNAMIC_CONDA",
        "/home/user/anaconda3/envs/diffdynamic",
    )
)
DIFFDYNAMIC_CONDA_NAME = os.environ.get("MASLD_DIFFDYNAMIC_CONDA_NAME", "diffdynamic")

SCHRODINGER_HOME = Path(
    os.environ.get("SCHRODINGER", os.environ.get("MASLD_SCHRODINGER", "/opt/schrodinger2023-3"))
)

EDRUG_ROOT = Path(os.environ.get("MASLD_EDRUG_ROOT", "/data/ye/e-drug-lab"))
EDRUG_BACKEND = Path(
    os.environ.get("MASLD_EDRUG_BACKEND", str(EDRUG_ROOT / "backend"))
)

HSVPOL_TEMPLATES = Path(
    os.environ.get(
        "MASLD_HSVPOL_TEMPLATES",
        "/home/user/Desktop/Ye/DiffDynamic/hsvpol/pipeline_templates",
    )
)

LARGE_BATCH_THRESHOLD = int(os.environ.get("MASLD_PLATFORM_LARGE_BATCH", "100"))
DEFAULT_GPUS = os.environ.get("MASLD_DIFFDYNAMIC_GPUS", "1-5")
