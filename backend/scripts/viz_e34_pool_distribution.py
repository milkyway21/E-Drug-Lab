#!/usr/bin/env python3
"""E34 Wetlab-13: position & distribution within the ~10K MolFactory pool.

E34 only (no E32/E33/Carsi). Focus: where the 13 wet-lab-similar molecules
sit in the E34-ranked pool, with special ★ highlighting of the 3 wet-lab
actives: 0228414, 0228390, LXC-106.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

E34_JSON = Path(
    "/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation/"
    "glare_e34_full_403/wetlab_13_similar_ranking.json"
)
OUT_DIR = E34_JSON.parent / "figures"

# Wet-lab actives (user: 0228414, 0228390/0228490, LXC-106) — JSON id is 0228390
ACTIVE_IDS = {"0228414", "0228390", "LXC-106"}
ACTIVE_ORDER = ["0228414", "0228390", "LXC-106"]

C_HERO = "#C9A227"
C_TOP10 = "#2E9E44"
C_TOP25 = "#E0B84A"
C_TOP50 = "#E28E2C"
C_OTHER = "#B64342"
C_ACTIVE = "#C51610"     # star / active emphasis
C_SIM = "#6B7280"        # similar non-actives
C_EDGE = "#272727"
C_RANDOM = "#9A9A9A"
C_MEAN = "#4D4D4D"
C_ACTIVE_BG = "#FDE8E6"


def load_data():
    with open(E34_JSON) as f:
        data = json.load(f)
    n_pool = int(data["pool_size"])
    mols = []
    for r in data["results"]:
        wid = r["wetlab_id"]
        tan = float(r["tanimoto"])
        rank = int(r["glare_rank"])
        pct = float(r["glare_pct"])
        mols.append(
            {
                "wetlab_id": wid,
                "molfactory_id": r["molfactory_id"],
                "tanimoto": tan,
                "glare_rank": rank,
                "glare_score": float(r["glare_score"]),
                "glare_pct": pct,
                "is_active": wid in ACTIVE_IDS,
                "zone": zone_of(rank, n_pool),
            }
        )
    actives = [m for m in mols if m["is_active"]]
    meta = {
        "pool_size": n_pool,
        "best_cycle": data.get("best_cycle", 7),
        "mean_rank": float(data["mean_rank"]),
        "median_rank": float(data["median_rank"]),
        "best_rank": int(data["best_rank"]),
        "worst_rank": int(data["worst_rank"]),
        "mean_pct": float(data["mean_pct"]),
        "top_10pct": int(data["top_10pct"]),
        "top_25pct": int(data["top_25pct"]),
        "top_50pct": int(data["top_50pct"]),
        "active_mean_rank": float(np.mean([m["glare_rank"] for m in actives])),
        "active_mean_pct": float(np.mean([m["glare_pct"] for m in actives])),
        "active_top10": sum(1 for m in actives if m["zone"] == "top10"),
        "active_top25": sum(1 for m in actives if m["zone"] in ("top10", "top25")),
    }
    return mols, meta


def zone_of(rank: int, n_pool: int) -> str:
    if rank <= n_pool * 0.10:
        return "top10"
    if rank <= n_pool * 0.25:
        return "top25"
    if rank <= n_pool * 0.50:
        return "top50"
    return "other"


def zone_color(zone: str) -> str:
    return {"top10": C_TOP10, "top25": C_TOP25, "top50": C_TOP50, "other": C_OTHER}[zone]


def point_color(m) -> str:
    return C_ACTIVE if m["is_active"] else zone_color(m["zone"])


def active_summary_text(mols, meta) -> str:
    lines = []
    by_id = {m["wetlab_id"]: m for m in mols}
    for wid in ACTIVE_ORDER:
        m = by_id[wid]
        lines.append(f"★ {wid}: #{m['glare_rank']} ({m['glare_pct']:.1f}%)")
    lines.append(
        f"Active mean #{meta['active_mean_rank']:.0f} "
        f"({meta['active_mean_pct']:.1f}%) · "
        f"top10 {meta['active_top10']}/3 · top25 {meta['active_top25']}/3"
    )
    return "\n".join(lines)


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
    path = OUT_DIR / "fig_e34_pool_distribution_source_data.csv"
    fields = [
        "wetlab_id",
        "molfactory_id",
        "tanimoto",
        "glare_rank",
        "glare_score",
        "glare_pct",
        "is_active",
        "zone",
        "pool_size",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in mols:
            row = {k: m[k] for k in fields if k != "pool_size"}
            row["pool_size"] = meta["pool_size"]
            w.writerow(row)
    print(f"  OK source CSV -> {path.name}")


def active_legend_handles():
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    return [
        Line2D(
            [0],
            [0],
            marker="*",
            color="w",
            markerfacecolor=C_ACTIVE,
            markeredgecolor=C_EDGE,
            markersize=14,
            label="★ Active: 0228414 / 0228390 / LXC-106",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=C_SIM,
            markeredgecolor=C_EDGE,
            markersize=7,
            label="Similar (non-active)",
        ),
        Patch(facecolor=C_TOP10, label="Top 10% zone"),
        Patch(facecolor=C_TOP25, label="Top 25% zone"),
        Patch(facecolor=C_TOP50, label="Top 50% zone"),
    ]


# ── Figure 1: lollipop ───────────────────────────────────────────────────────
def fig1_rank_lollipop(mols, meta, plt):
    mols_s = sorted(mols, key=lambda m: m["glare_rank"])
    n_pool = meta["pool_size"]
    y = np.arange(len(mols_s))
    ranks = [m["glare_rank"] for m in mols_s]

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    for i, m in enumerate(mols_s):
        c = point_color(m)
        lw = 2.2 if m["is_active"] else 1.2
        ax.hlines(i, 0, m["glare_rank"], color=c, lw=lw, alpha=0.9, zorder=2)
        if m["is_active"]:
            ax.scatter(
                m["glare_rank"], i, marker="*", s=220, c=C_ACTIVE,
                edgecolors=C_EDGE, lw=0.6, zorder=5,
            )
            ax.text(
                m["glare_rank"] + 60, i,
                f"★ #{m['glare_rank']} ({m['glare_pct']:.1f}%)",
                va="center", fontsize=7.5, color=C_ACTIVE, fontweight="bold",
            )
        else:
            ax.scatter(
                m["glare_rank"], i, marker="o", s=36, c=zone_color(m["zone"]),
                edgecolors=C_EDGE, lw=0.4, zorder=4, alpha=0.9,
            )

    for thr, label, ls in [
        (n_pool * 0.10, "Top 10%", ":"),
        (n_pool * 0.25, "Top 25%", "--"),
        (n_pool * 0.50, "Top 50%", "-."),
    ]:
        ax.axvline(thr, color=C_RANDOM, ls=ls, lw=0.8, alpha=0.7, zorder=1)
        ax.text(thr, -0.6, label, fontsize=7, color=C_RANDOM, ha="center", va="top")

    ax.axvline(meta["mean_rank"], color=C_MEAN, ls="--", lw=1.0, alpha=0.8, zorder=1)
    ax.axvline(meta["active_mean_rank"], color=C_ACTIVE, ls="--", lw=1.2, alpha=0.75, zorder=1)

    ylabels = []
    for m in mols_s:
        lab = m["wetlab_id"]
        if m["is_active"]:
            lab = f"★ {lab}"
        ylabels.append(lab)
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.get_yticklabels()[i].set_color(C_ACTIVE)
            ax.get_yticklabels()[i].set_fontweight("bold")

    ax.set_xlabel(f"E34 GLARE rank in pool (N={n_pool}; left = better)")
    ax.set_xlim(0, max(ranks) * 1.22)
    ax.invert_yaxis()
    ax.set_title(
        f"Figure 1: E34 Pool Positions — 13 Similar Molecules "
        f"(cycle_{meta['best_cycle']})\n"
        f"★ Actives highlighted · all-13 mean #{meta['mean_rank']:.0f} · "
        f"active mean #{meta['active_mean_rank']:.0f}"
    )
    ax.legend(handles=active_legend_handles(), loc="lower right", fontsize=7)
    ax.text(
        0.98, 0.98, active_summary_text(mols, meta),
        transform=ax.transAxes, ha="right", va="top", fontsize=7,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.35", facecolor=C_ACTIVE_BG, edgecolor=C_ACTIVE, alpha=0.95),
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig1_rank_lollipop")


# ── Figure 2: horizontal bars ────────────────────────────────────────────────
def fig2_rank_bar(mols, meta, plt):
    mols_s = sorted(mols, key=lambda m: m["glare_rank"])
    n_pool = meta["pool_size"]
    y = np.arange(len(mols_s))
    ranks = [m["glare_rank"] for m in mols_s]

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    colors = [C_ACTIVE if m["is_active"] else zone_color(m["zone"]) for m in mols_s]
    alphas = [0.95 if m["is_active"] else 0.75 for m in mols_s]
    for i, (m, c, a) in enumerate(zip(mols_s, colors, alphas)):
        ax.barh(i, m["glare_rank"], color=c, alpha=a, edgecolor=C_EDGE if m["is_active"] else "white",
                lw=0.8 if m["is_active"] else 0.3, zorder=3, height=0.72)
        tag = f"★ #{m['glare_rank']}" if m["is_active"] else f"#{m['glare_rank']}"
        ax.text(
            m["glare_rank"] + 40, i, tag, va="center", fontsize=7.5,
            color=C_ACTIVE if m["is_active"] else C_MEAN,
            fontweight="bold" if m["is_active"] else "normal",
        )
        if m["is_active"]:
            ax.plot(m["glare_rank"], i, marker="*", markersize=12, color=C_ACTIVE,
                    markeredgecolor=C_EDGE, markeredgewidth=0.5, zorder=5)

    for thr, label, ls in [
        (n_pool * 0.10, "Top 10%", ":"),
        (n_pool * 0.25, "Top 25%", "--"),
        (meta["mean_rank"], f"All mean #{meta['mean_rank']:.0f}", "-"),
        (meta["active_mean_rank"], f"Active mean #{meta['active_mean_rank']:.0f}", "-"),
    ]:
        col = C_ACTIVE if "Active" in label else (C_MEAN if "mean" in label else C_RANDOM)
        ax.axvline(thr, color=col, ls=ls, lw=1.1 if "Active" in label else 0.9, alpha=0.8, zorder=1)

    ylabels = [
        f"{'★ ' if m['is_active'] else ''}{m['wetlab_id']}  "
        f"({m['molfactory_id'].replace('MolFactory_', 'MF')})"
        for m in mols_s
    ]
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=7.5)
    for i, m in enumerate(mols_s):
        if m["is_active"]:
            ax.get_yticklabels()[i].set_color(C_ACTIVE)
            ax.get_yticklabels()[i].set_fontweight("bold")

    ax.set_xlabel("E34 GLARE rank (shorter = better)")
    ax.set_xlim(0, max(ranks) * 1.22)
    ax.invert_yaxis()
    ax.set_title(
        f"Figure 2: E34 Rank Bars — ★ Actives 0228414 / 0228390 / LXC-106\n"
        f"Best #{meta['best_rank']} · Worst #{meta['worst_rank']} · "
        f"Top10={meta['top_10pct']}/13 · Top25={meta['top_25pct']}/13"
    )
    ax.legend(handles=active_legend_handles()[:2], loc="lower right", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig2_rank_bar")


# ── Figure 3: pool rug ───────────────────────────────────────────────────────
def fig3_pool_rug(mols, meta, plt):
    n_pool = meta["pool_size"]
    fig, ax = plt.subplots(figsize=(12.5, 3.6))

    bands = [
        (0, n_pool * 0.10, C_TOP10, "Top 10%"),
        (n_pool * 0.10, n_pool * 0.25, C_TOP25, "Top 25%"),
        (n_pool * 0.25, n_pool * 0.50, C_TOP50, "Top 50%"),
        (n_pool * 0.50, n_pool, "#E8E8E8", "Rest"),
    ]
    for x0, x1, c, _ in bands:
        ax.axvspan(x0, x1, color=c, alpha=0.18, zorder=0)

    ax.hlines(0, 1, n_pool, color=C_RANDOM, lw=1.0, zorder=1)

    # non-actives first, actives on top
    rng = np.random.default_rng(42)
    for m in [x for x in mols if not x["is_active"]] + [x for x in mols if x["is_active"]]:
        jitter = float(rng.uniform(-0.28, 0.28))
        if m["is_active"]:
            ax.scatter(
                m["glare_rank"], jitter, marker="*", s=260, c=C_ACTIVE,
                edgecolors=C_EDGE, lw=0.7, zorder=6, alpha=1.0,
            )
            ax.annotate(
                f"★ {m['wetlab_id']}\n#{m['glare_rank']}",
                (m["glare_rank"], jitter),
                fontsize=7, fontweight="bold", color=C_ACTIVE,
                xytext=(0, 14 if jitter >= 0 else -18),
                textcoords="offset points", ha="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=C_ACTIVE_BG, edgecolor=C_ACTIVE, alpha=0.9),
            )
        else:
            ax.scatter(
                m["glare_rank"], jitter, marker="o", s=45, c=zone_color(m["zone"]),
                edgecolors=C_EDGE, lw=0.4, zorder=4, alpha=0.85,
            )
            ax.annotate(
                m["wetlab_id"], (m["glare_rank"], jitter), fontsize=5.5, alpha=0.7,
                xytext=(0, 9 if jitter >= 0 else -11), textcoords="offset points", ha="center",
            )

    ax.axvline(meta["mean_rank"], color=C_MEAN, ls="--", lw=1.0, zorder=2)
    ax.axvline(meta["active_mean_rank"], color=C_ACTIVE, ls="--", lw=1.3, zorder=2)
    ax.text(meta["mean_rank"], -0.78, f"all mean\n#{meta['mean_rank']:.0f}", fontsize=6.5, ha="center", color=C_MEAN)
    ax.text(
        meta["active_mean_rank"], 0.78,
        f"★ active mean\n#{meta['active_mean_rank']:.0f}",
        fontsize=6.5, ha="center", color=C_ACTIVE, fontweight="bold",
    )

    ax.set_xlim(0, n_pool)
    ax.set_ylim(-1.05, 1.1)
    ax.set_yticks([])
    ax.set_xlabel(f"E34 rank position in MolFactory pool (N={n_pool})")
    ax.set_title("Figure 3: ★ Three Actives on the 10K Rank Axis (E34)")
    from matplotlib.patches import Patch

    ax.legend(
        handles=[Patch(facecolor=c, alpha=0.45, label=lab) for _, _, c, lab in bands]
        + active_legend_handles()[:1],
        loc="upper right",
        ncol=5,
        fontsize=6.5,
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig3_pool_rug")


# ── Figure 4: enrichment ────────────────────────────────────────────────────
def fig4_enrichment(mols, meta, plt):
    n_pool = meta["pool_size"]
    ranks_all = sorted(m["glare_rank"] for m in mols)
    ranks_act = sorted(m["glare_rank"] for m in mols if m["is_active"])
    x = np.linspace(0, 50, 400)

    def curve(ranks):
        return np.array([(np.array(ranks) <= n_pool * xp / 100).sum() / len(ranks) * 100 for xp in x])

    fig, ax = plt.subplots(figsize=(7.2, 6))
    y_all = curve(ranks_all)
    y_act = curve(ranks_act)
    ax.plot(x, y_all, color=C_HERO, lw=2.0, label="All 13 similar", zorder=3)
    ax.plot(x, y_act, color=C_ACTIVE, lw=2.4, label="★ 3 actives", zorder=4)
    ax.plot([0, 50], [0, 50], ls="--", color=C_RANDOM, lw=1.2, label="Random", zorder=1)
    ax.fill_between(x, y_act, x, where=(y_act >= x), color=C_ACTIVE, alpha=0.10, zorder=2)

    for m in mols:
        if m["is_active"]:
            xp = m["glare_rank"] / n_pool * 100
            yp = (np.array(ranks_act) <= m["glare_rank"]).sum() / 3 * 100
            ax.scatter([xp], [yp], marker="*", s=160, c=C_ACTIVE, edgecolors=C_EDGE, lw=0.5, zorder=5)
            ax.annotate(m["wetlab_id"], (xp, yp), fontsize=6.5, color=C_ACTIVE, fontweight="bold",
                        xytext=(4, 4), textcoords="offset points")

    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Top % of E34-ranked pool")
    ax.set_ylabel("% of molecules found")
    ax.set_title("Figure 4: Enrichment — All 13 vs ★ 3 Actives (E34)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    save_fig(fig, plt, "fig4_enrichment")


# ── Figure 5: ECDF ──────────────────────────────────────────────────────────
def fig5_ecdf(mols, meta, plt):
    pcts = sorted(m["glare_pct"] for m in mols)
    y = np.arange(1, len(pcts) + 1) / len(pcts)

    fig, ax = plt.subplots(figsize=(7.2, 6))
    ax.step(pcts, y, where="post", color=C_HERO, lw=2.0, label="All 13", zorder=3)
    ax.plot([0, 100], [0, 1], ls="--", color=C_RANDOM, lw=1.2, label="Uniform random", zorder=1)

    mols_by_pct = sorted(mols, key=lambda z: z["glare_pct"])
    for p, yi, m in zip(pcts, y, mols_by_pct):
        if m["is_active"]:
            ax.scatter([p], [yi], marker="*", s=180, c=C_ACTIVE, edgecolors=C_EDGE, lw=0.5, zorder=5)
            ax.annotate(f"★ {m['wetlab_id']}", (p, yi), fontsize=7, color=C_ACTIVE, fontweight="bold",
                        xytext=(5, 3), textcoords="offset points")
        else:
            ax.scatter([p], [yi], marker="o", s=30, c=zone_color(m["zone"]), edgecolors=C_EDGE, lw=0.3, zorder=4)

    ax.axvline(meta["mean_pct"], color=C_MEAN, ls="--", lw=1.0, alpha=0.8)
    ax.axvline(meta["active_mean_pct"], color=C_ACTIVE, ls="--", lw=1.2, alpha=0.85)
    ax.text(meta["active_mean_pct"] + 0.8, 0.12, f"★ active mean {meta['active_mean_pct']:.1f}%",
            fontsize=7, color=C_ACTIVE, fontweight="bold")
    ax.set_xlim(0, max(35, max(pcts) * 1.15))
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("E34 rank percentile in pool")
    ax.set_ylabel("Cumulative fraction")
    ax.set_title("Figure 5: ECDF of Rank Percentiles (★ = active)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    save_fig(fig, plt, "fig5_ecdf")


# ── Figure 6: Top-N hits ────────────────────────────────────────────────────
def fig6_topn_hits(mols, meta, plt):
    n_pool = meta["pool_size"]
    thresholds = [0.01, 0.05, 0.10, 0.25, 0.50]
    labels = ["Top 1%", "Top 5%", "Top 10%", "Top 25%", "Top 50%"]
    counts_all = [sum(1 for m in mols if m["glare_rank"] <= n_pool * t) for t in thresholds]
    counts_act = [sum(1 for m in mols if m["is_active"] and m["glare_rank"] <= n_pool * t) for t in thresholds]
    expected = [13 * t for t in thresholds]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    x = np.arange(len(labels))
    w = 0.36
    b1 = ax.bar(x - w / 2, counts_all, w, color=C_HERO, alpha=0.9, label="All 13", zorder=3, edgecolor="white")
    b2 = ax.bar(x + w / 2, counts_act, w, color=C_ACTIVE, alpha=0.92, label="★ 3 actives", zorder=3, edgecolor="white")
    ax.plot(x, expected, color=C_RANDOM, ls="--", marker="o", markersize=4, lw=1.2, label="Random (n=13)", zorder=4)

    for bars in (b1, b2):
        for bar in bars:
            v = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.12, f"{int(v)}", ha="center", va="bottom",
                    fontsize=8, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Molecules retrieved")
    ax.set_ylim(0, 14.5)
    ax.axhline(13, color=C_RANDOM, ls=":", lw=0.8, alpha=0.5)
    ax.axhline(3, color=C_ACTIVE, ls=":", lw=0.8, alpha=0.45)
    ax.set_title("Figure 6: Top-N Hits — All 13 vs ★ 3 Actives (E34)")
    ax.legend(loc="upper left")
    ax.text(
        0.98, 0.55, active_summary_text(mols, meta),
        transform=ax.transAxes, ha="right", va="top", fontsize=7, family="monospace",
        bbox=dict(boxstyle="round,pad=0.3", facecolor=C_ACTIVE_BG, edgecolor=C_ACTIVE, alpha=0.95),
    )
    fig.tight_layout()
    save_fig(fig, plt, "fig6_topn_hits")


# ── Figure 7: score vs rank ─────────────────────────────────────────────────
def fig7_score_vs_rank(mols, meta, plt):
    fig, ax = plt.subplots(figsize=(7.8, 6.5))
    # non-actives
    others = [m for m in mols if not m["is_active"]]
    sc = ax.scatter(
        [m["glare_rank"] for m in others],
        [m["glare_score"] for m in others],
        c=[m["tanimoto"] for m in others],
        cmap="YlOrRd",
        vmin=0.5,
        vmax=1.0,
        s=60,
        marker="o",
        edgecolors=C_EDGE,
        lw=0.4,
        zorder=3,
        alpha=0.85,
    )
    for m in others:
        ax.annotate(m["wetlab_id"], (m["glare_rank"], m["glare_score"]), fontsize=6, alpha=0.7,
                    xytext=(3, 3), textcoords="offset points")

    for m in mols:
        if not m["is_active"]:
            continue
        ax.scatter(
            [m["glare_rank"]], [m["glare_score"]],
            marker="*", s=280, c=C_ACTIVE, edgecolors=C_EDGE, lw=0.7, zorder=6,
        )
        ax.annotate(
            f"★ {m['wetlab_id']}\n#{m['glare_rank']} · {m['glare_pct']:.1f}%",
            (m["glare_rank"], m["glare_score"]),
            fontsize=7, fontweight="bold", color=C_ACTIVE,
            xytext=(6, 6), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.2", facecolor=C_ACTIVE_BG, edgecolor=C_ACTIVE, alpha=0.9),
        )

    ax.axvline(meta["pool_size"] * 0.10, color=C_TOP10, ls=":", lw=0.9, alpha=0.7)
    ax.axvline(meta["active_mean_rank"], color=C_ACTIVE, ls="--", lw=1.1, alpha=0.8)
    ax.set_xlabel("E34 GLARE rank (left = better)")
    ax.set_ylabel("E34 GLARE select score")
    ax.set_title("Figure 7: Score vs Rank — ★ Actives Emphasized (E34)")
    ax.invert_xaxis()
    cbar = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Tanimoto (non-actives)", fontsize=8)
    ax.legend(handles=active_legend_handles()[:2], loc="lower left", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig7_score_vs_rank")


# ── Figure 8: percentile histogram ──────────────────────────────────────────
def fig8_pct_hist(mols, meta, plt):
    pcts = [m["glare_pct"] for m in mols]
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    bins = np.linspace(0, max(30, max(pcts) * 1.1), 10)
    ax.hist(pcts, bins=bins, color=C_HERO, alpha=0.55, edgecolor="white", zorder=2, label="All 13")

    for m in mols:
        if m["is_active"]:
            ax.axvline(m["glare_pct"], color=C_ACTIVE, ls="-", lw=1.4, alpha=0.85, zorder=3)
            ax.plot(m["glare_pct"], 0.15, marker="*", markersize=16, color=C_ACTIVE,
                    markeredgecolor=C_EDGE, zorder=5)
            ax.text(m["glare_pct"], 0.45, f"★ {m['wetlab_id']}\n{m['glare_pct']:.1f}%",
                    ha="center", va="bottom", fontsize=6.5, color=C_ACTIVE, fontweight="bold")
        else:
            ax.plot(m["glare_pct"], 0.08, marker="|", markersize=11, color=zone_color(m["zone"]), zorder=4)

    ax.axvline(meta["mean_pct"], color=C_MEAN, ls="--", lw=1.2, label=f"All mean {meta['mean_pct']:.1f}%")
    ax.axvline(meta["active_mean_pct"], color=C_ACTIVE, ls="--", lw=1.4,
               label=f"★ Active mean {meta['active_mean_pct']:.1f}%")
    ax.set_xlabel("E34 rank percentile in pool (%)")
    ax.set_ylabel("Count of molecules")
    ax.set_title("Figure 8: Percentile Distribution — ★ Actives Marked")
    ax.legend(loc="upper right", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig8_pct_hist")


# ── Figure 9: Tanimoto vs pct ───────────────────────────────────────────────
def fig9_tanimoto_vs_pct(mols, meta, plt):
    fig, ax = plt.subplots(figsize=(7.8, 6.2))
    for m in mols:
        if m["is_active"]:
            ax.scatter(
                m["tanimoto"], m["glare_pct"], marker="*", s=280, c=C_ACTIVE,
                edgecolors=C_EDGE, lw=0.7, zorder=5,
            )
            ax.annotate(
                f"★ {m['wetlab_id']}\n#{m['glare_rank']} ({m['glare_pct']:.1f}%)",
                (m["tanimoto"], m["glare_pct"]),
                fontsize=7, fontweight="bold", color=C_ACTIVE,
                xytext=(5, 5), textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=C_ACTIVE_BG, edgecolor=C_ACTIVE, alpha=0.9),
            )
        else:
            ax.scatter(
                m["tanimoto"], m["glare_pct"], marker="o", s=55, c=zone_color(m["zone"]),
                edgecolors=C_EDGE, lw=0.4, zorder=3, alpha=0.9,
            )
            ax.annotate(m["wetlab_id"], (m["tanimoto"], m["glare_pct"]), fontsize=6, alpha=0.7,
                        xytext=(3, 3), textcoords="offset points")

    xs = np.array([m["tanimoto"] for m in mols])
    ys = np.array([m["glare_pct"] for m in mols])
    if len(xs) > 2:
        r = np.corrcoef(xs, ys)[0, 1]
        ax.text(
            0.05, 0.05, f"Pearson r (all 13) = {r:.3f}",
            transform=ax.transAxes, va="bottom", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#DDDDDD", alpha=0.9),
        )

    ax.axhline(10, color=C_TOP10, ls=":", lw=0.9, alpha=0.7)
    ax.axhline(25, color=C_TOP25, ls=":", lw=0.9, alpha=0.7)
    ax.set_xlabel("Tanimoto similarity to wet-lab molecule")
    ax.set_ylabel("E34 rank percentile (lower = better)")
    ax.set_title("Figure 9: Tanimoto vs Pool Percentile — ★ Actives (E34)")
    ax.invert_yaxis()
    ax.legend(handles=active_legend_handles()[:2], loc="lower left", fontsize=7)
    fig.tight_layout()
    save_fig(fig, plt, "fig9_tanimoto_vs_pct")


# ── Figure 10: dashboard ────────────────────────────────────────────────────
def fig10_dashboard(mols, meta, plt):
    n_pool = meta["pool_size"]
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.5))
    by_id = {m["wetlab_id"]: m for m in mols}

    # A: pool rug
    ax = axes[0, 0]
    for x0, x1, c in [
        (0, n_pool * 0.10, C_TOP10),
        (n_pool * 0.10, n_pool * 0.25, C_TOP25),
        (n_pool * 0.25, n_pool * 0.50, C_TOP50),
        (n_pool * 0.50, n_pool, "#E8E8E8"),
    ]:
        ax.axvspan(x0, x1, color=c, alpha=0.15)
    ax.hlines(0, 1, n_pool, color=C_RANDOM, lw=0.9)
    for m in mols:
        if m["is_active"]:
            ax.scatter(m["glare_rank"], 0, marker="*", s=160, c=C_ACTIVE, edgecolors=C_EDGE, lw=0.5, zorder=5)
        else:
            ax.scatter(m["glare_rank"], 0, marker="o", s=35, c=zone_color(m["zone"]), edgecolors=C_EDGE, lw=0.3, zorder=3)
    ax.axvline(meta["mean_rank"], color=C_MEAN, ls="--", lw=1.0)
    ax.axvline(meta["active_mean_rank"], color=C_ACTIVE, ls="--", lw=1.2)
    ax.set_xlim(0, n_pool)
    ax.set_yticks([])
    ax.set_xlabel("E34 pool rank")
    ax.set_title("A. Positions on 10K axis (★ actives)")

    # B: enrichment (actives vs all)
    ax = axes[0, 1]
    ranks_all = sorted(m["glare_rank"] for m in mols)
    ranks_act = sorted(m["glare_rank"] for m in mols if m["is_active"])
    xv = np.linspace(0, 50, 300)
    y_all = [(np.array(ranks_all) <= n_pool * xp / 100).sum() / 13 * 100 for xp in xv]
    y_act = [(np.array(ranks_act) <= n_pool * xp / 100).sum() / 3 * 100 for xp in xv]
    ax.plot(xv, y_all, color=C_HERO, lw=1.8, label="All 13")
    ax.plot(xv, y_act, color=C_ACTIVE, lw=2.2, label="★ 3 actives")
    ax.plot([0, 50], [0, 50], ls="--", color=C_RANDOM, lw=1.0, label="Random")
    ax.set_xlim(0, 50)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Top % of pool")
    ax.set_ylabel("% found")
    ax.set_title("B. Enrichment")
    ax.legend(loc="lower right", fontsize=7)

    # C: summary + active detail table
    ax = axes[1, 0]
    ax.axis("off")
    rows = [
        ["Metric", "Value"],
        ["Pool / cycle", f"{n_pool} / {meta['best_cycle']}"],
        ["All-13 mean rank", f"#{meta['mean_rank']:.0f} ({meta['mean_pct']:.1f}%)"],
        ["★ Active mean", f"#{meta['active_mean_rank']:.0f} ({meta['active_mean_pct']:.1f}%)"],
        ["All Top10 / 25 / 50", f"{meta['top_10pct']}/{meta['top_25pct']}/{meta['top_50pct']} of 13"],
        ["★ Active Top10 / 25", f"{meta['active_top10']}/3 · {meta['active_top25']}/3"],
    ]
    for wid in ACTIVE_ORDER:
        m = by_id[wid]
        rows.append([f"★ {wid}", f"#{m['glare_rank']} ({m['glare_pct']:.1f}%)  T={m['tanimoto']:.3f}"])
    table = ax.table(cellText=rows, cellLoc="center", loc="center", colWidths=[0.38, 0.52])
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    for key, cell in table.get_celld().items():
        cell.set_linewidth(0.3)
        if key[0] == 0:
            cell.set_facecolor("#F0F0F0")
            cell.get_text().set_fontweight("bold")
        elif key[0] >= 6 or (key[0] == 3):
            cell.set_facecolor(C_ACTIVE_BG)
            if key[1] == 0:
                cell.get_text().set_color(C_ACTIVE)
                cell.get_text().set_fontweight("bold")
    ax.set_title("C. Summary + ★ active detail", pad=12)

    # D: score vs rank
    ax = axes[1, 1]
    others = [m for m in mols if not m["is_active"]]
    sc = ax.scatter(
        [m["glare_rank"] for m in others],
        [m["glare_score"] for m in others],
        c=[m["tanimoto"] for m in others],
        cmap="YlOrRd", vmin=0.5, vmax=1.0, s=55, edgecolors=C_EDGE, lw=0.3, zorder=3,
    )
    for m in mols:
        if m["is_active"]:
            ax.scatter([m["glare_rank"]], [m["glare_score"]], marker="*", s=200, c=C_ACTIVE,
                       edgecolors=C_EDGE, lw=0.5, zorder=5)
            ax.annotate(f"★ {m['wetlab_id']}", (m["glare_rank"], m["glare_score"]),
                        fontsize=6.5, color=C_ACTIVE, fontweight="bold",
                        xytext=(4, 4), textcoords="offset points")
        else:
            ax.annotate(m["wetlab_id"], (m["glare_rank"], m["glare_score"]), fontsize=5, alpha=0.65,
                        xytext=(2, 2), textcoords="offset points")
    ax.invert_xaxis()
    ax.set_xlabel("E34 rank")
    ax.set_ylabel("E34 score")
    ax.set_title("D. Score vs rank (★ actives)")
    fig.colorbar(sc, ax=ax, shrink=0.75, pad=0.02).set_label("Tanimoto", fontsize=7)

    fig.suptitle(
        f"Figure 10: E34 Wetlab-13 Pool Dashboard  ·  ★ Actives 0228414 / 0228390 / LXC-106",
        fontsize=12, fontweight="bold", y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_fig(fig, plt, "fig10_dashboard")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mols, meta = load_data()
    plt = setup_style()

    missing = ACTIVE_IDS - {m["wetlab_id"] for m in mols}
    if missing:
        raise SystemExit(f"Active IDs not found in JSON: {missing}")

    print("=" * 64)
    print("  E34 Wetlab-13 — pool distribution (★ 3 actives emphasized)")
    print("=" * 64)
    print(active_summary_text(mols, meta))
    print(
        f"  All-13: mean=#{meta['mean_rank']:.0f}  "
        f"top10={meta['top_10pct']}  top25={meta['top_25pct']}  top50={meta['top_50pct']}"
    )

    write_source_csv(mols, meta)
    fig1_rank_lollipop(mols, meta, plt)
    fig2_rank_bar(mols, meta, plt)
    fig3_pool_rug(mols, meta, plt)
    fig4_enrichment(mols, meta, plt)
    fig5_ecdf(mols, meta, plt)
    fig6_topn_hits(mols, meta, plt)
    fig7_score_vs_rank(mols, meta, plt)
    fig8_pct_hist(mols, meta, plt)
    fig9_tanimoto_vs_pct(mols, meta, plt)
    fig10_dashboard(mols, meta, plt)

    print(f"\nAll figures saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
