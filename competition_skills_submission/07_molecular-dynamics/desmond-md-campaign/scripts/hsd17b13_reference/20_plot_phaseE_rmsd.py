#!/usr/bin/env python3
"""Create publication-style Phase E protein/ligand RMSD figures."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROTEIN = "#24557A"
LIGAND = "#D95F02"
GRID = "#D5D9DC"
LATE = "#E7EFF3"
STATUS = {
    "RETAINED": "#2E7D32",
    "ALT_POSE": "#B36B00",
    "WEAK_RETENTION": "#6D6D6D",
    "LOST": "#B3261E",
}


def style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 8,
            "axes.linewidth": 0.7,
            "axes.labelsize": 8,
            "axes.titlesize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "legend.fontsize": 7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def clean_axis(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.grid(axis="y", color=GRID, linewidth=0.45, alpha=0.65)
    axis.tick_params(length=2.5)


def save(figure: plt.Figure, output_dir: Path, stem: str) -> None:
    figure.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight")
    figure.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(figure)


def overview(
    traces: pd.DataFrame,
    metrics: pd.DataFrame,
    molecule_ids: list[str],
    output_dir: Path,
) -> None:
    columns = 4
    rows = math.ceil(len(molecule_ids) / columns)
    figure, axes = plt.subplots(rows, columns, figsize=(7.2, 1.58 * rows), sharex=True)
    axes = np.asarray(axes).reshape(-1)
    for axis, molecule_id in zip(axes, molecule_ids):
        table = traces[traces["molecule_id"] == molecule_id].sort_values("time_ns")
        axis.axvspan(40, 50, color=LATE, lw=0, zorder=0)
        axis.plot(table["time_ns"], table["protein_ca"], color=PROTEIN, lw=0.75)
        axis.plot(table["time_ns"], table["ligand_wrt_protein"], color=LIGAND, lw=0.75)
        retention = metrics.loc[molecule_id, "binding_retention"]
        axis.set_title(molecule_id, color=STATUS.get(retention, "#222222"), fontweight="bold", pad=2)
        axis.set_xlim(0, 50)
        axis.set_ylim(bottom=0)
        clean_axis(axis)
    for axis in axes[len(molecule_ids):]:
        axis.set_visible(False)
    handles = [
        plt.Line2D([0], [0], color=PROTEIN, lw=1.3, label=r"Protein C$\alpha$"),
        plt.Line2D([0], [0], color=LIGAND, lw=1.3, label="Ligand fitted on protein"),
    ]
    figure.legend(handles=handles, loc="upper center", ncol=2, frameon=False)
    figure.supxlabel("Production time (ns)", y=0.005)
    figure.supylabel(r"RMSD ($\AA$)", x=0.005)
    figure.tight_layout(rect=(0.02, 0.02, 1, 0.965), h_pad=0.8, w_pad=0.7)
    save(figure, output_dir, "01_protein_ligand_rmsd_overview")


def individual_figures(
    traces: pd.DataFrame,
    metrics: pd.DataFrame,
    molecule_ids: list[str],
    output_dir: Path,
) -> None:
    per_molecule = output_dir / "per_molecule"
    per_molecule.mkdir(parents=True, exist_ok=True)
    for molecule_id in molecule_ids:
        table = traces[traces["molecule_id"] == molecule_id].sort_values("time_ns").copy()
        table["protein_smooth"] = table["protein_ca"].rolling(5, center=True, min_periods=1).mean()
        table["ligand_smooth"] = table["ligand_wrt_protein"].rolling(5, center=True, min_periods=1).mean()
        row = metrics.loc[molecule_id]
        figure, axes = plt.subplots(2, 1, figsize=(6.6, 4.7), sharex=True)
        series = [
            (axes[0], "protein_ca", "protein_smooth", PROTEIN, r"Protein C$\alpha$ RMSD"),
            (axes[1], "ligand_wrt_protein", "ligand_smooth", LIGAND, "Ligand RMSD fitted on protein"),
        ]
        for axis, raw, smooth, color, label in series:
            axis.axvspan(40, 50, color=LATE, lw=0, zorder=0)
            axis.plot(table["time_ns"], table[raw], color=color, lw=0.55, alpha=0.32)
            axis.plot(table["time_ns"], table[smooth], color=color, lw=1.35, label="1 ns rolling mean")
            late_values = table.loc[table["time_ns"] >= 40, raw]
            axis.axhline(late_values.median(), color=color, lw=0.8, ls="--", alpha=0.9)
            axis.set_ylabel(label + r" ($\AA$)")
            axis.set_xlim(0, 50)
            axis.set_ylim(0, max(1.0, table[raw].quantile(0.995) * 1.16))
            clean_axis(axis)
        axes[1].set_xlabel("Production time (ns)")
        retention = row["binding_retention"]
        figure.suptitle(
            f"{molecule_id}   {retention}   late contact={row['late_direct_contact_coverage']:.0%}",
            x=0.08,
            ha="left",
            color=STATUS.get(retention, "#222222"),
            fontweight="bold",
            fontsize=10,
        )
        figure.text(
            0.98,
            0.965,
            f"late ligand mean {row['ligand_rmsd_late_mean']:.2f} A | protein p95 {row['protein_ca_p95']:.2f} A",
            ha="right",
            va="top",
            fontsize=7.5,
            color="#444444",
        )
        figure.tight_layout(rect=(0.02, 0.02, 1, 0.93), h_pad=0.45)
        save(figure, per_molecule, f"{molecule_id}_protein_ligand_rmsd")


def ranking(metrics: pd.DataFrame, output_dir: Path) -> None:
    ordered = metrics.sort_values("ligand_rmsd_late_mean", ascending=True)
    y = np.arange(len(ordered))
    figure, axes = plt.subplots(1, 2, figsize=(7.2, 6.4), sharey=True)
    axes[0].scatter(ordered["protein_ca_p95"], y, color=PROTEIN, s=18, zorder=3)
    axes[0].axvline(2.5, color="#777777", ls="--", lw=0.8)
    axes[0].set_xlabel(r"Protein C$\alpha$ RMSD p95 ($\AA$)")
    axes[0].set_yticks(y, ordered.index)
    colors = [STATUS.get(value, "#777777") for value in ordered["binding_retention"]]
    axes[1].scatter(ordered["ligand_rmsd_late_mean"], y, c=colors, s=20, zorder=3)
    axes[1].axvline(3.5, color="#777777", ls="--", lw=0.8)
    axes[1].set_xlabel(r"Late ligand RMSD mean ($\AA$)")
    for axis in axes:
        clean_axis(axis)
        axis.set_ylim(-0.7, len(ordered) - 0.3)
    figure.tight_layout(w_pad=1.0)
    save(figure, output_dir, "02_late_rmsd_ranking")


def diagnostics(
    traces: pd.DataFrame,
    metrics: pd.DataFrame,
    molecule_ids: list[str],
    output_dir: Path,
) -> None:
    rows = []
    for molecule_id in molecule_ids:
        table = traces[traces["molecule_id"] == molecule_id].sort_values("time_ns")
        row = metrics.loc[molecule_id]
        early = table.loc[table["time_ns"] <= 2, "ligand_wrt_protein"]
        late = table.loc[table["time_ns"] >= 40, "ligand_wrt_protein"]
        rows.append(
            {
                "molecule_id": molecule_id,
                "n_frames": len(table),
                "first_time_ns": table["time_ns"].min(),
                "last_time_ns": table["time_ns"].max(),
                "ligand_rmsd_first_A": table["ligand_wrt_protein"].iloc[0],
                "ligand_rmsd_0_2ns_median_A": early.median(),
                "ligand_rmsd_40_50ns_median_A": late.median(),
                "protein_ca_40_50ns_median_A": table.loc[table["time_ns"] >= 40, "protein_ca"].median(),
                "direct_contact_coverage": row["direct_contact_coverage"],
                "late_direct_contact_coverage": row["late_direct_contact_coverage"],
                "binding_retention": row["binding_retention"],
                "possible_initial_offset": bool(early.median() > 6 and row["direct_contact_coverage"] < 0.25),
            }
        )
    pd.DataFrame(rows).to_csv(output_dir / "phaseE_offset_diagnostics.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    output_dir = args.out or args.summary / "publication_figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    style()
    traces = pd.read_csv(args.summary / "md27_rmsd_traces.csv")
    metrics = pd.read_csv(args.summary / "md27_metrics.csv").set_index("molecule_id")
    molecule_ids = metrics.sort_values("md_triage_score", ascending=False).index.tolist()
    overview(traces, metrics, molecule_ids, output_dir)
    individual_figures(traces, metrics, molecule_ids, output_dir)
    ranking(metrics, output_dir)
    diagnostics(traces, metrics, molecule_ids, output_dir)
    print(f"Wrote publication figures for {len(molecule_ids)} molecules to {output_dir}")


if __name__ == "__main__":
    main()
