#!/usr/bin/env python3
"""构建 MD 八体系 md8 特征表（需 pyarrow；推荐 diffdynamic env）。

用法:
  /home/user/anaconda3/envs/diffdynamic/bin/python backend/scripts/build_md8_feature_table.py
  # 或
  cd backend && ../.venv 若含 pyarrow: .venv/bin/python scripts/build_md8_feature_table.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/data/ye/e-drug-lab/backend")
sys.path.insert(0, str(ROOT))

from app.pipelines.vav1_rl.md_features import build_md8_features  # noqa: E402


def main() -> None:
    qc = build_md8_features()
    print(json.dumps(qc, indent=2, default=str))
    if not qc.get("gate_pass"):
        sys.exit(2)


if __name__ == "__main__":
    main()
