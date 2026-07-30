#!/usr/bin/env python3
"""E34 → E36 RL progress: soft green/red semantics.

Green = improved (rank down / better). Red = worse (rank up / pushed back).
★ Actives: 0228414, 0228390, LXC-106
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

E36_JSON = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e36_full_patent_plus_wetlab/e36_ranking.json"
)
E34_JSON = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e34_full_403/wetlab_13_similar_ranking.json"
)
OUT_DIR = E36_JSON.parent / "figures"

ACTIVE_IDS = {"0228414", "0228390", "LXC-106"}
ACTIVE_ORDER = ["0228414", "0228390", "LXC-106"]

# Soft green / soft red semantic palette
C_E34 = "#C8D0D8"          # soft cool gray — pre baseline
C_IMPROVED = "#A8D5A2"     # soft green — better
C_IMPROVED_DK = "#5FAF6B"  # deeper green — ★ actives / emphasis
C_WORSE = "#E8A6A1"        # soft red — worse
C_WORSE_DK = "#D4736B"     # deeper soft red
C_NEG = "#B0B8C0"          # neutral gray
C_EDGE = "#5A6570"
C_RANDOM = "#C5CCD3"
C_MEAN = "#6E7A86"
C_GREEN_BG = "#F0F7EF"
C_RED_BG = "#FBF0EF"
C_TOP10 = "#8FCB88"


def delta_color(delta: float, active: bool = False) -> str:
    if delta > 0:
        return C_IMPROVED_DK if active else C_IMPROVED
    if delta < 0:
        return C_WORSE_DK if active else C_WORSE
    return C_NEG


def load_data():
    with open(E36_JSON) as f:
        e36_doc = json.load(f)
    with open(E34_JSON) as f:
        e34_doc = json.load(f)

    e34_map = {r["wetlab_id"]: r for r in e34_doc["results"]}
    n_pool = int(e36_doc["pool_size"])
    mols = []
    for r in e36_doc["e36"]["results"]:
        wid = r["wetlab_id"]
        e34r = e34_map[wid]
        e34_rank = int(e34r["glare_rank"])
        e36_rank = int(r["glare_rank"])
        is_active = bool(r.get("is_positive")) or wid in ACTIVE_IDS
        mols.append(
            {
                "wetlab_id": wid,
                "molfactory_id": r["molfactory_id"],
                "tanimoto": float(r["tanimoto"]),
                "is_active": is_active,
                "e34_rank": e34_rank,
                "e36_rank": e36_rank,
                "e34_pct": float(e34r["glare_pct"]),
                "e36_pct": float(r["glare_pct"]),
                "e34_score": float(e34r["glare_score"]),
                "e36_score": float(r["glare_score"]),
                "delta": e34_rank - e36_rank,  # >0 improved
            }
        )

    actives = [m for m in mols if m["is_active"]]
    negs = [m for m in mols if not m["is_active"]]
    meta = {
        "pool_size": n_pool,
        "e34_mean": float(np.mean([m["e34_rank"] for m in mols])),
        "e36_mean": float(e36_doc["e36"]["mean_rank"]),
        "e34_pos_mean": float(np.mean([m["e34_rank"] for m in actives])),
        "e36_pos_mean": float(e36_doc["e36"]["pos_mean_rank"]),
        "e34_neg_mean": float(np.mean([m["e34_rank"] for m in negs])),
        "e36_neg_mean": float(e36_doc["e36"]["neg_mean_rank"]),
        "n_improved": int(e36_doc["delta_vs_e34"]["n_improved"]),
        "n_worse": int(e36_doc["delta_vs_e34"]["n_worse"]),
        "n_active_improved": sum(1 for m in actives if m["delta"] > 0),
    }
    meta["e34_gap"] = meta["e34_neg_mean"] - meta["e34_pos_mean"]
    meta["e36_gap"] = meta["e36_neg_mean"] - meta["e36_pos_mean"]
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


def write_source_csv(mols, meta):
    path = OUT_DIR / "fig_e36_rl_progress_source_data.csv"
    fields = [
        "wetlab_id", "molfactory_id", "tanimoto", "is_active",
        "e34_rank", "e36_rank", "delta", "e34_pct", "e36_pct", "pool_size",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in mols:
            row = {k: m[k] for k in fields if k != "pool_size"}
            row["pool_size"] = meta["pool_size"]
            w.writerow(row)
    print(f"  OK {path.name}")


def active_box_text(mols, meta) -> str:
    by_id = {m["wetlab_id"]: m for m in mols}
    lines = []
    for wid in ACTIVE_ORDER:
        m = by_id[wid]
        lines.append(f"★ {wid}: #{m['e34_rank']}→#{m['e36_rank']} (Δ{m['delta']:+d})")
    lines.append(
        f"★ pos mean #{meta['e34_pos_mean']:.0f}→#{meta['e36_pos_mean']:.0f}  "
        f"gap {meta['e34_gap']:.0f}→{meta['e36_gap']:.0f}"
    )
    return "\n".join(lines)


def enrichment_xy(ranks, n_pool, xmax=50, n=300):
    ranks = np.asarray(sorted(ranks), dtype=float)
    x = np.linspace(0, xmax, n)
    y = np.array([(ranks <= n_pool * xp / 100).sum() / len(ranks) * 100 for xp in x])
    return x, y


def legend_change():
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    return [
        Patch(facecolor=C_E34, label="E34 (pre)"),
        Patch(facecolor=C_IMPROVED, label="Improved (green)"),
        Patch(facecolor=C_WORSE, label="Worse (red)"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=C_IMPROVED_DK,
               markeredgecolor=C_EDGE, markersize=12, label="★ Active"),
    ]


# ── fig1: E34 gray + E36 colored by Δ ────────────────────────────────────────
def fig1_pre_post_bar(mols, meta, plt):
    # Sort: actives first (by e36), then others by e36 — clearer narrative
    act = sorted([m for m in mols if m["is_active"]], key=lambda m: m["e36_rank"])
    neg = sorted([m for m in mols if not m["is_active"]], key=lambda m: m["e36_rank"])
    mols_s = act + neg
    x = np.arange(len(mols_s))
    w = 0.38

    fig, ax = plt.subplots(figsize=(12.5, 5.8))
    ax.bar(x - w / 2, [m["e34_rank"] for m in mols_s], w, color=C_E34, alpha=0.95, zorder=3, label="E34")
    e36_colors = [delta_color(m["delta"], m["is_active"]) for m in mols_s]
    ax.bar(x + w / 2, [m["e36_rank"] for m in mols_s], w, color=e36_colors, alpha=0.95, zorder=3,
           edgecolor=[C_EDGE if m["is_active"] else "white" for m in mols_s],
           lw=[0.9 if m["is_active"] else 0.2 for m in mols_s])

    # separator between actives and negs
    ax.axvline(2.5, color=C_RANDOM, ls="--", lw=0.9, alpha=0.8, zorder=1)

    for i, m in enumerate(mols_s):
        if not m["is_active"]:
            continue
        top = max(m["e34_rank"], m["e36_rank"])
        ax.plot(i, top * 0.02 + top + 120, marker="*", markersize=13,
                color=C_IMPROVED_DK, markeredgecolor=C_EDGE, zorder=5)
        ax.text(i, top + 320, f"Δ{m['delta']:+d}", ha="center", fontsize=7.5,
                color=C_IMPROVED_DK, fontweight="bold")

    ax.axhline(meta["pool_size"] * 0.10, color=C_TOP10, ls=":", lw=0.9, alpha=0.7)
    ax.text(len(mols_s) - 0.2, meta["pool_size"] * 0.10, "Top 10%", fontsize=6.5,
            color=C_IMPROVED_DK, ha="right", va="bottom")

    labels = [f"{'★ ' if m['is_active'] else ''}{m['wetlab_id']}" for m in mols_s]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.get_xticklabels()[i].set_color(C_IMPROVED_DK)
            ax.get_xticklabels()[i].set_fontweight("bold")

    ax.set_ylabel("GLARE rank (lower = better)")
    ax.set_title(
        "Figure 1: E34→E36 Ranking  ·  E36 bar = green if improved, red if worse\n"
        f"★ Actives all improved · pos mean #{meta['e34_pos_mean']:.0f}→#{meta['e36_pos_mean']:.0f}"
    )
    ymax = max(max(m["e34_rank"], m["e36_rank"]) for m in mols_s) * 1.12
    ax.set_ylim(0, ymax)
    ax.invert_yaxis()
    ax.legend(handles=legend_change(), loc="lower right", fontsize=7)
    ax.text(
        0.01, 0.02, active_box_text(mols, meta), transform=ax.transAxes, fontsize=6.8,
        family="monospace", va="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=C_GREEN_BG, edgecolor=C_IMPROVED_DK, alpha=0.95),
    )
    # group labels
    ax.text(1.0, 1.02, "★ Actives", transform=ax.get_xaxis_transform(), ha="center",
            fontsize=7.5, color=C_IMPROVED_DK, fontweight="bold")
    ax.text(7.5, 1.02, "Negatives", transform=ax.get_xaxis_transform(), ha="center",
            fontsize=7.5, color=C_MEAN)
    fig.tight_layout()
    save_fig(fig, plt, "fig1_pre_post_bar")


# ── fig2 ─────────────────────────────────────────────────────────────────────
def fig2_waterfall(mols, meta, plt):
    from matplotlib.patches import Patch

    mols_s = sorted(mols, key=lambda m: m["delta"], reverse=True)
    x = np.arange(len(mols_s))
    colors = [delta_color(m["delta"], m["is_active"]) for m in mols_s]

    fig, ax = plt.subplots(figsize=(12.5, 5.8))
    ax.bar(
        x, [m["delta"] for m in mols_s], color=colors, alpha=0.95, zorder=3,
        edgecolor=[C_EDGE if m["is_active"] else "white" for m in mols_s],
        lw=[1.0 if m["is_active"] else 0.2 for m in mols_s],
    )
    for i, m in enumerate(mols_s):
        va = "bottom" if m["delta"] >= 0 else "top"
        off = 150 if m["delta"] >= 0 else -150
        ax.text(
            i, m["delta"] + off,
            f"{'★' if m['is_active'] else ''}{m['delta']:+d}",
            ha="center", va=va, fontsize=7,
            color=delta_color(m["delta"], True),
            fontweight="bold" if m["is_active"] else "normal",
        )
        if m["is_active"]:
            ax.plot(i, m["delta"], marker="*", markersize=11, color=C_IMPROVED_DK,
                    markeredgecolor=C_EDGE, zorder=5)

    ax.axhline(0, color=C_EDGE, lw=0.9)
    # soft background bands
    ax.axhspan(0, max(m["delta"] for m in mols_s) * 1.15, color=C_GREEN_BG, alpha=0.45, zorder=0)
    ax.axhspan(min(m["delta"] for m in mols_s) * 1.15, 0, color=C_RED_BG, alpha=0.45, zorder=0)

    labels = [f"{'★ ' if m['is_active'] else ''}{m['wetlab_id']}" for m in mols_s]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.get_xticklabels()[i].set_color(C_IMPROVED_DK)
            ax.get_xticklabels()[i].set_fontweight("bold")

    ax.set_ylabel("Δ Rank = E34 − E36  (↑ green = improved)")
    ax.set_title(
        f"Figure 2: Rank Change — green improved / red worse  ·  "
        f"★ {meta['n_active_improved']}/3 actives up · overall {meta['n_improved']}↑ {meta['n_worse']}↓"
    )
    ax.legend(
        handles=[
            Patch(facecolor=C_IMPROVED, label="Improved"),
            Patch(facecolor=C_WORSE, label="Worse"),
            Patch(facecolor=C_IMPROVED_DK, label="★ Active improved"),
        ],
        loc="upper right",
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig2_waterfall")


# ── fig3 ─────────────────────────────────────────────────────────────────────
def fig3_active_focus(mols, meta, plt):
    actives = [next(m for m in mols if m["wetlab_id"] == wid) for wid in ACTIVE_ORDER]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    y = np.arange(len(actives))

    for i, m in enumerate(actives):
        ax.annotate(
            "",
            xy=(m["e36_rank"], i),
            xytext=(m["e34_rank"], i),
            arrowprops=dict(arrowstyle="-|>", color=C_IMPROVED_DK, lw=2.0, mutation_scale=12),
        )
        ax.scatter([m["e34_rank"]], [i], s=80, c=C_E34, edgecolors=C_EDGE, lw=0.6, zorder=3,
                   label="E34" if i == 0 else None)
        ax.scatter([m["e36_rank"]], [i], s=200, c=C_IMPROVED_DK, marker="*", edgecolors=C_EDGE,
                   lw=0.6, zorder=4, label="E36 ★" if i == 0 else None)
        ax.text(
            m["e36_rank"] - 40, i + 0.22,
            f"#{m['e34_rank']}→#{m['e36_rank']}  Δ{m['delta']:+d}",
            ha="right", va="bottom", fontsize=8, color=C_IMPROVED_DK, fontweight="bold",
        )

    ax.axvline(meta["pool_size"] * 0.10, color=C_TOP10, ls=":", lw=1.0, alpha=0.8)
    ax.text(meta["pool_size"] * 0.10, 2.45, "Top 10%", fontsize=7, color=C_IMPROVED_DK, ha="center")
    ax.set_yticks(y)
    ax.set_yticklabels([f"★ {m['wetlab_id']}" for m in actives], fontweight="bold", color=C_IMPROVED_DK)
    ax.set_xlabel("GLARE rank in 10K pool (left = better)")
    ax.set_xlim(0, max(m["e34_rank"] for m in actives) * 1.12)
    ax.set_ylim(-0.6, 2.7)
    ax.invert_yaxis()
    ax.set_facecolor(C_GREEN_BG)
    ax.set_title(
        f"Figure 3: ★ Three Actives Move Forward (E34→E36)\n"
        f"pos mean #{meta['e34_pos_mean']:.0f} → #{meta['e36_pos_mean']:.0f}"
    )
    ax.legend(loc="lower right")
    fig.tight_layout()
    save_fig(fig, plt, "fig3_active_focus")


# ── fig4 ─────────────────────────────────────────────────────────────────────
def fig4_enrichment(mols, meta, plt):
    n_pool = meta["pool_size"]
    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    series = [
        ("E34 all 13", [m["e34_rank"] for m in mols], C_E34, "-", 1.7),
        ("E36 all 13", [m["e36_rank"] for m in mols], C_WORSE_DK, "-", 1.6),  # overall worse (negs)
        ("E34 ★ actives", [m["e34_rank"] for m in mols if m["is_active"]], C_NEG, "--", 1.5),
        ("E36 ★ actives", [m["e36_rank"] for m in mols if m["is_active"]], C_IMPROVED_DK, "-", 2.5),
    ]
    for name, ranks, c, ls, lw in series:
        x, y = enrichment_xy(ranks, n_pool)
        ax.plot(x, y, color=c, ls=ls, lw=lw, label=name, zorder=3)
    ax.plot([0, 50], [0, 50], ls=":", color=C_RANDOM, lw=1.1, label="Random", zorder=1)

    for m in mols:
        if not m["is_active"]:
            continue
        xp = m["e36_rank"] / n_pool * 100
        ranks_act = sorted(x["e36_rank"] for x in mols if x["is_active"])
        yp = sum(1 for r in ranks_act if r <= m["e36_rank"]) / 3 * 100
        ax.scatter([xp], [yp], marker="*", s=150, c=C_IMPROVED_DK, edgecolors=C_EDGE, zorder=5)
        ax.annotate(m["wetlab_id"], (xp, yp), fontsize=6.5, color=C_IMPROVED_DK, fontweight="bold",
                    xytext=(4, 4), textcoords="offset points")

    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Top % of ranked pool")
    ax.set_ylabel("% of molecules found")
    ax.set_title("Figure 4: Enrichment — ★ Actives (green) rise; all-13 dips as negs drop")
    ax.legend(loc="lower right", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig4_enrichment")


# ── fig5 ─────────────────────────────────────────────────────────────────────
def fig5_pos_neg_box(mols, meta, plt):
    from matplotlib.patches import Patch

    pos_e34 = [m["e34_rank"] for m in mols if m["is_active"]]
    pos_e36 = [m["e36_rank"] for m in mols if m["is_active"]]
    neg_e34 = [m["e34_rank"] for m in mols if not m["is_active"]]
    neg_e36 = [m["e36_rank"] for m in mols if not m["is_active"]]

    fig, ax = plt.subplots(figsize=(7.8, 5.8))
    positions = [1, 2, 4, 5]
    data = [pos_e34, pos_e36, neg_e34, neg_e36]
    # E34 gray; E36 pos green; E36 neg soft red
    colors = [C_E34, C_IMPROVED, C_E34, C_WORSE]
    bp = ax.boxplot(
        data, positions=positions, widths=0.55, patch_artist=True,
        medianprops={"color": C_EDGE, "lw": 1.4},
        flierprops={"marker": "o", "markersize": 4, "alpha": 0.5},
    )
    for patch, c in zip(bp["boxes"], colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.85)

    rng = np.random.default_rng(42)
    for pos, d, c, mark_star in zip(positions, data, colors, [True, True, False, False]):
        jitter = rng.normal(0, 0.05, len(d))
        ax.scatter(
            np.full(len(d), pos) + jitter, d, c=c,
            s=140 if mark_star else 32,
            marker="*" if mark_star else "o",
            edgecolors=C_EDGE, lw=0.4, zorder=5, alpha=0.95,
        )

    ax.set_xticks([1.5, 4.5])
    ax.set_xticklabels(["★ Active (n=3)", "Negative (n=10)"])
    ax.set_ylabel("GLARE rank (lower = better)")
    ax.invert_yaxis()
    ax.set_title(
        f"Figure 5: Separation — actives shift green (better), negatives shift red (worse)\n"
        f"gap {meta['e34_gap']:.0f} → {meta['e36_gap']:.0f}"
    )
    ax.legend(
        handles=[
            Patch(facecolor=C_E34, label="E34"),
            Patch(facecolor=C_IMPROVED, label="E36 ★ actives (↑)"),
            Patch(facecolor=C_WORSE, label="E36 negatives (↓)"),
        ],
        loc="upper right",
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig5_pos_neg_box")


# ── fig6 ─────────────────────────────────────────────────────────────────────
def fig6_separation(mols, meta, plt):
    fig, ax = plt.subplots(figsize=(7.8, 5.0))
    cats = ["★ Pos mean\n(lower better)", "Neg mean\n(higher = pushed)", "Gap\n(neg − pos)"]
    e34_vals = [meta["e34_pos_mean"], meta["e34_neg_mean"], meta["e34_gap"]]
    e36_vals = [meta["e36_pos_mean"], meta["e36_neg_mean"], meta["e36_gap"]]
    # E36 colors: pos green, neg red, gap green (larger gap = desired)
    e36_colors = [C_IMPROVED, C_WORSE, C_IMPROVED_DK]
    x = np.arange(len(cats))
    w = 0.34
    b1 = ax.bar(x - w / 2, e34_vals, w, color=C_E34, alpha=0.95, label="E34", zorder=3)
    b2 = ax.bar(x + w / 2, e36_vals, w, color=e36_colors, alpha=0.95, label="E36", zorder=3,
                edgecolor=C_EDGE, lw=0.5)
    ax.plot(x[0] + w / 2, e36_vals[0], marker="*", markersize=14, color=C_IMPROVED_DK,
            markeredgecolor=C_EDGE, zorder=5)

    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 60, f"{h:.0f}",
                    ha="center", va="bottom", fontsize=8, fontweight="bold", color=C_MEAN)

    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("Rank / gap")
    ax.set_title("Figure 6: Pos↓ (green) · Neg↑ (red) · Gap widens")
    ax.legend(loc="upper left")
    ax.text(
        0.98, 0.97, active_box_text(mols, meta), transform=ax.transAxes, ha="right", va="top",
        fontsize=6.8, family="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=C_GREEN_BG, edgecolor=C_IMPROVED_DK, alpha=0.95),
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig6_separation")


# ── fig7 ─────────────────────────────────────────────────────────────────────
def fig7_scatter(mols, meta, plt):
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(7.2, 6.8))
    mx = max(max(m["e34_rank"] for m in mols), max(m["e36_rank"] for m in mols)) * 1.05
    ax.plot([0, mx], [0, mx], ls="--", color=C_RANDOM, lw=1.0, zorder=1)

    for m in mols:
        c = delta_color(m["delta"], m["is_active"])
        if m["is_active"]:
            ax.scatter(m["e34_rank"], m["e36_rank"], marker="*", s=260, c=c,
                       edgecolors=C_EDGE, lw=0.6, zorder=5)
            ax.annotate(
                f"★ {m['wetlab_id']}\nΔ{m['delta']:+d}",
                (m["e34_rank"], m["e36_rank"]),
                fontsize=7, fontweight="bold", color=C_IMPROVED_DK,
                xytext=(6, 6), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=C_GREEN_BG, edgecolor=C_IMPROVED_DK, alpha=0.9),
            )
        else:
            ax.scatter(m["e34_rank"], m["e36_rank"], marker="o", s=50, c=c,
                       edgecolors=C_EDGE, lw=0.3, zorder=3, alpha=0.9)
            ax.annotate(m["wetlab_id"], (m["e34_rank"], m["e36_rank"]), fontsize=6, alpha=0.75,
                        xytext=(3, 3), textcoords="offset points")

    ax.set_xlabel("E34 rank (pre)")
    ax.set_ylabel("E36 rank (post)")
    ax.set_title("Figure 7: Green = improved (below identity) · Red = worse")
    ax.set_xlim(0, mx)
    ax.set_ylim(0, mx)
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.legend(
        handles=[
            Line2D([0], [0], marker="*", color="w", markerfacecolor=C_IMPROVED_DK, markersize=14, label="★ Active↑"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor=C_IMPROVED, markersize=8, label="Improved"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor=C_WORSE, markersize=8, label="Worse"),
        ],
        loc="lower left",
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig7_scatter")


# ── fig8 ─────────────────────────────────────────────────────────────────────
def fig8_ecdf(mols, meta, plt):
    n_pool = meta["pool_size"]
    fig, ax = plt.subplots(figsize=(7.2, 5.8))

    def plot_ecdf(ranks, **kwargs):
        pcts = sorted(r / n_pool * 100 for r in ranks)
        y = np.arange(1, len(pcts) + 1) / len(pcts)
        ax.step(pcts, y, where="post", **kwargs)
        return pcts, y

    plot_ecdf([m["e34_rank"] for m in mols], color=C_E34, lw=1.8, label="E34 all 13")
    plot_ecdf([m["e36_rank"] for m in mols], color=C_WORSE_DK, lw=1.6, label="E36 all 13 (negs down)")
    plot_ecdf([m["e34_rank"] for m in mols if m["is_active"]], color=C_NEG, lw=1.4, ls="--", label="E34 ★")
    pcts, y = plot_ecdf(
        [m["e36_rank"] for m in mols if m["is_active"]],
        color=C_IMPROVED_DK, lw=2.5, label="E36 ★ (improved)",
    )

    act_sorted = sorted([m for m in mols if m["is_active"]], key=lambda m: m["e36_rank"])
    for p, yi, m in zip(pcts, y, act_sorted):
        ax.scatter([p], [yi], marker="*", s=150, c=C_IMPROVED_DK, edgecolors=C_EDGE, zorder=5)
        ax.annotate(m["wetlab_id"], (p, yi), fontsize=6.5, color=C_IMPROVED_DK, fontweight="bold",
                    xytext=(4, 3), textcoords="offset points")

    ax.plot([0, 100], [0, 1], ls=":", color=C_RANDOM, lw=1.0, label="Random")
    ax.set_xlim(0, 90)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Rank percentile in pool (left = better)")
    ax.set_ylabel("Cumulative fraction")
    ax.set_title("Figure 8: ECDF — ★ Actives shift left (green)")
    ax.legend(loc="lower right", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig8_ecdf")


# ── fig9 ─────────────────────────────────────────────────────────────────────
def fig9_topn_actives(mols, meta, plt):
    n_pool = meta["pool_size"]
    thresholds = [0.01, 0.05, 0.10, 0.25, 0.50]
    labels = ["Top 1%", "Top 5%", "Top 10%", "Top 25%", "Top 50%"]

    def counts(rank_key, active_only=False):
        subset = [m for m in mols if (m["is_active"] if active_only else True)]
        return [sum(1 for m in subset if m[rank_key] <= n_pool * t) for t in thresholds]

    e34_all, e36_all = counts("e34_rank", False), counts("e36_rank", False)
    e34_act, e36_act = counts("e34_rank", True), counts("e36_rank", True)

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8))
    x = np.arange(len(labels))
    w = 0.35

    ax = axes[0]
    ax.bar(x - w / 2, e34_all, w, color=C_E34, label="E34", zorder=3)
    # all-13: color E36 by whether count increased
    cols = [C_IMPROVED if b >= a else C_WORSE for a, b in zip(e34_all, e36_all)]
    ax.bar(x + w / 2, e36_all, w, color=cols, label="E36", zorder=3)
    ax.plot(x, [13 * t for t in thresholds], ls="--", color=C_MEAN, alpha=0.45, marker="o", markersize=3, label="Random")
    for i, (a, b) in enumerate(zip(e34_all, e36_all)):
        ax.text(i - w / 2, a + 0.12, str(a), ha="center", fontsize=7)
        ax.text(i + w / 2, b + 0.12, str(b), ha="center", fontsize=7, fontweight="bold",
                color=C_IMPROVED_DK if b >= a else C_WORSE_DK)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Molecules retrieved")
    ax.set_ylim(0, 14.5)
    ax.set_title("A. All 13 (green=gain, red=loss)")
    ax.legend(fontsize=7, loc="upper left")

    ax = axes[1]
    ax.bar(x - w / 2, e34_act, w, color=C_E34, label="E34 ★", zorder=3)
    ax.bar(x + w / 2, e36_act, w, color=C_IMPROVED, label="E36 ★", zorder=3, edgecolor=C_IMPROVED_DK, lw=0.6)
    ax.plot(x, [3 * t for t in thresholds], ls="--", color=C_MEAN, alpha=0.45, marker="o", markersize=3, label="Random")
    for i, (a, b) in enumerate(zip(e34_act, e36_act)):
        ax.text(i - w / 2, a + 0.06, str(a), ha="center", fontsize=7)
        ax.text(i + w / 2, b + 0.06, str(b), ha="center", fontsize=7, fontweight="bold", color=C_IMPROVED_DK)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(0, 3.6)
    ax.set_title("B. ★ 3 Actives (all gains in green)")
    ax.legend(fontsize=7, loc="upper left")
    ax.set_facecolor(C_GREEN_BG)

    fig.suptitle("Figure 9: Top-N Hits — green gain / red loss", fontsize=11, fontweight="bold", y=1.01)
    fig.tight_layout()
    save_fig(fig, plt, "fig9_topn_actives")


# ── fig10 ────────────────────────────────────────────────────────────────────
def fig10_dashboard(mols, meta, plt):
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.2))
    by_id = {m["wetlab_id"]: m for m in mols}

    # A
    ax = axes[0, 0]
    act = sorted([m for m in mols if m["is_active"]], key=lambda m: m["e36_rank"])
    neg = sorted([m for m in mols if not m["is_active"]], key=lambda m: m["e36_rank"])
    mols_s = act + neg
    x = np.arange(len(mols_s))
    w = 0.38
    ax.bar(x - w / 2, [m["e34_rank"] for m in mols_s], w, color=C_E34, label="E34")
    ax.bar(x + w / 2, [m["e36_rank"] for m in mols_s], w,
           color=[delta_color(m["delta"], m["is_active"]) for m in mols_s], label="E36")
    ax.axvline(2.5, color=C_RANDOM, ls="--", lw=0.8)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.plot(i, max(m["e34_rank"], m["e36_rank"]) + 180, marker="*", color=C_IMPROVED_DK, markersize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{'★' if m['is_active'] else ''}{m['wetlab_id']}" for m in mols_s],
                       rotation=40, ha="right", fontsize=6.5)
    ax.invert_yaxis()
    ax.set_ylabel("Rank")
    ax.set_title("A. Pre/post (E36 colored by Δ)")
    ax.legend(fontsize=7, loc="lower right")

    # B
    ax = axes[0, 1]
    mols_w = sorted(mols, key=lambda m: m["delta"], reverse=True)
    ax.bar(range(len(mols_w)), [m["delta"] for m in mols_w],
           color=[delta_color(m["delta"], m["is_active"]) for m in mols_w], alpha=0.95)
    ax.axhline(0, color=C_EDGE, lw=0.7)
    ax.axhspan(0, max(m["delta"] for m in mols_w) * 1.1, color=C_GREEN_BG, alpha=0.35, zorder=0)
    ax.axhspan(min(m["delta"] for m in mols_w) * 1.1, 0, color=C_RED_BG, alpha=0.35, zorder=0)
    ax.set_xticks(range(len(mols_w)))
    ax.set_xticklabels([f"{'★' if m['is_active'] else ''}{m['wetlab_id']}" for m in mols_w],
                       rotation=40, ha="right", fontsize=6.5)
    ax.set_ylabel("Δ Rank")
    ax.set_title("B. Waterfall (green↑ / red↓)")

    # C
    ax = axes[1, 0]
    ax.axis("off")
    rows = [
        ["Metric", "E34", "E36", "Δ"],
        ["★ Pos mean", f"#{meta['e34_pos_mean']:.0f}", f"#{meta['e36_pos_mean']:.0f}",
         f"{meta['e34_pos_mean'] - meta['e36_pos_mean']:+.0f}"],
        ["Neg mean", f"#{meta['e34_neg_mean']:.0f}", f"#{meta['e36_neg_mean']:.0f}",
         f"{meta['e34_neg_mean'] - meta['e36_neg_mean']:+.0f}"],
        ["Gap (neg−pos)", f"{meta['e34_gap']:.0f}", f"{meta['e36_gap']:.0f}",
         f"{meta['e36_gap'] - meta['e34_gap']:+.0f}"],
        ["All-13 mean", f"#{meta['e34_mean']:.0f}", f"#{meta['e36_mean']:.0f}",
         f"{meta['e34_mean'] - meta['e36_mean']:+.0f}"],
        ["Improved / Worse", "", "", f"{meta['n_improved']} / {meta['n_worse']}"],
    ]
    for wid in ACTIVE_ORDER:
        m = by_id[wid]
        rows.append([f"★ {wid}", f"#{m['e34_rank']}", f"#{m['e36_rank']}", f"{m['delta']:+d}"])
    table = ax.table(cellText=rows, cellLoc="center", loc="center", colWidths=[0.28, 0.18, 0.18, 0.16])
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    for key, cell in table.get_celld().items():
        cell.set_linewidth(0.3)
        r, c = key
        if r == 0:
            cell.set_facecolor("#EEF1F4")
            cell.get_text().set_fontweight("bold")
        elif r in (1, 6, 7, 8):
            cell.set_facecolor(C_GREEN_BG)
            if c == 0:
                cell.get_text().set_color(C_IMPROVED_DK)
                cell.get_text().set_fontweight("bold")
        elif r == 2:
            cell.set_facecolor(C_RED_BG)
    ax.set_title("C. ★ Active detail (green rows)", pad=10)

    # D
    ax = axes[1, 1]
    cats = ["★ Pos", "Neg", "Gap"]
    xv = np.arange(3)
    w = 0.34
    ax.bar(xv - w / 2, [meta["e34_pos_mean"], meta["e34_neg_mean"], meta["e34_gap"]], w, color=C_E34, label="E34")
    ax.bar(xv + w / 2, [meta["e36_pos_mean"], meta["e36_neg_mean"], meta["e36_gap"]], w,
           color=[C_IMPROVED, C_WORSE, C_IMPROVED_DK], label="E36")
    ax.plot([w / 2], [meta["e36_pos_mean"]], marker="*", markersize=13, color=C_IMPROVED_DK, zorder=5)
    ax.set_xticks(xv)
    ax.set_xticklabels(cats)
    ax.set_ylabel("Rank / gap")
    ax.set_title("D. Separation (green pos / red neg)")
    ax.legend(fontsize=7)

    fig.suptitle(
        "Figure 10: E34→E36 RL Progress  ·  soft green = better · soft red = worse",
        fontsize=12, fontweight="bold", y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_fig(fig, plt, "fig10_dashboard")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mols, meta = load_data()
    plt = setup_style()

    missing = ACTIVE_IDS - {m["wetlab_id"] for m in mols if m["is_active"]}
    if missing:
        raise SystemExit(f"Active IDs missing: {missing}")

    print("=" * 64)
    print("  E34→E36 RL progress (soft green/red)")
    print("=" * 64)
    print(active_box_text(mols, meta))

    write_source_csv(mols, meta)
    fig1_pre_post_bar(mols, meta, plt)
    fig2_waterfall(mols, meta, plt)
    fig3_active_focus(mols, meta, plt)
    fig4_enrichment(mols, meta, plt)
    fig5_pos_neg_box(mols, meta, plt)
    fig6_separation(mols, meta, plt)
    fig7_scatter(mols, meta, plt)
    fig8_ecdf(mols, meta, plt)
    fig9_topn_actives(mols, meta, plt)
    fig10_dashboard(mols, meta, plt)

    print(f"\nAll figures -> {OUT_DIR}")


if __name__ == "__main__":
    main()
