#!/usr/bin/env python3
"""Export SEA plot images from *-out.eaf without PDF (avoids Qt QImage OverflowError).

Must be run via: $SCHRODINGER/run python3 scripts/06d_export_plots_only.py --ids T1075
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from schrodinger.utils import qapplication

sys.path.insert(0, "/opt/schrodinger2023-3/mmshare-v6.3/python/scripts")
from event_analysis import EventAnalysisPanel  # noqa: E402


def export_plots(eaf: Path, data_dir: Path) -> list[str]:
    data_dir.mkdir(parents=True, exist_ok=True)
    qapplication.get_application()
    ea = EventAnalysisPanel(test_mode=True)
    ea.loadEAF(str(eaf))
    # Skip generateReportFile (PDF) — that crashes for some ligands.
    ea.interactSurveyPanel.export_plots(str(data_dir))
    return sorted(
        p.name
        for p in data_dir.iterdir()
        if p.suffix.lower() in {".png", ".svg", ".pdf", ".jpg"}
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", required=True)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = ap.parse_args()

    for mid in args.ids:
        out = args.root / "05_analysis/per_molecule" / mid
        eaf = out / f"{mid}_sea-out.eaf"
        data = out / "data"
        if not eaf.is_file():
            raise SystemExit(f"missing eaf: {eaf}")
        print(f"{datetime.now().isoformat(timespec='seconds')} {mid}: export_plots")
        names = export_plots(eaf, data)
        plots = out / "plots"
        plots.mkdir(exist_ok=True)
        for name in names:
            src = data / name
            (plots / name).write_bytes(src.read_bytes())
        (out / "PLOTS_DONE.flag").write_text(
            datetime.now().isoformat() + "\n" + "\n".join(names) + "\n"
        )
        print(
            f"{datetime.now().isoformat(timespec='seconds')} {mid}: DONE "
            f"n_img={len(names)} -> {data}"
        )
        for n in names:
            print(f"  {n}")


if __name__ == "__main__":
    main()
