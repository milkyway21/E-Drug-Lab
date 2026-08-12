#!/usr/bin/env python3
"""Export SEA data tables from out.eaf without generating PDF/plots.

Use this when `event_analysis.py report` crashes in Qt image generation.
Must be run via: $SCHRODINGER/run python3 scripts/06c_export_data_only.py ...
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from schrodinger.Qt import qapplication
from schrodinger.application.desmond.event_analysis_dir import (  # type: ignore
    pl_interact_survey,
)
# Fallback import path used by installed scripts
try:
    from event_analysis import EventAnalysisPanel
except ImportError:
    import sys

    sys.path.insert(
        0,
        "/opt/schrodinger2023-3/mmshare-v6.3/python/scripts",
    )
    from event_analysis import EventAnalysisPanel


def export_one(eaf: Path, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    qapplication.get_application()
    ea = EventAnalysisPanel(test_mode=True)
    ea.loadEAF(str(eaf))
    ea.interactSurveyPanel.export_data(str(data_dir))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", required=True)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    ap.add_argument(
        "--analysis-root",
        type=Path,
        default=None,
        help="Directory containing <id>/ EAF outputs",
    )
    ap.add_argument(
        "--eaf-pattern",
        default="{mid}_sea-out.eaf",
        help="EAF filename pattern relative to each molecule directory",
    )
    args = ap.parse_args()
    analysis_root = args.analysis_root or args.root / "05_analysis/per_molecule"
    for mid in args.ids:
        out = analysis_root / mid
        eaf = out / args.eaf_pattern.format(mid=mid)
        data = out / "data"
        print(f"{datetime.now().isoformat(timespec='seconds')} {mid}: export_data")
        export_one(eaf, data)
        if args.analysis_root is None:
            inter = args.root / "05_analysis/interaction_tables" / mid
            inter.mkdir(parents=True, exist_ok=True)
            for f in data.glob("*.dat"):
                (inter / f.name).write_bytes(f.read_bytes())
        (out / "SEA_DONE.flag").write_text(datetime.now().isoformat() + "\n")
        print(
            f"{datetime.now().isoformat(timespec='seconds')} {mid}: DONE "
            f"n_dat={len(list(data.glob('*.dat')))}"
        )


if __name__ == "__main__":
    main()
