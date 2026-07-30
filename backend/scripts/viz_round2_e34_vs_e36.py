#!/usr/bin/env python3
"""Round-2 dynamics molecules: E34 vs E36 ranking visualization.

Pool N≈11697, 19 query mols. Soft green = improved, soft red = worse.
★ Experimental actives: 0228300, 0228413, 0228423, 0228325, 0228274, LXC-201
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

JSON_PATH = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "round2_dynamics_ranking/e34_vs_e36_round2_dynamics.json"
)
OUT_DIR = JSON_PATH.parent / "figures_actives_highlight"

# User-specified experimental actives (short forms → full IDs in data)
ACTIVE_IDS = {
    "0228300",
    "0228413",  # 413
    "0228423",  # 423
    "0228325",  # 325
    "0228274",  # 274
    "LXC-201",
}
ACTIVE_ORDER = ["0228413", "LXC-201", "0228423", "0228325", "0228300", "0228274"]

C_E34 = "#C8D0D8"
C_IMPROVED = "#A8D5A2"
C_IMPROVED_DK = "#5FAF6B"
C_WORSE = "#E8A6A1"
C_WORSE_DK = "#D4736B"
C_NEG = "#B0B8C0"
C_EDGE = "#5A6570"
C_RANDOM = "#C5CCD3"
C_MEAN = "#6E7A86"
C_GREEN_BG = "#F0F7EF"
C_RED_BG = "#FBF0EF"
C_TOP10 = "#8FCB88"
C_STAR = "#3D8B4F"


def delta_color(delta: float, active: bool = False) -> str:
    if delta > 0:
        return C_IMPROVED_DK if active else C_IMPROVED
    if delta < 0:
        return C_WORSE_DK if active else C_WORSE
    return C_NEG


def short_label(mol_id: str) -> str:
    return mol_id.replace("0185078(1)", "0185078")


def load_data():
    with open(JSON_PATH) as f:
        doc = json.load(f)
    n_pool = int(doc["pool_size"])
    mols = []
    for r in doc["results"]:
        mid = r["mol_id"]
        mols.append(
            {
                "mol_id": mid,
                "label": short_label(mid),
                "is_active": mid in ACTIVE_IDS,
                "e34_rank": int(r["e34_rank"]),
                "e36_rank": int(r["e36_rank"]),
                "e34_pct": float(r["e34_pct"]),
                "e36_pct": float(r["e36_pct"]),
                "delta": int(r["delta"]),
                "e36_better": bool(r["e36_better"]),
            }
        )
    actives = [m for m in mols if m["is_active"]]
    inactives = [m for m in mols if not m["is_active"]]
    meta = {
        "pool_size": n_pool,
        "n_query": len(mols),
        "e34_mean": float(doc["e34_mean_rank"]),
        "e36_mean": float(doc["e36_mean_rank"]),
        "e36_better_count": int(doc["e36_better_count"]),
        "e34_better_count": int(doc["e34_better_count"]),
        "active_mean_e34": float(np.mean([m["e34_rank"] for m in actives])) if actives else np.nan,
        "active_mean_e36": float(np.mean([m["e36_rank"] for m in actives])) if actives else np.nan,
        "inactive_mean_e34": float(np.mean([m["e34_rank"] for m in inactives])) if inactives else np.nan,
        "inactive_mean_e36": float(np.mean([m["e36_rank"] for m in inactives])) if inactives else np.nan,
        "n_active_improved": sum(1 for m in actives if m["delta"] > 0),
        "n_active_worse": sum(1 for m in actives if m["delta"] < 0),
        "n_active": len(actives),
    }
    missing = ACTIVE_IDS - {m["mol_id"] for m in mols}
    if missing:
        raise SystemExit(f"Active IDs not in JSON: {missing}")
    return mols, meta


def setup_style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "legend.frameon": False,
        }
    )
    return plt


def save_fig(fig, plt, stem: str):
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=300)
    fig.savefig(OUT_DIR / f"{stem}.svg")
    plt.close(fig)
    print(f"  OK {stem}")


def write_csv(mols, meta):
    path = OUT_DIR / "round2_e34_vs_e36_source_data.csv"
    fields = [
        "mol_id", "is_active", "e34_rank", "e36_rank", "delta",
        "e34_pct", "e36_pct", "e36_better", "pool_size",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in mols:
            row = {k: m[k] for k in fields if k != "pool_size"}
            row["pool_size"] = meta["pool_size"]
            w.writerow(row)
    print(f"  OK {path.name}")


def active_box(mols, meta) -> str:
    by_id = {m["mol_id"]: m for m in mols}
    lines = []
    for wid in ACTIVE_ORDER:
        m = by_id[wid]
        mark = "↑" if m["delta"] > 0 else "↓"
        lines.append(f"★ {wid}: #{m['e34_rank']}→#{m['e36_rank']} (Δ{m['delta']:+d}) {mark}")
    lines.append(
        f"★ actives improved {meta['n_active_improved']}/{meta['n_active']}  ·  "
        f"all E36 better {meta['e36_better_count']}/{meta['n_query']}"
    )
    return "\n".join(lines)


def enrichment_xy(ranks, n_pool, xmax=50, n=300):
    ranks = np.asarray(sorted(ranks), dtype=float)
    x = np.linspace(0, xmax, n)
    y = np.array([(ranks <= n_pool * xp / 100).sum() / max(len(ranks), 1) * 100 for xp in x])
    return x, y


# ── fig1 ─────────────────────────────────────────────────────────────────────
def fig1_pre_post_bar(mols, meta, plt):
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    act = sorted([m for m in mols if m["is_active"]], key=lambda m: m["e36_rank"])
    ina = sorted([m for m in mols if not m["is_active"]], key=lambda m: m["e36_rank"])
    mols_s = act + ina
    x = np.arange(len(mols_s))
    w = 0.38

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar(x - w / 2, [m["e34_rank"] for m in mols_s], w, color=C_E34, zorder=3)
    ax.bar(
        x + w / 2, [m["e36_rank"] for m in mols_s], w,
        color=[delta_color(m["delta"], m["is_active"]) for m in mols_s], zorder=3,
        edgecolor=[C_EDGE if m["is_active"] else "white" for m in mols_s],
        lw=[0.9 if m["is_active"] else 0.2 for m in mols_s],
    )
    ax.axvline(len(act) - 0.5, color=C_RANDOM, ls="--", lw=0.9)

    for i, m in enumerate(mols_s):
        if not m["is_active"]:
            continue
        top = max(m["e34_rank"], m["e36_rank"])
        ax.plot(i, top + 250, marker="*", markersize=12, color=C_STAR, markeredgecolor=C_EDGE, zorder=5)
        ax.text(i, top + 550, f"Δ{m['delta']:+d}", ha="center", fontsize=6.5,
                color=delta_color(m["delta"], True), fontweight="bold")

    ax.axhline(meta["pool_size"] * 0.10, color=C_TOP10, ls=":", lw=0.9, alpha=0.75)
    labels = [f"{'★ ' if m['is_active'] else ''}{m['label']}" for m in mols_s]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.get_xticklabels()[i].set_color(C_STAR)
            ax.get_xticklabels()[i].set_fontweight("bold")

    ax.set_ylabel("Rank in pool (lower = better)")
    ax.set_title(
        f"Figure 1: Round-2 Dynamics — E34 vs E36 (N={meta['pool_size']})\n"
        f"E36 better {meta['e36_better_count']}/{meta['n_query']}  ·  "
        f"mean #{meta['e34_mean']:.0f}→#{meta['e36_mean']:.0f}  ·  "
        f"★ actives {meta['n_active_improved']}↑/{meta['n_active_worse']}↓"
    )
    ax.set_ylim(0, max(max(m["e34_rank"], m["e36_rank"]) for m in mols_s) * 1.12)
    ax.invert_yaxis()
    ax.legend(
        handles=[
            Patch(facecolor=C_E34, label="E34"),
            Patch(facecolor=C_IMPROVED, label="E36 improved"),
            Patch(facecolor=C_WORSE, label="E36 worse"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor=C_STAR, markersize=12, label="★ Active"),
        ],
        loc="lower right", fontsize=7,
    )
    ax.text(
        0.01, 0.02, active_box(mols, meta), transform=ax.transAxes, fontsize=6.2,
        family="monospace", va="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=C_GREEN_BG, edgecolor=C_IMPROVED_DK, alpha=0.95),
    )
    ax.text(len(act) / 2 - 0.5, 1.02, "★ Actives", transform=ax.get_xaxis_transform(),
            ha="center", fontsize=7.5, color=C_STAR, fontweight="bold")
    ax.text(len(act) + len(ina) / 2 - 0.5, 1.02, "Inactives", transform=ax.get_xaxis_transform(),
            ha="center", fontsize=7.5, color=C_MEAN)
    fig.tight_layout()
    save_fig(fig, plt, "fig1_pre_post_bar")


# ── fig2 ─────────────────────────────────────────────────────────────────────
def fig2_waterfall(mols, meta, plt):
    from matplotlib.patches import Patch

    mols_s = sorted(mols, key=lambda m: m["delta"], reverse=True)
    x = np.arange(len(mols_s))
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.axhspan(0, max(m["delta"] for m in mols_s) * 1.1, color=C_GREEN_BG, alpha=0.5, zorder=0)
    ax.axhspan(min(m["delta"] for m in mols_s) * 1.1, 0, color=C_RED_BG, alpha=0.5, zorder=0)
    ax.bar(
        x, [m["delta"] for m in mols_s],
        color=[delta_color(m["delta"], m["is_active"]) for m in mols_s],
        edgecolor=[C_EDGE if m["is_active"] else "white" for m in mols_s],
        lw=[1.0 if m["is_active"] else 0.2 for m in mols_s], zorder=3,
    )
    for i, m in enumerate(mols_s):
        va = "bottom" if m["delta"] >= 0 else "top"
        off = 200 if m["delta"] >= 0 else -200
        ax.text(
            i, m["delta"] + off,
            f"{'★' if m['is_active'] else ''}{m['delta']:+d}",
            ha="center", va=va, fontsize=6.5,
            color=delta_color(m["delta"], True),
            fontweight="bold" if m["is_active"] else "normal",
        )
        if m["is_active"]:
            ax.plot(i, m["delta"], marker="*", markersize=10, color=C_STAR, markeredgecolor=C_EDGE, zorder=5)

    ax.axhline(0, color=C_EDGE, lw=0.9)
    labels = [f"{'★ ' if m['is_active'] else ''}{m['label']}" for m in mols_s]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.get_xticklabels()[i].set_color(C_STAR)
            ax.get_xticklabels()[i].set_fontweight("bold")

    ax.set_ylabel("Δ Rank = E34 − E36  (↑ green = improved)")
    ax.set_title(
        f"Figure 2: Rank Change Waterfall  ·  E36 better {meta['e36_better_count']}/{meta['n_query']}  ·  "
        f"★ actives {meta['n_active_improved']}↑ {meta['n_active_worse']}↓"
    )
    ax.legend(
        handles=[
            Patch(facecolor=C_IMPROVED, label="Improved"),
            Patch(facecolor=C_WORSE, label="Worse"),
            Patch(facecolor=C_IMPROVED_DK, label="★ Active improved"),
            Patch(facecolor=C_WORSE_DK, label="★ Active worse"),
        ],
        loc="upper right", fontsize=7,
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig2_waterfall")


# ── fig3 ─────────────────────────────────────────────────────────────────────
def fig3_active_dumbbell(mols, meta, plt):
    by_id = {m["mol_id"]: m for m in mols}
    actives = [by_id[w] for w in ACTIVE_ORDER]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    y = np.arange(len(actives))

    for i, m in enumerate(actives):
        col = delta_color(m["delta"], True)
        ax.annotate(
            "",
            xy=(m["e36_rank"], i),
            xytext=(m["e34_rank"], i),
            arrowprops=dict(arrowstyle="-|>", color=col, lw=2.0, mutation_scale=12),
        )
        ax.scatter([m["e34_rank"]], [i], s=70, c=C_E34, edgecolors=C_EDGE, lw=0.5, zorder=3,
                   label="E34" if i == 0 else None)
        ax.scatter([m["e36_rank"]], [i], s=180, c=col, marker="*", edgecolors=C_EDGE, lw=0.5, zorder=4,
                   label="E36 ★" if i == 0 else None)
        side = "left" if m["e36_rank"] < m["e34_rank"] else "right"
        ax.text(
            m["e36_rank"] + (-80 if side == "left" else 80), i + 0.18,
            f"#{m['e34_rank']}→#{m['e36_rank']}  Δ{m['delta']:+d}",
            ha="right" if side == "left" else "left",
            va="bottom", fontsize=7.5, color=col, fontweight="bold",
        )

    ax.axvline(meta["pool_size"] * 0.10, color=C_TOP10, ls=":", lw=1.0)
    ax.text(meta["pool_size"] * 0.10, len(actives) - 0.35, "Top 10%", fontsize=7, color=C_IMPROVED_DK, ha="center")
    ax.set_yticks(y)
    ax.set_yticklabels([f"★ {m['mol_id']}" for m in actives], fontweight="bold")
    for i, m in enumerate(actives):
        ax.get_yticklabels()[i].set_color(delta_color(m["delta"], True))
    ax.set_xlabel(f"Rank in pool (N={meta['pool_size']}; left = better)")
    ax.set_xlim(0, max(m["e34_rank"] for m in actives) * 1.08)
    ax.invert_yaxis()
    ax.set_title(
        f"Figure 3: ★ 6 Experimental Actives — E34→E36\n"
        f"improved {meta['n_active_improved']}/{meta['n_active']}  ·  "
        f"mean #{meta['active_mean_e34']:.0f}→#{meta['active_mean_e36']:.0f}"
    )
    ax.legend(loc="lower right")
    fig.tight_layout()
    save_fig(fig, plt, "fig3_active_dumbbell")


# ── fig4 ─────────────────────────────────────────────────────────────────────
def fig4_enrichment(mols, meta, plt):
    n_pool = meta["pool_size"]
    fig, ax = plt.subplots(figsize=(7.5, 6))
    series = [
        ("E34 all 19", [m["e34_rank"] for m in mols], C_E34, "-", 1.6),
        ("E36 all 19", [m["e36_rank"] for m in mols], C_MEAN, "-", 1.7),
        ("E34 ★ actives", [m["e34_rank"] for m in mols if m["is_active"]], C_NEG, "--", 1.5),
        ("E36 ★ actives", [m["e36_rank"] for m in mols if m["is_active"]], C_IMPROVED_DK, "-", 2.4),
    ]
    for name, ranks, c, ls, lw in series:
        xv, yv = enrichment_xy(ranks, n_pool, xmax=100)
        ax.plot(xv, yv, color=c, ls=ls, lw=lw, label=name)
    ax.plot([0, 100], [0, 100], ls=":", color=C_RANDOM, lw=1.0, label="Random")

    for m in mols:
        if not m["is_active"]:
            continue
        xp = m["e36_rank"] / n_pool * 100
        ranks_a = sorted(x["e36_rank"] for x in mols if x["is_active"])
        yp = sum(1 for r in ranks_a if r <= m["e36_rank"]) / len(ranks_a) * 100
        ax.scatter([xp], [yp], marker="*", s=120, c=delta_color(m["delta"], True), edgecolors=C_EDGE, zorder=5)
        ax.annotate(m["mol_id"], (xp, yp), fontsize=6, color=delta_color(m["delta"], True),
                    fontweight="bold", xytext=(3, 3), textcoords="offset points")

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Top % of ranked pool")
    ax.set_ylabel("% of molecules found")
    ax.set_title("Figure 4: Enrichment — all 19 vs ★ 6 actives")
    ax.legend(loc="lower right", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig4_enrichment")


# ── fig5 ─────────────────────────────────────────────────────────────────────
def fig5_active_inactive_box(mols, meta, plt):
    from matplotlib.patches import Patch

    groups = [
        ([m["e34_rank"] for m in mols if m["is_active"]], C_E34, 1),
        ([m["e36_rank"] for m in mols if m["is_active"]], C_IMPROVED, 2),
        ([m["e34_rank"] for m in mols if not m["is_active"]], C_E34, 4),
        ([m["e36_rank"] for m in mols if not m["is_active"]], C_WORSE, 5),
    ]
    fig, ax = plt.subplots(figsize=(8, 5.8))
    data = [g[0] for g in groups]
    colors = [g[1] for g in groups]
    positions = [g[2] for g in groups]
    bp = ax.boxplot(
        data, positions=positions, widths=0.55, patch_artist=True,
        medianprops={"color": C_EDGE, "lw": 1.3},
    )
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.85)

    rng = np.random.default_rng(42)
    for pos, d, c, star in zip(positions, data, colors, [True, True, False, False]):
        jitter = rng.normal(0, 0.05, len(d))
        ax.scatter(np.full(len(d), pos) + jitter, d, c=c, s=110 if star else 28,
                   marker="*" if star else "o", edgecolors=C_EDGE, lw=0.35, zorder=5, alpha=0.95)

    ax.set_xticks([1.5, 4.5])
    ax.set_xticklabels([f"★ Active (n={meta['n_active']})", f"Inactive (n={meta['n_query'] - meta['n_active']})"])
    ax.set_ylabel("Rank (lower = better)")
    ax.invert_yaxis()
    ax.set_title(
        f"Figure 5: Active vs Inactive Rank Distributions\n"
        f"★ mean #{meta['active_mean_e34']:.0f}→#{meta['active_mean_e36']:.0f}  ·  "
        f"inactive #{meta['inactive_mean_e34']:.0f}→#{meta['inactive_mean_e36']:.0f}"
    )
    ax.legend(
        handles=[
            Patch(facecolor=C_E34, label="E34"),
            Patch(facecolor=C_IMPROVED, label="E36 ★ actives"),
            Patch(facecolor=C_WORSE, label="E36 inactives"),
        ],
        loc="upper right",
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig5_active_inactive_box")


# ── fig6 ─────────────────────────────────────────────────────────────────────
def fig6_summary_bars(mols, meta, plt):
    fig, ax = plt.subplots(figsize=(8, 5))
    cats = ["All-19\nmean", "★ Active\nmean", "Inactive\nmean"]
    e34_vals = [meta["e34_mean"], meta["active_mean_e34"], meta["inactive_mean_e34"]]
    e36_vals = [meta["e36_mean"], meta["active_mean_e36"], meta["inactive_mean_e36"]]
    # color E36 by whether mean improved (lower rank)
    e36_cols = [
        C_IMPROVED if e36_vals[i] < e34_vals[i] else C_WORSE
        for i in range(3)
    ]
    x = np.arange(3)
    w = 0.34
    b1 = ax.bar(x - w / 2, e34_vals, w, color=C_E34, label="E34")
    b2 = ax.bar(x + w / 2, e36_vals, w, color=e36_cols, label="E36", edgecolor=C_EDGE, lw=0.4)
    ax.plot([1 + w / 2], [meta["active_mean_e36"]], marker="*", markersize=14, color=C_STAR, zorder=5)

    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 120, f"{h:.0f}",
                    ha="center", va="bottom", fontsize=8, fontweight="bold", color=C_MEAN)

    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("Mean rank")
    ax.set_title(
        f"Figure 6: Mean Rank Summary  ·  E36 better on {meta['e36_better_count']}/{meta['n_query']} mols\n"
        f"(green = mean improved, red = mean worse)"
    )
    ax.legend(loc="upper right")
    ax.text(
        0.02, 0.98, active_box(mols, meta), transform=ax.transAxes, ha="left", va="top",
        fontsize=6.2, family="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=C_GREEN_BG, edgecolor=C_IMPROVED_DK, alpha=0.95),
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig6_summary_bars")


# ── fig7 ─────────────────────────────────────────────────────────────────────
def fig7_scatter(mols, meta, plt):
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(7.5, 7))
    mx = max(max(m["e34_rank"] for m in mols), max(m["e36_rank"] for m in mols)) * 1.05
    ax.plot([0, mx], [0, mx], ls="--", color=C_RANDOM, lw=1.0, zorder=1)

    for m in mols:
        c = delta_color(m["delta"], m["is_active"])
        if m["is_active"]:
            ax.scatter(m["e34_rank"], m["e36_rank"], marker="*", s=240, c=c,
                       edgecolors=C_EDGE, lw=0.55, zorder=5)
            ax.annotate(
                f"★ {m['mol_id']}\nΔ{m['delta']:+d}",
                (m["e34_rank"], m["e36_rank"]),
                fontsize=6.5, fontweight="bold", color=c,
                xytext=(5, 5), textcoords="offset points",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor=C_GREEN_BG if m["delta"] > 0 else C_RED_BG,
                    edgecolor=c, alpha=0.9,
                ),
            )
        else:
            ax.scatter(m["e34_rank"], m["e36_rank"], marker="o", s=45, c=c,
                       edgecolors=C_EDGE, lw=0.3, zorder=3, alpha=0.9)
            ax.annotate(m["label"], (m["e34_rank"], m["e36_rank"]), fontsize=5.5, alpha=0.7,
                        xytext=(2, 2), textcoords="offset points")

    ax.set_xlabel("E34 rank (pre-RL)")
    ax.set_ylabel("E36 rank (post-RL)")
    ax.set_title("Figure 7: E34 vs E36  ·  green=improved · red=worse · ★=active")
    ax.set_xlim(0, mx)
    ax.set_ylim(0, mx)
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.legend(
        handles=[
            Line2D([0], [0], marker="*", color="w", markerfacecolor=C_IMPROVED_DK, markersize=13, label="★ Active↑"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor=C_WORSE_DK, markersize=13, label="★ Active↓"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor=C_IMPROVED, markersize=8, label="Inactive↑"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor=C_WORSE, markersize=8, label="Inactive↓"),
        ],
        loc="lower left", fontsize=7,
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig7_scatter")


# ── fig8 ─────────────────────────────────────────────────────────────────────
def fig8_topn(mols, meta, plt):
    n_pool = meta["pool_size"]
    thresholds = [0.01, 0.05, 0.10, 0.25, 0.50]
    labels = ["Top 1%", "Top 5%", "Top 10%", "Top 25%", "Top 50%"]

    def counts(key, active_only=None):
        if active_only is True:
            subset = [m for m in mols if m["is_active"]]
        elif active_only is False:
            subset = [m for m in mols if not m["is_active"]]
        else:
            subset = mols
        return [sum(1 for m in subset if m[key] <= n_pool * t) for t in thresholds]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    x = np.arange(len(labels))
    w = 0.35

    for ax, active_only, title, n_ref in [
        (axes[0], None, f"A. All {meta['n_query']}", meta["n_query"]),
        (axes[1], True, f"B. ★ {meta['n_active']} Actives", meta["n_active"]),
    ]:
        a = counts("e34_rank", active_only)
        b = counts("e36_rank", active_only)
        ax.bar(x - w / 2, a, w, color=C_E34, label="E34")
        cols = [C_IMPROVED if bb >= aa else C_WORSE for aa, bb in zip(a, b)]
        ax.bar(x + w / 2, b, w, color=cols, label="E36")
        ax.plot(x, [n_ref * t for t in thresholds], ls="--", color=C_MEAN, alpha=0.45, marker="o", markersize=3)
        for i, (aa, bb) in enumerate(zip(a, b)):
            ax.text(i - w / 2, aa + 0.08, str(aa), ha="center", fontsize=7)
            ax.text(i + w / 2, bb + 0.08, str(bb), ha="center", fontsize=7, fontweight="bold",
                    color=C_IMPROVED_DK if bb >= aa else C_WORSE_DK)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylim(0, n_ref + 1.2)
        ax.set_title(title)
        ax.legend(fontsize=7, loc="upper left")
        if active_only:
            ax.set_facecolor(C_GREEN_BG)

    axes[0].set_ylabel("Molecules retrieved")
    fig.suptitle("Figure 8: Top-N Hits — green=gain · red=loss", fontsize=11, fontweight="bold", y=1.02)
    fig.tight_layout()
    save_fig(fig, plt, "fig8_topn")


# ── fig9 ─────────────────────────────────────────────────────────────────────
def fig9_top_improvers(mols, meta, plt):
    """Highlight biggest gains + biggest drops (incl. actives)."""
    top = sorted(mols, key=lambda m: m["delta"], reverse=True)[:6]
    bot = sorted(mols, key=lambda m: m["delta"])[:4]
    # unique preserve order
    seen = set()
    show = []
    for m in top + bot:
        if m["mol_id"] not in seen:
            seen.add(m["mol_id"])
            show.append(m)
    show = sorted(show, key=lambda m: m["delta"], reverse=True)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    y = np.arange(len(show))
    for i, m in enumerate(show):
        col = delta_color(m["delta"], m["is_active"])
        ax.barh(i, m["delta"], color=col, edgecolor=C_EDGE if m["is_active"] else "white",
                lw=0.8 if m["is_active"] else 0.2, zorder=3)
        ax.text(
            m["delta"] + (80 if m["delta"] >= 0 else -80), i,
            f"{'★ ' if m['is_active'] else ''}#{m['e34_rank']}→#{m['e36_rank']}  Δ{m['delta']:+d}",
            va="center", ha="left" if m["delta"] >= 0 else "right",
            fontsize=7.5, color=col, fontweight="bold" if m["is_active"] else "normal",
        )
    ax.axvline(0, color=C_EDGE, lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{'★ ' if m['is_active'] else ''}{m['label']}" for m in show])
    for i, m in enumerate(show):
        if m["is_active"]:
            ax.get_yticklabels()[i].set_color(C_STAR)
            ax.get_yticklabels()[i].set_fontweight("bold")
    ax.set_xlabel("Δ Rank (E34 − E36)")
    ax.set_title("Figure 9: Largest Gains (green) and Drops (red) — ★ = experimental active")
    ax.invert_yaxis()
    fig.tight_layout()
    save_fig(fig, plt, "fig9_extremes")


# ── fig10 ────────────────────────────────────────────────────────────────────
def fig10_dashboard(mols, meta, plt):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.5))
    by_id = {m["mol_id"]: m for m in mols}

    # A
    ax = axes[0, 0]
    act = sorted([m for m in mols if m["is_active"]], key=lambda m: m["e36_rank"])
    ina = sorted([m for m in mols if not m["is_active"]], key=lambda m: m["e36_rank"])
    mols_s = act + ina
    x = np.arange(len(mols_s))
    w = 0.38
    ax.bar(x - w / 2, [m["e34_rank"] for m in mols_s], w, color=C_E34)
    ax.bar(x + w / 2, [m["e36_rank"] for m in mols_s], w,
           color=[delta_color(m["delta"], m["is_active"]) for m in mols_s])
    ax.axvline(len(act) - 0.5, color=C_RANDOM, ls="--", lw=0.8)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.plot(i, max(m["e34_rank"], m["e36_rank"]) + 200, marker="*", color=C_STAR, markersize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{'★' if m['is_active'] else ''}{m['label']}" for m in mols_s],
                       rotation=45, ha="right", fontsize=5.5)
    ax.invert_yaxis()
    ax.set_ylabel("Rank")
    ax.set_title("A. Pre/post (E36 by Δ)")

    # B
    ax = axes[0, 1]
    mols_w = sorted(mols, key=lambda m: m["delta"], reverse=True)
    ax.bar(range(len(mols_w)), [m["delta"] for m in mols_w],
           color=[delta_color(m["delta"], m["is_active"]) for m in mols_w])
    ax.axhline(0, color=C_EDGE, lw=0.7)
    ax.set_xticks(range(len(mols_w)))
    ax.set_xticklabels([f"{'★' if m['is_active'] else ''}{m['label']}" for m in mols_w],
                       rotation=45, ha="right", fontsize=5.5)
    ax.set_ylabel("Δ Rank")
    ax.set_title("B. Waterfall")

    # C table
    ax = axes[1, 0]
    ax.axis("off")
    rows = [
        ["Metric", "E34", "E36", "Note"],
        ["All-19 mean", f"#{meta['e34_mean']:.0f}", f"#{meta['e36_mean']:.0f}",
         f"{meta['e36_better_count']}/{meta['n_query']} better"],
        ["★ Active mean", f"#{meta['active_mean_e34']:.0f}", f"#{meta['active_mean_e36']:.0f}",
         f"{meta['n_active_improved']}↑ {meta['n_active_worse']}↓"],
        ["Inactive mean", f"#{meta['inactive_mean_e34']:.0f}", f"#{meta['inactive_mean_e36']:.0f}", ""],
    ]
    for wid in ACTIVE_ORDER:
        m = by_id[wid]
        rows.append([f"★ {wid}", f"#{m['e34_rank']}", f"#{m['e36_rank']}", f"Δ{m['delta']:+d}"])
    table = ax.table(cellText=rows, cellLoc="center", loc="center",
                     colWidths=[0.26, 0.16, 0.16, 0.22])
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    for key, cell in table.get_celld().items():
        cell.set_linewidth(0.3)
        r, c = key
        if r == 0:
            cell.set_facecolor("#EEF1F4")
            cell.get_text().set_fontweight("bold")
        elif r == 2 or r >= 4:
            m = by_id[ACTIVE_ORDER[r - 4]] if r >= 4 else None
            if r == 2 or (m and m["delta"] > 0):
                cell.set_facecolor(C_GREEN_BG)
            elif m and m["delta"] < 0:
                cell.set_facecolor(C_RED_BG)
            if c == 0 and r >= 2:
                cell.get_text().set_fontweight("bold")
    ax.set_title("C. ★ Active detail", pad=8)

    # D enrichment compact
    ax = axes[1, 1]
    n_pool = meta["pool_size"]
    for name, ranks, c, ls, lw in [
        ("E34 all", [m["e34_rank"] for m in mols], C_E34, "-", 1.5),
        ("E36 all", [m["e36_rank"] for m in mols], C_MEAN, "-", 1.5),
        ("E36 ★", [m["e36_rank"] for m in mols if m["is_active"]], C_IMPROVED_DK, "-", 2.2),
    ]:
        xv, yv = enrichment_xy(ranks, n_pool, xmax=50)
        ax.plot(xv, yv, color=c, ls=ls, lw=lw, label=name)
    ax.plot([0, 50], [0, 50], ls=":", color=C_RANDOM, lw=1.0)
    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Top % pool")
    ax.set_ylabel("% found")
    ax.set_title("D. Enrichment (0–50%)")
    ax.legend(fontsize=7, loc="lower right")

    fig.suptitle(
        "Figure 10: Round-2 Dynamics E34→E36 Dashboard  ·  ★ experimental actives highlighted",
        fontsize=12, fontweight="bold", y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_fig(fig, plt, "fig10_dashboard")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mols, meta = load_data()
    plt = setup_style()

    print("=" * 64)
    print("  Round-2 dynamics E34 vs E36 (★ experimental actives)")
    print("=" * 64)
    print(active_box(mols, meta))
    print(f"  pool={meta['pool_size']}  E36 better {meta['e36_better_count']}/{meta['n_query']}")

    write_csv(mols, meta)
    fig1_pre_post_bar(mols, meta, plt)
    fig2_waterfall(mols, meta, plt)
    fig3_active_dumbbell(mols, meta, plt)
    fig4_enrichment(mols, meta, plt)
    fig5_active_inactive_box(mols, meta, plt)
    fig6_summary_bars(mols, meta, plt)
    fig7_scatter(mols, meta, plt)
    fig8_topn(mols, meta, plt)
    fig9_top_improvers(mols, meta, plt)
    fig10_dashboard(mols, meta, plt)

    print(f"\nAll figures -> {OUT_DIR}")


if __name__ == "__main__":
    main()
