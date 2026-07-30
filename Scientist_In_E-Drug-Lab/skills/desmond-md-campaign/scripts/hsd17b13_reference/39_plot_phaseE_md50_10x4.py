#!/usr/bin/env python3
"""Render all 40 Phase E 50 ns RMSD traces as a 10-by-4 portrait-A4 plate."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BATCH = "phaseE_corrected_pose_2_50_all40_20260727"
ANALYSIS = ROOT / "05_analysis" / BATCH
DEFAULT_TRACES = ANALYSIS / "summary" / "md27_rmsd_traces.csv"
DEFAULT_METRICS = ANALYSIS / "summary" / "md27_metrics.csv"
DEFAULT_DIAGNOSTICS = ANALYSIS / "pocket_geometry" / "phaseE_target_pocket_diagnostics.csv"
DEFAULT_OUTPUT = (
    ANALYSIS
    / "summary"
    / "publication_figures"
    / "phaseE_md50_rmsd_10high_4wide_all40_h95"
)

FIGURE_BG = "#FFFFFF"
AXIS_BG = "#F1F8FC"
AXIS_NAVY = "#173B57"
PROTEIN = "#1F6A8A"
LIGAND = "#D85F4A"
CLASS_COLORS = {
    "A": "#238557",
    "B": "#C68700",
    "C": "#C94848",
    "D": "#A73434",
}
DIAGNOSIS_CLASS = {
    "target_pocket_retained": "A",
    "contact_retained_rearrangement": "B",
    "inconclusive_displacement": "C",
    "pocket_exit": "D",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--diagnostics", type=Path, default=DEFAULT_DIAGNOSTICS)
    parser.add_argument(
        "--ids",
        nargs="*",
        help="Explicit row-major molecule order. At most 40 IDs are accepted.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--ymax",
        type=float,
        help="Optional common Y maximum; default is adaptive per molecule.",
    )
    parser.add_argument("--dpi", type=int, default=600)
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 5,
            "axes.titlesize": 7,
            "axes.linewidth": 0.5,
            "xtick.labelsize": 5,
            "ytick.labelsize": 5,
            "xtick.major.width": 0.45,
            "ytick.major.width": 0.45,
            "legend.fontsize": 7,
            "lines.solid_capstyle": "round",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def read_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return pd.read_csv(path)


def ordered_ids(
    traces: pd.DataFrame,
    metrics: pd.DataFrame,
    diagnostics: pd.DataFrame,
    requested: list[str] | None,
) -> list[str]:
    available = traces["molecule_id"].astype(str).drop_duplicates().tolist()
    if requested:
        ids = list(dict.fromkeys(requested))
        unknown = [mid for mid in ids if mid not in available]
        if unknown:
            raise ValueError(f"IDs absent from trace data: {', '.join(unknown)}")
    else:
        ranking = diagnostics[["molecule_id", "pocket_diagnosis"]].copy()
        ranking["molecule_id"] = ranking["molecule_id"].astype(str)
        ranking["md_class"] = ranking["pocket_diagnosis"].map(DIAGNOSIS_CLASS).fillna("C")
        if "md_triage_score" in metrics:
            ranking = ranking.merge(
                metrics[["molecule_id", "md_triage_score"]],
                on="molecule_id",
                how="left",
                validate="one_to_one",
            )
        else:
            ranking["md_triage_score"] = np.nan
        ranking["class_order"] = ranking["md_class"].map({"A": 0, "B": 1, "C": 2, "D": 3})
        ranking = ranking.sort_values(
            ["class_order", "md_triage_score", "molecule_id"],
            ascending=[True, False, True],
            kind="stable",
        )
        ids = ranking["molecule_id"].tolist()
        ids.extend(mid for mid in available if mid not in ids)
    if len(ids) > 40:
        raise ValueError(f"The 10 x 4 plate accepts at most 40 molecules; received {len(ids)}")
    return ids


def nice_upper(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return 2.0
    target = max(2.0, float(finite.max()) * 1.04)
    magnitude = 10.0 ** np.floor(np.log10(target))
    scaled = target / magnitude
    for candidate in (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if scaled <= candidate:
            return candidate * magnitude
    return 10.0 * magnitude


def style_axis(axis: plt.Axes, ymax: float) -> None:
    axis.set_facecolor(AXIS_BG)
    axis.set_xlim(0.0, 50.0)
    axis.set_ylim(0.0, ymax)
    axis.set_xticks([0, 25, 50])
    axis.set_yticks([0.0, ymax / 2.0, ymax])
    axis.set_box_aspect(0.57)
    axis.tick_params(
        axis="both",
        colors=AXIS_NAVY,
        direction="out",
        length=1.6,
        width=0.45,
        pad=1.0,
        labelsize=5,
    )
    axis.spines["top"].set_visible(False)
    for side in ("left", "bottom", "right"):
        axis.spines[side].set_color(AXIS_NAVY)
        axis.spines[side].set_linewidth(0.5)
    axis.grid(False)


def render(
    traces: pd.DataFrame,
    diagnostics: pd.DataFrame,
    ids: list[str],
    output: Path,
    ymax: float | None,
    dpi: int,
) -> None:
    required_trace = {"molecule_id", "frame", "time_ns", "protein_ca", "ligand_wrt_protein"}
    required_diagnostics = {"molecule_id", "pocket_diagnosis"}
    if missing := required_trace.difference(traces.columns):
        raise ValueError(f"Trace table is missing columns: {sorted(missing)}")
    if missing := required_diagnostics.difference(diagnostics.columns):
        raise ValueError(f"Diagnostics table is missing columns: {sorted(missing)}")
    if ymax is not None and ymax <= 0:
        raise ValueError("The Y-axis maximum must be positive")

    traces = traces.drop_duplicates(["molecule_id", "frame"], keep="last")
    diagnoses = (
        diagnostics.drop_duplicates("molecule_id", keep="last")
        .set_index("molecule_id")["pocket_diagnosis"]
        .to_dict()
    )

    page_width = 8.27
    page_height = 11.69
    panel_width = 1.46
    original_panel_height = panel_width * 0.6
    panel_height = original_panel_height * 0.95
    column_gap = 0.48
    row_gap = 0.17 + 10.0 * (original_panel_height - panel_height) / 9.0
    block_width = 4.0 * panel_width + 3.0 * column_gap
    block_height = 10.0 * panel_height + 9.0 * row_gap
    block_left = (page_width - block_width) / 2.0
    block_bottom = (page_height - block_height) / 2.0

    figure = plt.figure(figsize=(page_width, page_height))
    figure.patch.set_facecolor(FIGURE_BG)
    axes = np.empty((10, 4), dtype=object)
    for row in range(10):
        for column in range(4):
            left = block_left + column * (panel_width + column_gap)
            bottom = block_bottom + (9 - row) * (panel_height + row_gap)
            axes[row, column] = figure.add_axes(
                [
                    left / page_width,
                    bottom / page_height,
                    panel_width / page_width,
                    panel_height / page_height,
                ]
            )

    plotted: list[str] = []
    class_counts = {letter: 0 for letter in CLASS_COLORS}
    for index, axis in enumerate(axes.flat):
        if index >= len(ids):
            axis.set_visible(False)
            continue
        molecule_id = ids[index]
        table = traces.loc[traces["molecule_id"].astype(str) == molecule_id].sort_values("time_ns")
        if table.empty:
            axis.set_visible(False)
            continue

        panel_ymax = ymax
        if panel_ymax is None:
            panel_ymax = nice_upper(
                table[["protein_ca", "ligand_wrt_protein"]].to_numpy(dtype=float).ravel()
            )
        style_axis(axis, panel_ymax)
        axis.plot(
            table["time_ns"],
            table["protein_ca"],
            color=PROTEIN,
            linewidth=0.48,
            alpha=0.9,
            antialiased=True,
            zorder=3,
        )
        axis.plot(
            table["time_ns"],
            table["ligand_wrt_protein"],
            color=LIGAND,
            linewidth=0.48,
            alpha=0.86,
            antialiased=True,
            zorder=4,
        )
        letter = DIAGNOSIS_CLASS.get(str(diagnoses.get(molecule_id, "")), "C")
        axis.set_title(
            molecule_id,
            color=CLASS_COLORS[letter],
            fontsize=7,
            fontweight="semibold",
            pad=1.0,
        )
        class_counts[letter] += 1
        plotted.append(molecule_id)

    handles = [
        Line2D([0], [0], color=PROTEIN, linewidth=0.8, label=r"Protein C$\alpha$ RMSD"),
        Line2D([0], [0], color=LIGAND, linewidth=0.8, label="Ligand RMSD"),
    ]
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.017),
        ncol=2,
        frameon=False,
        fontsize=7,
        handlelength=2.8,
        handletextpad=0.6,
        columnspacing=2.4,
        labelcolor=AXIS_NAVY,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output.with_suffix(".pdf"),
        facecolor=figure.get_facecolor(),
        metadata={"Title": "Phase E 50 ns protein and ligand RMSD for all 40 molecules"},
    )
    figure.savefig(output.with_suffix(".png"), dpi=dpi, facecolor=figure.get_facecolor())
    plt.close(figure)

    counts = ", ".join(f"{letter}={class_counts[letter]}" for letter in CLASS_COLORS)
    print(f"Plotted {len(plotted)}/{len(ids)} supplied molecules ({counts})")
    print("Canvas: 8.27 x 11.69 in (portrait A4); grid: 10 rows x 4 columns")
    print("Panel height: 95% of the previous version; width:height ratio: 1.754:1")
    print(f"Physical panel height: {panel_height:.3f} in; physical row gap: {row_gap:.3f} in")
    print(f"Shared protein/ligand Y axis: {'adaptive per molecule' if ymax is None else f'0-{ymax:g} A'}")
    print(output.with_suffix(".pdf"))
    print(output.with_suffix(".png"))


def main() -> None:
    args = parse_args()
    configure_style()
    traces = read_csv(args.traces, "trace CSV")
    metrics = read_csv(args.metrics, "metrics CSV")
    diagnostics = read_csv(args.diagnostics, "diagnostics CSV")
    ids = ordered_ids(traces, metrics, diagnostics, args.ids)
    render(
        traces=traces,
        diagnostics=diagnostics,
        ids=ids,
        output=args.output,
        ymax=args.ymax,
        dpi=args.dpi,
    )


if __name__ == "__main__":
    main()
