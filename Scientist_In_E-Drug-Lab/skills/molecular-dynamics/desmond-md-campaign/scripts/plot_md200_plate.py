#!/usr/bin/env python3
"""Render 200 ns RMSD as five rows by four columns on portrait A4."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


DEFAULT_OUTPUT = Path.cwd() / "md200_rmsd_5high_4wide"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--traces",
        type=Path,
        nargs="+",
        required=True,
        help="One or more md200_traces.csv files.",
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        nargs="+",
        required=True,
        help="One or more md200_decision_table.csv files.",
    )
    parser.add_argument(
        "--ids",
        nargs="*",
        help="Explicit row-major molecule order. The first 20 IDs are used.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--ymax",
        type=float,
        help="Optional common Y maximum for every panel; default is adaptive per molecule.",
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


def load_tables(paths: list[Path], label: str) -> pd.DataFrame:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {label}: {', '.join(missing)}")
    tables = [pd.read_csv(path) for path in paths]
    return pd.concat(tables, ignore_index=True)


def ordered_ids(
    traces: pd.DataFrame,
    decisions: pd.DataFrame,
    requested: list[str] | None,
) -> list[str]:
    if requested:
        ids = list(dict.fromkeys(requested))
    else:
        ranked = decisions.copy()
        if "rank" in ranked:
            ranked = ranked.sort_values("rank", kind="stable")
        ids = ranked["molecule_id"].astype(str).drop_duplicates().tolist()
        ids.extend(mid for mid in traces["molecule_id"].astype(str).unique() if mid not in ids)
    if len(ids) > 20:
        raise ValueError(f"The 5 x 4 plate accepts at most 20 molecules; received {len(ids)}")
    return ids


def class_letter(value: object) -> str:
    text = str(value).strip().upper()
    return text[:1] if text[:1] in CLASS_COLORS else ""


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
    axis.set_xlim(0.0, 200.0)
    axis.set_ylim(0.0, ymax)
    axis.set_xticks([0, 50, 100, 150, 200])
    axis.set_yticks([0.0, ymax / 2.0, ymax])
    # The former 2:1 panel is 20% taller: height / width = 0.5 * 1.2 = 0.6.
    axis.set_box_aspect(0.6)
    axis.tick_params(
        axis="both",
        colors=AXIS_NAVY,
        direction="out",
        length=1.8,
        width=0.45,
        pad=1.2,
        labelsize=5,
    )
    axis.spines["top"].set_visible(False)
    for side in ("left", "bottom", "right"):
        axis.spines[side].set_color(AXIS_NAVY)
        axis.spines[side].set_linewidth(0.5)
    axis.grid(False)


def render(
    traces: pd.DataFrame,
    decisions: pd.DataFrame,
    ids: list[str],
    output: Path,
    ymax: float | None,
    dpi: int,
) -> None:
    required_trace = {"molecule_id", "time_ns", "protein_ca_rmsd_geom", "ligand_rmsd_geom"}
    required_decision = {"molecule_id", "md_class"}
    if missing := required_trace.difference(traces.columns):
        raise ValueError(f"Trace table is missing columns: {sorted(missing)}")
    if missing := required_decision.difference(decisions.columns):
        raise ValueError(f"Decision table is missing columns: {sorted(missing)}")
    if ymax is not None and ymax <= 0:
        raise ValueError("The Y-axis maximum must be positive")

    traces = traces.drop_duplicates(["molecule_id", "frame"], keep="last")
    classes = (
        decisions.drop_duplicates("molecule_id", keep="last")
        .set_index("molecule_id")["md_class"]
        .map(class_letter)
        .to_dict()
    )

    page_width = 8.27
    page_height = 11.69
    panel_width = 1.525
    panel_height = panel_width * 0.6
    column_gap = 0.534
    row_gap = 1.566 / 3.0
    block_height = 5.0 * panel_height + 4.0 * row_gap
    block_bottom = (page_height - block_height) / 2.0

    figure = plt.figure(figsize=(page_width, page_height))
    figure.patch.set_facecolor(FIGURE_BG)
    axes = np.empty((5, 4), dtype=object)
    for row in range(5):
        for column in range(4):
            left = 0.447 + column * (panel_width + column_gap)
            bottom = block_bottom + (4 - row) * (panel_height + row_gap)
            axes[row, column] = figure.add_axes(
                [
                    left / page_width,
                    bottom / page_height,
                    panel_width / page_width,
                    panel_height / page_height,
                ]
            )

    plotted: list[str] = []
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
                table[["protein_ca_rmsd_geom", "ligand_rmsd_geom"]].to_numpy(dtype=float).ravel()
            )
        style_axis(axis, panel_ymax)
        axis.plot(
            table["time_ns"],
            table["protein_ca_rmsd_geom"],
            color=PROTEIN,
            linewidth=0.52,
            alpha=0.9,
            antialiased=True,
            zorder=3,
        )
        axis.plot(
            table["time_ns"],
            table["ligand_rmsd_geom"],
            color=LIGAND,
            linewidth=0.52,
            alpha=0.86,
            antialiased=True,
            zorder=4,
        )
        letter = classes.get(molecule_id, "")
        axis.set_title(
            molecule_id,
            color=CLASS_COLORS.get(letter, AXIS_NAVY),
            fontsize=7,
            fontweight="semibold",
            pad=1.5,
        )
        plotted.append(molecule_id)

    handles = [
        Line2D([0], [0], color=PROTEIN, linewidth=0.8, label=r"Protein C$\alpha$ RMSD"),
        Line2D([0], [0], color=LIGAND, linewidth=0.8, label="Ligand RMSD"),
    ]
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, (block_bottom - 0.42) / page_height),
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
        metadata={"Title": "200 ns protein and ligand RMSD"},
    )
    figure.savefig(output.with_suffix(".png"), dpi=dpi, facecolor=figure.get_facecolor())
    plt.close(figure)

    print(f"Plotted {len(plotted)}/{len(ids)} supplied molecules: {', '.join(plotted)}")
    print("Canvas: 8.27 x 11.69 in (portrait A4); grid: 5 rows x 4 columns")
    print("Panel width:height ratio: 1.667:1 (20% taller than 2:1)")
    print(f"Physical panel height: {panel_height:.3f} in; physical row gap: {row_gap:.3f} in")
    print(f"Shared protein/ligand Y axis: {'adaptive per molecule' if ymax is None else f'0-{ymax:g} A'}")
    print(output.with_suffix(".pdf"))
    print(output.with_suffix(".png"))


def main() -> None:
    args = parse_args()
    configure_style()
    traces = load_tables(args.traces, "trace CSV")
    decisions = load_tables(args.decisions, "decision CSV")
    ids = ordered_ids(traces, decisions, args.ids)
    render(
        traces=traces,
        decisions=decisions,
        ids=ids,
        output=args.output,
        ymax=args.ymax,
        dpi=args.dpi,
    )


if __name__ == "__main__":
    main()
