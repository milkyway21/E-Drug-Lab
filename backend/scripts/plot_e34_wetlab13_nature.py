#!/usr/bin/env python3
"""
Nature-style multi-panel figure for E34 wet-lab similar-molecule ranking.

Core conclusion:
  GLARE E34 (cycle 7) enriches 13 wet-lab-similar molecules far above random
  within a ~10K MolFactory pool (mean rank top 13.2%; 5/13 in top 10%).

Archetype: quantitative grid | Backend: Python | Width: 183 mm (double column)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
# ── Paths ──────────────────────────────────────────────────────────────────
E34_JSON = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e34_full_403/wetlab_13_similar_ranking.json"
)
E32_JSON = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e32_paper_al_20260630/wetlab_13_ranking/wetlab_13_similar_ranking.json"
)
OUT_DIR = E34_JSON.parent / "figures"
STEM = "fig_e34_wetlab13_nature"

# E33 ranks from prior wetlab_13 comparison summary (same 13 IDs, same order)
E33_RANK_MAP = {
    "0228271": 2464,
    "0228279": 1733,
    "0228283": 8908,
    "0228303": 5162,
    "0228366": 5803,
    "0228390": 2090,
    "0228405": 4195,
    "0228414": 1212,
    "0228416": 4743,
    "0228417": 1907,
    "LXC-102": 587,
    "LXC-104": 1733,
    "LXC-106": 5481,
}

PALETTE = {
    "carsi": "#B64342",
    "e32": "#0F4D92",
    "e33": "#3775BA",
    "e34": "#C9A227",
    "neutral": "#767676",
    "exact": "#4D4D4D",
    "band": "#F6F3E8",
}


def apply_publication_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "legend.fontsize": 6,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "legend.frameon": False,
            "figure.dpi": 150,
            "savefig.dpi": 600,
        }
    )


def save_pub(fig: plt.Figure, stem: Path, dpi: int = 600) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(f"{stem}.svg", bbox_inches="tight")
    fig.savefig(f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(f"{stem}.tiff", dpi=dpi, bbox_inches="tight")


def enrichment_curve(ranks: list[float], n_pool: int, n_pts: int = 400) -> tuple[np.ndarray, np.ndarray]:
    ranks = np.asarray(sorted(ranks), dtype=float)
    x = np.linspace(0, 50, n_pts)
    y = np.array([(ranks <= n_pool * xp / 100).sum() / len(ranks) * 100 for xp in x])
    return x, y


def hit_counts(ranks: list[float], n_pool: int) -> dict[str, int]:
    arr = np.asarray(ranks, dtype=float)
    return {
        "top10": int((arr <= n_pool * 0.10).sum()),
        "top25": int((arr <= n_pool * 0.25).sum()),
        "top50": int((arr <= n_pool * 0.50).sum()),
    }


def load_table() -> tuple[pd.DataFrame, dict]:
    with open(E34_JSON) as f:
        e34 = json.load(f)
    e32_by_id: dict[str, dict] = {}
    if E32_JSON.exists():
        with open(E32_JSON) as f:
            e32 = json.load(f)
        e32_by_id = {r["wetlab_id"]: r for r in e32["results"]}

    rows = []
    for r in e34["results"]:
        wid = r["wetlab_id"]
        e32r = e32_by_id.get(wid, {})
        rows.append(
            {
                "wetlab_id": wid,
                "molfactory_id": r["molfactory_id"],
                "tanimoto": float(r["tanimoto"]),
                "is_exact": float(r["tanimoto"]) >= 0.999,
                "glare_rank": int(r["glare_rank"]),
                "glare_score": float(r["glare_score"]),
                "glare_pct": float(r["glare_pct"]),
                "carsi_rank": int(r["carsi_rank"]),
                "e32_rank": int(e32r["glare_e32_rank"]) if e32r.get("glare_e32_rank") else np.nan,
                "e33_rank": int(E33_RANK_MAP.get(wid, np.nan)),
            }
        )
    df = pd.DataFrame(rows)
    # Stable display order by E34 rank (hero method)
    df = df.sort_values("glare_rank", kind="mergesort").reset_index(drop=True)
    meta = {
        "pool_size": int(e34["pool_size"]),
        "best_cycle": e34.get("best_cycle", 7),
        "mean_rank": float(e34["mean_rank"]),
        "median_rank": float(e34["median_rank"]),
        "best_rank": int(e34["best_rank"]),
        "worst_rank": int(e34["worst_rank"]),
        "mean_pct": float(e34["mean_pct"]),
        "top_10pct": int(e34["top_10pct"]),
        "top_25pct": int(e34["top_25pct"]),
        "top_50pct": int(e34["top_50pct"]),
    }
    return df, meta


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.08,
        1.06,
        label,
        transform=ax.transAxes,
        fontsize=8,
        fontweight="bold",
        va="bottom",
        ha="left",
    )


def build_figure(df: pd.DataFrame, meta: dict) -> plt.Figure:
    n_pool = meta["pool_size"]
    n = len(df)

    # Nature double-column ≈ 183 mm
    fig = plt.figure(figsize=(7.2, 4.6))
    gs = fig.add_gridspec(
        2,
        2,
        width_ratios=[1.55, 1.0],
        height_ratios=[1.15, 1.0],
        wspace=0.32,
        hspace=0.42,
        left=0.07,
        right=0.98,
        top=0.92,
        bottom=0.12,
    )
    ax_a = fig.add_subplot(gs[:, 0])  # hero spans both rows
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 1])

    # ── a: per-molecule ranks (E34 vs Carsi) ───────────────────────────────
    y = np.arange(n)
    h = 0.36
    carsi = df["carsi_rank"].to_numpy()
    e34 = df["glare_rank"].to_numpy()

    ax_a.barh(y + h / 2, carsi, height=h, color=PALETTE["carsi"], alpha=0.88, label="CarsiScore", zorder=3)
    ax_a.barh(y - h / 2, e34, height=h, color=PALETTE["e34"], alpha=0.95, label="GLARE E34", zorder=3)

    # exact-match markers
    for i, exact in enumerate(df["is_exact"]):
        if exact:
            xmax = max(carsi[i], e34[i])
            ax_a.plot(xmax + n_pool * 0.015, i, marker="*", markersize=7, color=PALETTE["exact"], zorder=4)

    ax_a.axvline(n_pool * 0.10, color=PALETTE["neutral"], ls=":", lw=0.7, zorder=1)
    ax_a.text(
        n_pool * 0.10 * 1.02,
        -0.55,
        "Top 10%",
        fontsize=5.5,
        color=PALETTE["neutral"],
        ha="left",
        va="bottom",
    )
    ax_a.axvline(meta["mean_rank"], color=PALETTE["e34"], ls="--", lw=0.9, alpha=0.7, zorder=2)
    ax_a.axvline(float(np.mean(carsi)), color=PALETTE["carsi"], ls="--", lw=0.8, alpha=0.55, zorder=2)

    ylabels = [
        f"{wid}  ({mf.replace('MolFactory_', 'MF')})"
        for wid, mf in zip(df["wetlab_id"], df["molfactory_id"])
    ]
    ax_a.set_yticks(y)
    ax_a.set_yticklabels(ylabels, fontsize=5.5)
    ax_a.set_xlabel("Rank in 10K pool (shorter = better)")
    ax_a.set_xlim(0, max(carsi.max(), e34.max()) * 1.08)
    ax_a.invert_yaxis()  # best E34 rank at top
    ax_a.legend(loc="lower left", fontsize=6, handlelength=1.2)
    panel_label(ax_a, "a")
    ax_a.set_title(
        f"E34 cycle_{meta['best_cycle']}  ·  mean #{meta['mean_rank']:.0f} "
        f"(top {meta['mean_pct']:.1f}%)  ·  ★ exact match",
        loc="left",
        fontsize=7,
        pad=6,
    )

    # ── b: enrichment ──────────────────────────────────────────────────────
    series = [
        ("CarsiScore", carsi.tolist(), PALETTE["carsi"]),
        ("GLARE E34", e34.tolist(), PALETTE["e34"]),
    ]
    if df["e32_rank"].notna().all():
        series.insert(1, ("GLARE E32", df["e32_rank"].tolist(), PALETTE["e32"]))

    for name, ranks, color in series:
        x, yv = enrichment_curve(ranks, n_pool)
        ax_b.plot(x, yv, color=color, lw=1.6, label=name, zorder=3)
    ax_b.plot([0, 50], [0, 50], ls="--", color=PALETTE["neutral"], lw=0.9, label="Random", zorder=1)
    ax_b.set_xlim(0, 50)
    ax_b.set_ylim(0, 105)
    ax_b.set_xlabel("Top % of ranked pool")
    ax_b.set_ylabel("% of 13 molecules found")
    ax_b.legend(loc="lower right", fontsize=5.5, handlelength=1.4)
    panel_label(ax_b, "b")

    # ── c: hit-rate summary ────────────────────────────────────────────────
    methods = []
    for name, ranks, color in series:
        hits = hit_counts(ranks, n_pool)
        methods.append((name, hits, color))

    cats = ["Top 10%", "Top 25%", "Top 50%"]
    keys = ["top10", "top25", "top50"]
    x = np.arange(len(cats))
    width = 0.22 if len(methods) == 3 else 0.28
    offsets = np.linspace(-(len(methods) - 1) / 2, (len(methods) - 1) / 2, len(methods)) * width

    for off, (name, hits, color) in zip(offsets, methods):
        vals = [hits[k] for k in keys]
        bars = ax_c.bar(x + off, vals, width=width * 0.92, color=color, alpha=0.92, zorder=3, label=name)
        for bar, v in zip(bars, vals):
            ax_c.text(
                bar.get_x() + bar.get_width() / 2,
                v + 0.15,
                str(v),
                ha="center",
                va="bottom",
                fontsize=5.5,
                color=PALETTE["exact"],
            )

    ax_c.axhline(13, color=PALETTE["neutral"], ls=":", lw=0.7, zorder=1)
    ax_c.set_xticks(x)
    ax_c.set_xticklabels(cats)
    ax_c.set_ylabel("Molecules retrieved (n=13)")
    ax_c.set_ylim(0, 14.5)
    ax_c.legend(loc="upper left", fontsize=5.5, ncol=1, handlelength=1.2)
    panel_label(ax_c, "c")

    return fig


def main() -> None:
    apply_publication_style()
    df, meta = load_table()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Source data for journal traceability
    src = df.copy()
    src["pool_size"] = meta["pool_size"]
    src_path = OUT_DIR / f"{STEM}_source_data.csv"
    src.to_csv(src_path, index=False)

    fig = build_figure(df, meta)
    stem = OUT_DIR / STEM
    save_pub(fig, stem)
    plt.close(fig)

    print(f"Saved: {stem}.{{svg,pdf,png,tiff}}")
    print(f"Source data: {src_path}")
    print(
        f"E34 mean=#{meta['mean_rank']:.0f} | "
        f"top10={meta['top_10pct']}/13 | top25={meta['top_25pct']}/13 | top50={meta['top_50pct']}/13"
    )


if __name__ == "__main__":
    main()
