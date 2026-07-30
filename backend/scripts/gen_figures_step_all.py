#!/usr/bin/env python3
"""E24-E31 GLARE 实验方法对比可视化（60 配置 × 8 实验）。
输出: figures/step_all/ 下的 PNG + SVG 双格式 Nature 风格图表。
用法: python3 gen_figures_step_all.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import json, warnings, os
from scipy import stats as sp_stats

# ── Config ──
ROOT = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation")
OUTDIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/reports/figures/step_all")
OUTDIR.mkdir(parents=True, exist_ok=True)

# Arial priority, fallback DejaVu Sans
_font = "Arial" if any("Arial" in f for f in plt.rcParams["font.sans-serif"]) else "DejaVu Sans"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": [_font, "DejaVu Sans", "Helvetica"],
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "svg.fonttype": "none",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.5,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "lines.linewidth": 1.0,
    "grid.alpha": 0.3,
})

# ── Color palette ──
EXP_COLORS = {
    "E24": "#484878", "E25": "#7884B4", "E26": "#B4C0E4", "E27": "#E4CCD8",
    "E28": "#CC6677", "E29": "#88CCEE", "E30": "#44AA99", "E31": "#DDCC77",
}
STRAT_COLORS = {"supervised": "#0F4D92", "grpo": "#E53935"}
PASS_COLORS = {"PASS": "#2E9E44", "FAIL": "#E53935"}

# ── Data compilation ──
EXPERIMENTS = {
    "E24": ROOT / "glare_e24_patent_split_20260629",
    "E25": ROOT / "glare_e25_warmlr_optimization_20260629",
    "E26": ROOT / "glare_e26_patent_320_83_20260630",
    "E27": ROOT / "glare_e27_warmlr_320_83_20260630",
    "E28": ROOT / "glare_e28_lr_sweep_20260629",
    "E29": ROOT / "glare_e29_retro_modern_20260629",
    "E30": ROOT / "glare_e30_grpo_20260630",
    "E31": ROOT / "glare_e31_paper_grpo_20260630",
}


def parse_summary(path):
    """Parse a single summary.json, return flat dict."""
    try:
        d = json.load(open(path))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    cfg = d.get("config", {}) or {}
    rs = d.get("rounds", [])
    if not rs:
        return None
    config_name = d.get("name", "")

    r0 = rs[0]
    r_last = rs[-1]
    num_r = len(rs)

    # Strategy detection — try multiple sources
    r1_strategy = cfg.get("r1_strategy") or cfg.get("strat") or "supervised"
    if config_name in ("grpo_default", "grpo_high_lambda", "grpo_low_beta", "grpo_5e4",
                       "grpo_half_decoy", "grpo_r2", "grpo_two_phase", "grpo_hard_neg",
                       "grpo_3e4", "grpo_1e3", "grpo_10ep", "grpo_3K_decoy",
                       "grpo_ens5", "grpo_combo_w2", "grpo_hard_neg_3K",
                       "grpo_half_decoy_5e4", "grpo_r2_high_lam"):
        # E30 configs — all used supervised after W1, despite grpo_ prefix
        if config_name in ("grpo_default", "grpo_high_lambda", "grpo_low_beta", "grpo_5e4"):
            r1_strategy = "grpo"
        else:
            r1_strategy = "supervised"
    if config_name.startswith("e31_"):
        r1_strategy = cfg.get("strat") or "grpo"
        if config_name == "e31_sup":
            r1_strategy = "supervised"

    # LR extraction — try config dict first, then fall back to name-based inference
    lr_r1 = cfg.get("r1_lr") or cfg.get("lr")
    if isinstance(lr_r1, list):
        lr_r1 = lr_r1[-1]
    if isinstance(lr_r1, str) and lr_r1.startswith("["):
        import ast
        lr_list = ast.literal_eval(lr_r1)
        lr_r1 = lr_list[-1] if lr_list else 3e-4
    if lr_r1 is None or lr_r1 == "?":
        # Fallback: infer from config name
        lr_map = {
            "lr_5e4": 5e-4, "lr_7e4": 7e-4, "lr_8e4": 8e-4, "lr_9e4": 9e-4,
            "lr_1p5e3": 1.5e-3, "lr_1e3": 1e-3,
            "warm_lr": 1e-3, "fb_amp": 3e-3, "high_weight": 3e-4,
            "curriculum": 3e-3, "combo_moderate": 1e-3,
            "combo_lr5e4_w3_r2": 5e-4, "half_decoy_lr5e4_r2": 5e-4,
            "deep_r0": 7e-4, "ens5_r0": 7e-4, "hard_neg_r1": 7e-4,
            "two_phase_r1": 3e-4,  # second phase LR
            "lr_anneal_r1": 3e-4,
            "grpo_5e4": 5e-4, "grpo_3e4": 3e-4, "grpo_1e3": 1e-3,
            "grpo_10ep": 7e-4, "grpo_3K_decoy": 7e-4, "grpo_ens5": 7e-4,
            "grpo_combo_w2": 5e-4, "grpo_hard_neg_3K": 7e-4,
            "grpo_half_decoy_5e4": 5e-4, "sup_half_decoy_5e4": 5e-4,
            "sup_5e4": 5e-4, "sup_7e4": 7e-4,
            "grpo_r2_high_lam": 7e-4, "fb_amp_r2": 3e-3,
            "lr_7e4_r2": 7e-4, "lr_8e4_r2": 8e-4,
            "warm_lr_r2": 1e-3, "warm_lr_replica": 1e-3,
            "lr_7e4_10ep": 7e-4, "lr_7e4_grpo": 7e-4,
            "half_decoy": 1e-3,
        }
        lr_r1 = lr_map.get(config_name, 7e-4)
    lr_r1 = float(lr_r1)

    # Decoy — from config or infer from name
    r1_decoy = cfg.get("r1_decoy") or cfg.get("dc")
    if r1_decoy is None:
        decoy_map = {
            "grpo_half_decoy": "half", "grpo_3K_decoy": "3K",
            "grpo_hard_neg": "hard_neg", "grpo_hard_neg_3K": "hard_neg_3K",
            "grpo_half_decoy_5e4": "half", "sup_half_decoy_5e4": "half",
            "grpo_two_phase": "two_phase", "two_phase_r1": "two_phase",
            "grpo_r2_high_lam": "full", "grpo_r2": "full",
            "half_decoy": "half", "half_decoy_lr5e4_r2": "half",
            "hard_neg_r1": "hard_neg", "lr_anneal_r1": "full",
            "e31_d50": 50, "e31_d100": 100, "e31_d200": 200, "e31_sup": 100,
        }
        r1_decoy = decoy_map.get(config_name, "full")
    if isinstance(r1_decoy, (int, float)):
        r1_decoy = int(r1_decoy)

    # Method family assignment
    lr = float(lr_r1 or 3e-4)
    if lr <= 3.1e-4:     lr_family = "3e-4 (conservative)"
    elif lr <= 5.1e-4:   lr_family = "5e-4 (mod-conservative)"
    elif lr <= 7.1e-4:   lr_family = "7e-4 (moderate)"
    elif lr <= 8.1e-4:   lr_family = "8e-4 (mod-aggressive)"
    elif lr <= 9.1e-4:   lr_family = "9e-4 (aggressive)"
    elif lr <= 1.1e-3:   lr_family = "1e-3 (very aggressive)"
    elif lr <= 1.6e-3:   lr_family = "1.5e-3 (extreme)"
    else:                lr_family = "3e-3 (ultra-extreme)"

    # Decoy family
    if isinstance(r1_decoy, str):
        if "hard_neg" in str(r1_decoy):  decoy_family = "Hard Negative"
        elif "half" in str(r1_decoy):    decoy_family = "Half (5K)"
        elif "3K" in str(r1_decoy):     decoy_family = "3K"
        elif "two_phase" in str(r1_decoy): decoy_family = "Two-Phase"
        elif "curriculum" in str(r1_decoy): decoy_family = "Curriculum"
        else:                            decoy_family = "Full (10K)"
    elif isinstance(r1_decoy, (int, float)):
        d = int(r1_decoy)
        if d <= 60:      decoy_family = "Tiny (≤50)"
        elif d <= 150:   decoy_family = "Tiny (100-150)"
        else:            decoy_family = "Tiny (200)"
    else:
        decoy_family = "Full (10K)"

    # Mechanism flags
    has_r2 = num_r >= 3 or "r2" in config_name.lower()
    is_two_phase = isinstance(cfg.get("r1_lr"), list) or "two_phase" in str(r1_decoy) or "two_phase" in config_name
    is_hard_neg = "hard_neg" in str(r1_decoy) or "hard_neg" in config_name
    strong_w = cfg.get("strong_w_mult", 1.0)
    # Infer strong_w from config name
    if strong_w == 1.0:
        w_map = {"combo_moderate": 1.5, "combo_lr5e4_w3_r2": 3.0,
                 "grpo_combo_w2": 2.0, "high_weight": 2.5}
        strong_w = w_map.get(config_name, 1.0)
    is_combo = strong_w > 1.0 or "combo" in config_name.lower()
    ens = cfg.get("ens") or cfg.get("ensemble_size", 3)
    if ens is None or ens == "?":
        ens = 5 if "ens5" in config_name else 3
    ep = cfg.get("r1_ep", 5)
    if isinstance(ep, list): ep = sum(ep)
    if isinstance(ep, str) and ep.startswith("["):
        import ast
        ep_list = ast.literal_eval(ep)
        ep = sum(ep_list) if ep_list else 5
    if ep is None or ep == "?":
        ep = 10 if "10ep" in config_name else 5

    return {
        "experiment": d.get("experiment", ""),
        "config_name": d.get("name", ""),
        "strategy": r1_strategy,
        "lr_r1": lr_r1,
        "lr_family": lr_family,
        "r1_decoy_raw": r1_decoy,
        "decoy_family": decoy_family,
        "num_rounds": num_r,
        "has_r2": has_r2,
        "is_two_phase": is_two_phase,
        "is_hard_neg": is_hard_neg,
        "is_combo": is_combo,
        "strong_w": strong_w,
        "ensemble_size": ens,
        "epochs_r1": ep,
        "R0_ROC": r0.get("roc"),
        "R1_ROC": r_last.get("roc") if num_r >= 2 else r0.get("roc"),
        "R2_ROC": rs[2].get("roc") if num_r >= 3 else None,
        "R0_rank_strong": r0.get("rank_strong"),
        "R_final_rank_strong": r_last.get("rank_strong"),
        "R0_rank_all13": r0.get("rank_all13"),
        "R_final_rank_all13": r_last.get("rank_all13"),
        "delta_roc": d.get("delta_roc"),
        "delta_rank_strong": d.get("delta_rank_strong"),
        "delta_rank_all13": d.get("delta_rank_all13"),
        "PASS": d.get("success_rank_improved", False) and d.get("success_roc_preserved", False),
    }


def build_master_df():
    """Parse all summary.json files into one DataFrame."""
    rows = []
    for exp_name, exp_dir in EXPERIMENTS.items():
        if not exp_dir.exists():
            continue
        for sf in sorted(exp_dir.rglob("summary.json")):
            # Skip shared R0 and master summaries, and files not in config subdirs
            parent = sf.parent.name
            if "shared" in str(sf) or parent in ("master_summary.json", ""):
                continue
            try:
                row = parse_summary(sf)
            except Exception as e:
                print(f"  ERROR parsing {sf}: {e}")
                continue
            if row is None:
                continue
            row["experiment"] = exp_name  # override
            rows.append(row)
    df = pd.DataFrame(rows)
    # Drop duplicates (same config from different paths)
    df = df.drop_duplicates(subset=["experiment", "config_name"])
    print(f"Compiled {len(df)} configs across {df['experiment'].nunique()} experiments")
    print(f"  PASS: {df['PASS'].sum()}/{len(df)} ({(df['PASS'].sum()/len(df)*100):.0f}%)")
    print(f"  GRPO: {(df['strategy']=='grpo').sum()}, Supervised: {(df['strategy']!='grpo').sum()}")
    return df


# ── Utility ──
def save_pub(fig, name):
    for fmt in ["png", "svg"]:
        fig.savefig(OUTDIR / f"{name}.{fmt}", format=fmt)
    plt.close(fig)


def add_panel_label(ax, label, x=-0.08, y=1.05):
    ax.text(x, y, label, transform=ax.transAxes, fontsize=10, fontweight="bold", va="top")


def style_ax(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.3, linewidth=0.3)


# ── Figure 1: Leaderboard ──
def fig1_leaderboard(df):
    fig = plt.figure(figsize=(7.2, 8.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.35)

    # Panel a: ΔROC vs ΔRank scatter
    ax = fig.add_subplot(gs[0])
    add_panel_label(ax, "a")

    for exp in sorted(df["experiment"].unique()):
        sub = df[df["experiment"] == exp]
        is_good = sub["PASS"]
        ax.scatter(
            sub.loc[~is_good, "delta_rank_strong"], sub.loc[~is_good, "delta_roc"],
            c=EXP_COLORS[exp], marker="o", s=35, alpha=0.5, edgecolors="none",
            label="_nolegend_"
        )
        ax.scatter(
            sub.loc[is_good, "delta_rank_strong"], sub.loc[is_good, "delta_roc"],
            c=EXP_COLORS[exp], marker="o", s=50, alpha=0.95, edgecolors="white",
            linewidths=0.5, label=exp,
        )
    # PASS zone shading
    ax.axhline(y=-0.03, color="#767676", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axvline(x=0, color="#767676", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.axhspan(-0.03, 0.15, xmin=0.5, alpha=0.04, color="green")
    ax.axhspan(-0.25, -0.03, xmin=0, xmax=0.5, alpha=0.04, color="green")
    ax.fill_between([-20000, 0], -0.03, 0.15, alpha=0.06, color="#2E9E44")
    ax.text(-17000, 0.12, "PASS zone", fontsize=7, color="#2E9E44", fontstyle="italic", alpha=0.7)

    # Annotate top configs
    top5 = df[df["PASS"]].nlargest(5, "R1_ROC")
    top5r = df[df["PASS"]].nsmallest(5, "delta_rank_strong")
    annotate = pd.concat([top5, top5r]).drop_duplicates()
    for _, row in annotate.iterrows():
        offset_y = 0.008 if row["delta_rank_strong"] > -500 else 0.012
        ax.annotate(
            f"{row['experiment']} {row['config_name']}",
            (row["delta_rank_strong"], row["delta_roc"]),
            xytext=(row["delta_rank_strong"] + 50, row["delta_roc"] + offset_y),
            fontsize=5.5, alpha=0.85,
            arrowprops=dict(arrowstyle="->", color="#555555", lw=0.4, connectionstyle="arc3,rad=0.1"),
        )

    ax.set_xlabel("Δ Rank-Strong (negative = improved ranking)")
    ax.set_ylabel("Δ ROC")
    ax.legend(loc="upper left", frameon=False, fontsize=6, ncol=2, markerscale=0.8)
    style_ax(ax)

    # Panel b: PASS rate by experiment
    ax2 = fig.add_subplot(gs[1])
    add_panel_label(ax2, "b")

    exp_summary = df.groupby("experiment").agg(
        total=("PASS", "count"),
        passed=("PASS", "sum"),
    ).reset_index()
    exp_summary["fail"] = exp_summary["total"] - exp_summary["passed"]
    exp_summary["pct"] = (exp_summary["passed"] / exp_summary["total"] * 100).astype(int)

    x = np.arange(len(exp_summary))
    w = 0.6
    bars_pass = ax2.bar(x, exp_summary["passed"], w, color="#2E9E44", alpha=0.8, label="PASS")
    bars_fail = ax2.bar(x, exp_summary["fail"], w, bottom=exp_summary["passed"], color="#E53935", alpha=0.5, label="FAIL")
    for i, row in exp_summary.iterrows():
        ax2.text(i, row["total"] + 0.5, f'{row["pct"]}%\n({int(row["passed"])}/{int(row["total"])})',
                ha="center", fontsize=6.5, lineheight=1.2)
    ax2.set_xticks(x)
    ax2.set_xticklabels(exp_summary["experiment"])
    ax2.set_ylabel("Config count")
    ax2.legend(frameon=False, fontsize=7, ncol=2)
    ax2.set_ylim(0, exp_summary["total"].max() + 4)
    style_ax(ax2)

    save_pub(fig, "fig1_leaderboard")
    print("  fig1_leaderboard saved")


# ── Figure 2: Method Family Comparison ──
def fig2_method_families(df):
    fig, axes = plt.subplots(2, 3, figsize=(7.5, 7.0))
    axes = axes.flatten()

    families = [
        ("lr_family", "LR Strategy", axes[0]),
        ("decoy_family", "Decoy Strategy", axes[1]),
        ("epochs_r1", "Training Epochs", axes[2]),
        ("has_r2", "Multi-Round", axes[3]),
        ("ensemble_size", "Ensemble Size", axes[4]),
        ("strong_w", "Weight Multiplier", axes[5]),
    ]

    for col, title, ax in families:
        add_panel_label(ax, chr(97 + families.index((col, title, ax))))

        if col == "has_r2":
            cats = {False: "2-Round (R0→R1)", True: "3-Round (R0→R1→R2)"}
            df_plot = df.copy()
            df_plot["cat"] = df_plot["has_r2"].map(cats)
            order = ["2-Round (R0→R1)", "3-Round (R0→R1→R2)"]
        elif col == "epochs_r1":
            df_plot = df.copy()
            df_plot["cat"] = df_plot["epochs_r1"].apply(lambda x: f"{int(x)} ep")
            order = sorted(df_plot["cat"].unique())
        elif col == "ensemble_size":
            df_plot = df.copy()
            df_plot["cat"] = df_plot["ensemble_size"].apply(lambda x: f"Ens={int(x)}")
            order = sorted(df_plot["cat"].unique())
        elif col == "strong_w":
            df_plot = df.copy()
            def w_cat(w):
                if w <= 1.0: return "w=1.0"
                if w <= 1.5: return "w=1.5"
                if w <= 2.0: return "w=2.0"
                return "w≥2.5"
            df_plot["cat"] = df_plot["strong_w"].apply(w_cat)
            order = ["w=1.0", "w=1.5", "w=2.0", "w≥2.5"]
        else:
            df_plot = df.copy()
            df_plot["cat"] = df_plot[col]
            order = sorted(df_plot["cat"].unique())

        # Filter categories with at least 1 data point
        order = [o for o in order if (df_plot["cat"] == o).sum() > 0]

        # Box + strip plot
        palette = sns.color_palette("vlag_r", len(order)) if len(order) > 2 else ["#B4C8E8", "#3C68A8"]
        sns.boxplot(
            data=df_plot, y="cat", x="delta_rank_strong", order=order,
            ax=ax, palette=palette, width=0.5, linewidth=0.5, fliersize=0,
            showmeans=True, meanprops={"marker": "D", "markerfacecolor": "#E53935", "markersize": 4}
        )
        sns.stripplot(
            data=df_plot, y="cat", x="delta_rank_strong", order=order,
            ax=ax, color="black", alpha=0.25, size=3, jitter=True,
        )
        ax.axvline(x=0, color="#767676", linestyle="--", linewidth=0.6)

        # Kruskal-Wallis test
        groups = [df_plot[df_plot["cat"] == o]["delta_rank_strong"].dropna().values for o in order if (df_plot["cat"] == o).sum() > 3]
        if len(groups) >= 2:
            try:
                h, p = sp_stats.kruskal(*groups)
                p_text = f"p={p:.3f}" if p >= 0.001 else "p<0.001"
                ax.set_title(f"{title}  (K-W {p_text})", fontsize=7.5, color="#555555")
            except Exception:
                ax.set_title(title, fontsize=7.5)
        else:
            ax.set_title(title, fontsize=7.5)

        ax.set_ylabel("")
        ax.set_xlabel("Δ Rank-Strong (← better)")
        style_ax(ax)

    fig.tight_layout(pad=1.5)
    save_pub(fig, "fig2_method_families_rank")
    print("  fig2_method_families_rank saved")


# ── Figure 3: ΔROC by Method Family ──
def fig3_method_families_roc(df):
    fig, axes = plt.subplots(2, 3, figsize=(7.5, 7.0))
    axes = axes.flatten()

    families = [
        ("lr_family", "LR Strategy", axes[0]),
        ("decoy_family", "Decoy Strategy", axes[1]),
        ("epochs_r1", "Training Epochs", axes[2]),
        ("has_r2", "Multi-Round", axes[3]),
        ("ensemble_size", "Ensemble Size", axes[4]),
        ("strong_w", "Weight Multiplier", axes[5]),
    ]

    for col, title, ax in families:
        add_panel_label(ax, chr(97 + families.index((col, title, ax))))

        if col == "has_r2":
            cats = {False: "2-Round", True: "3-Round"}
            df_plot = df.copy()
            df_plot["cat"] = df_plot["has_r2"].map(cats)
            order = ["2-Round", "3-Round"]
        elif col == "epochs_r1":
            df_plot = df.copy()
            df_plot["cat"] = df_plot["epochs_r1"].apply(lambda x: f"{int(x)} ep")
            order = sorted(df_plot["cat"].unique())
        elif col == "ensemble_size":
            df_plot = df.copy()
            df_plot["cat"] = df_plot["ensemble_size"].apply(lambda x: f"Ens={int(x)}")
            order = sorted(df_plot["cat"].unique())
        elif col == "strong_w":
            df_plot = df.copy()
            def w_cat(w):
                if w <= 1.0: return "w=1.0"
                if w <= 1.5: return "w=1.5"
                if w <= 2.0: return "w=2.0"
                return "w≥2.5"
            df_plot["cat"] = df_plot["strong_w"].apply(w_cat)
            order = ["w=1.0", "w=1.5", "w=2.0", "w≥2.5"]
        else:
            df_plot = df.copy()
            df_plot["cat"] = df_plot[col]
            order = sorted(df_plot["cat"].unique())

        order = [o for o in order if (df_plot["cat"] == o).sum() > 0]

        palette = sns.color_palette("vlag_r", len(order)) if len(order) > 2 else ["#B4C8E8", "#3C68A8"]
        sns.boxplot(
            data=df_plot, y="cat", x="delta_roc", order=order,
            ax=ax, palette=palette, width=0.5, linewidth=0.5, fliersize=0,
            showmeans=True, meanprops={"marker": "D", "markerfacecolor": "#E53935", "markersize": 4}
        )
        sns.stripplot(
            data=df_plot, y="cat", x="delta_roc", order=order,
            ax=ax, color="black", alpha=0.25, size=3, jitter=True,
        )
        ax.axvline(x=-0.03, color="#E53935", linestyle=":", linewidth=0.6, alpha=0.7)
        ax.axvline(x=0, color="#767676", linestyle="--", linewidth=0.6)
        # ROC tolerance zone
        ax.axvspan(-0.03, 0.03, alpha=0.04, color="#2E9E44")

        groups = [df_plot[df_plot["cat"] == o]["delta_roc"].dropna().values for o in order if (df_plot["cat"] == o).sum() > 3]
        if len(groups) >= 2:
            try:
                h, p = sp_stats.kruskal(*groups)
                p_text = f"p={p:.3f}" if p >= 0.001 else "p<0.001"
                ax.set_title(f"{title}  (K-W {p_text})", fontsize=7.5, color="#555555")
            except Exception:
                ax.set_title(title, fontsize=7.5)
        else:
            ax.set_title(title, fontsize=7.5)
        ax.set_ylabel("")
        ax.set_xlabel("Δ ROC")
        style_ax(ax)

    fig.tight_layout(pad=1.5)
    save_pub(fig, "fig3_method_families_roc")
    print("  fig3_method_families_roc saved")


# ── Figure 4: GRPO vs Supervised ──
def fig4_grpo_comparison(df):
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 3.5))
    ax0, ax1, ax2 = axes

    # Panel a: GRPO collapse (E30 Wave 1) + Supervised
    add_panel_label(ax0, "a")
    grpo_w1 = df[(df["experiment"] == "E30") & (df["config_name"].isin(["grpo_default", "grpo_high_lambda", "grpo_low_beta", "grpo_5e4"]))]
    # Supervised Wave 3-5 E30 configs
    sup_e30 = df[(df["experiment"] == "E30") & (~df["config_name"].isin(["grpo_default", "grpo_high_lambda", "grpo_low_beta", "grpo_5e4"]))]

    x_pos = [0, 1]
    grpo_vals = grpo_w1["delta_roc"].dropna().values
    sup_vals = sup_e30["delta_roc"].dropna().values

    bp0 = ax0.boxplot([grpo_vals, sup_vals], positions=x_pos, widths=0.4,
                       patch_artist=True, showmeans=True,
                       meanprops={"marker": "D", "markerfacecolor": "#E53935", "markersize": 5})
    bp0["boxes"][0].set_facecolor("#E53935"); bp0["boxes"][0].set_alpha(0.6)
    bp0["boxes"][1].set_facecolor("#0F4D92"); bp0["boxes"][1].set_alpha(0.6)
    ax0.scatter(np.random.normal(0, 0.03, len(grpo_vals)), grpo_vals, c="#E53935", alpha=0.5, s=10, zorder=5)
    ax0.scatter(np.random.normal(1, 0.03, len(sup_vals)), sup_vals, c="#0F4D92", alpha=0.5, s=10, zorder=5)
    ax0.axhline(y=-0.03, color="#767676", linestyle="--", linewidth=0.6)
    ax0.axhline(y=0, color="#767676", linestyle="-", linewidth=0.4, alpha=0.5)
    ax0.set_xticks(x_pos)
    ax0.set_xticklabels(["GRPO (E30 W1)\ncollapsed to ROC=0.5", "Supervised\n(E30 W2-W5)"], fontsize=6.5)
    ax0.set_ylabel("Δ ROC")
    ax0.set_title("GRPO Collapse vs. Supervised", fontsize=7.5)
    # Mann-Whitney
    try:
        u, p = sp_stats.mannwhitneyu(grpo_vals, sup_vals)
        ax0.text(0.5, 0.95, f"M-W p={p:.4f}", transform=ax0.transAxes, ha="center", fontsize=6.5, color="#555555")
    except Exception:
        pass
    style_ax(ax0)

    # Panel b: E31 — GRPO with fix vs Supervised (same decoy)
    add_panel_label(ax1, "b")
    e31 = df[df["experiment"] == "E31"].copy()
    e31["label"] = e31["config_name"].apply(lambda x: x.replace("e31_", ""))
    for i, (_, row) in enumerate(e31.iterrows()):
        color = STRAT_COLORS.get(row["strategy"], "#888888")
        marker = "o" if row["strategy"] == "grpo" else "s"
        ax1.scatter(row["delta_rank_strong"], row["delta_roc"], c=color, marker=marker,
                    s=80, edgecolors="white", linewidths=0.5, zorder=5)
        ax1.annotate(row["label"], (row["delta_rank_strong"], row["delta_roc"]),
                     xytext=(row["delta_rank_strong"] + 2, row["delta_roc"] + 0.002),
                     fontsize=6, alpha=0.9)
    ax1.axhline(y=-0.03, color="#767676", linestyle="--", linewidth=0.6)
    ax1.axvline(x=0, color="#767676", linestyle="--", linewidth=0.6)
    ax1.set_xlabel("Δ Rank-Strong")
    ax1.set_ylabel("Δ ROC")
    ax1.set_title("E31: Fixed GRPO (tiny decoy)", fontsize=7.5)
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor=STRAT_COLORS["grpo"], markersize=6, label='GRPO'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor=STRAT_COLORS["supervised"], markersize=6, label='Supervised'),
    ]
    ax1.legend(handles=legend_elements, frameon=False, fontsize=6, loc="lower left")
    style_ax(ax1)

    # Panel c: Final ROC vs Rank-Strong bubble
    add_panel_label(ax2, "c")
    grpo_all = df[df["strategy"] == "grpo"]
    sup_all = df[df["strategy"] != "grpo"]

    ax2.scatter(sup_all["R_final_rank_strong"], sup_all["R1_ROC"],
                c="#0F4D92", alpha=0.4, s=sup_all["epochs_r1"] * 8, label="Supervised", edgecolors="none")
    ax2.scatter(grpo_all["R_final_rank_strong"], grpo_all["R1_ROC"],
                c="#E53935", alpha=0.7, s=grpo_all["epochs_r1"] * 8, marker="^", label="GRPO", edgecolors="white", linewidths=0.3)

    ax2.set_xlabel("Final Rank-Strong (lower = better)")
    ax2.set_ylabel("Final ROC")
    ax2.set_title("ROC vs. Ranking: All Configs", fontsize=7.5)
    ax2.legend(frameon=False, fontsize=6)
    style_ax(ax2)

    fig.tight_layout(pad=1.5)
    save_pub(fig, "fig4_grpo_comparison")
    print("  fig4_grpo_comparison saved")


# ── Figure 5: Summary Heatmap ──
def fig5_heatmap(df):
    # Sort: experiment, then delta_rank_strong within experiment
    df_sorted = df.sort_values(["experiment", "delta_rank_strong"]).copy()

    metrics = ["R0_ROC", "R1_ROC", "R2_ROC", "R0_rank_strong", "R_final_rank_strong",
               "delta_roc", "delta_rank_strong", "delta_rank_all13"]
    metric_labels = ["R0 ROC", "R1 ROC", "R2 ROC", "R0 Rank-Str", "Final Rank-Str",
                     "Δ ROC", "Δ Rank-Str", "Δ Rank-All13"]

    data = df_sorted[metrics].copy()
    # Z-score normalize each column
    data_norm = data.copy()
    for col in metrics:
        mean_v = data[col].mean()
        std_v = data[col].std()
        if std_v > 0:
            data_norm[col] = (data[col] - mean_v) / std_v
        else:
            data_norm[col] = 0

    n_configs = len(df_sorted)
    fig_height = max(8, n_configs * 0.22)
    fig, ax = plt.subplots(figsize=(8, fig_height))

    # Diverging colormap
    from matplotlib.colors import LinearSegmentedColormap
    cmap = sns.diverging_palette(240, 10, as_cmap=True)

    im = ax.imshow(data_norm.values, aspect="auto", cmap=cmap, vmin=-2.5, vmax=2.5)

    # Labels
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metric_labels, rotation=45, ha="right", fontsize=6.5)
    ax.set_yticks(range(n_configs))
    ax.set_yticklabels(
        [f"{r['experiment']} {r['config_name'][:22]}" for _, r in df_sorted.iterrows()],
        fontsize=5.5
    )

    # PASS strip on right
    for i, (_, r) in enumerate(df_sorted.iterrows()):
        color = PASS_COLORS["PASS"] if r["PASS"] else PASS_COLORS["FAIL"]
        ax.annotate("✓" if r["PASS"] else "✗", (len(metrics), i),
                    fontsize=7, color=color, ha="center", va="center", weight="bold")

    # Method strips on left
    lr_colors = sns.color_palette("Blues", df_sorted["lr_family"].nunique())
    lr_map = {k: v for k, v in zip(df_sorted["lr_family"].unique(), lr_colors)}
    for i, (_, r) in enumerate(df_sorted.iterrows()):
        ax.add_patch(plt.Rectangle((-1.2, i - 0.45), 0.25, 0.9, color=lr_map.get(r["lr_family"], "#ccc"), clip_on=False))

    ax.add_patch(plt.Rectangle((-1.2, -0.5), 0.25, 0, color="none"))  # dummy for extent
    ax.set_xlim(-1.3, len(metrics) + 0.3)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.5, aspect=30, pad=0.01)
    cbar.set_label("Z-score (per metric)", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    ax.set_title("E24-E31 Full Config × Metric Heatmap (60 configs)", fontsize=8.5, pad=8)
    fig.tight_layout(pad=1.0)
    save_pub(fig, "fig5_heatmap")
    print("  fig5_heatmap saved")


# ── Figure 6: Top Configs Leaderboard (clean bar chart) ──
def fig6_top_configs(df):
    # Top PASS configs by combined score
    pass_df = df[df["PASS"]].copy()
    pass_df["combined"] = -pass_df["delta_rank_strong"] / 100 + pass_df["delta_roc"] * 100
    top = pass_df.nlargest(15, "combined")

    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    add_panel_label(ax, "a")

    y_pos = range(len(top))
    colors = [EXP_COLORS.get(e, "#888") for e in top["experiment"]]
    bars = ax.barh(y_pos, top["combined"], color=colors, alpha=0.85, height=0.6)

    # Add metric annotations
    for i, (_, row) in enumerate(top.iterrows()):
        label = f'{row["experiment"]} {row["config_name"]}'
        ax.text(-0.5, i, label, ha="right", va="center", fontsize=6, fontfamily="monospace")
        metrics_text = f'ROC={row["R1_ROC"]:.3f}  ΔROC={row["delta_roc"]:+.3f}  ΔRank={row["delta_rank_strong"]:+.0f}'
        ax.text(row["combined"] + 0.1, i, metrics_text, ha="left", va="center", fontsize=5.5, color="#555555")

    ax.set_yticks([])
    ax.set_xlabel("Combined Score (−ΔRank/100 + ΔROC×100)")
    ax.set_title("Top 15 PASS Configs by Combined Score (ROC + Rank)", fontsize=8)
    ax.axvline(x=0, color="#767676", linewidth=0.5, linestyle="--")

    # Legend for experiments
    legend_elements = [mpatches.Patch(facecolor=c, alpha=0.85, label=e) for e, c in EXP_COLORS.items()]
    ax.legend(handles=legend_elements, frameon=False, fontsize=6, ncol=4, loc="lower right")
    style_ax(ax)

    fig.tight_layout(pad=1.0)
    save_pub(fig, "fig6_top_configs")
    print("  fig6_top_configs saved")


# ── Main ──
if __name__ == "__main__":
    os.chdir("/data/ye/e-drug-lab/backend")
    print("Building master dataframe...")
    df = build_master_df()

    # Save compiled data
    df.to_csv(OUTDIR / "compiled_data.csv", index=False)
    print(f"  compiled_data.csv saved ({len(df)} rows)")

    print("\nGenerating figures...")
    fig1_leaderboard(df)
    fig2_method_families(df)
    fig3_method_families_roc(df)
    fig4_grpo_comparison(df)
    fig5_heatmap(df)
    fig6_top_configs(df)

    # Stats report
    report = {
        "total_configs": len(df),
        "total_pass": int(df["PASS"].sum()),
        "pass_rate": f"{df['PASS'].sum()/len(df)*100:.1f}%",
        "by_experiment": df.groupby("experiment").agg(
            total=("PASS", "count"), passed=("PASS", "sum"),
            pass_pct=("PASS", lambda x: f"{x.sum()/len(x)*100:.0f}%"),
            best_roc=("R1_ROC", "max"),
            best_rank=("delta_rank_strong", "min"),
        ).to_dict(),
        "best_overall_roc": float(df.loc[df["R1_ROC"].idxmax(), "R1_ROC"]),
        "best_overall_roc_config": str(df.loc[df["R1_ROC"].idxmax(), "config_name"]),
        "best_rank_improvement": float(df["delta_rank_strong"].min()),
        "best_rank_config": str(df.loc[df["delta_rank_strong"].idxmin(), "config_name"]),
    }
    with open(OUTDIR / "statistical_tests.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  statistical_tests.json saved")
    print(f"\nDone! All figures in {OUTDIR}/")
