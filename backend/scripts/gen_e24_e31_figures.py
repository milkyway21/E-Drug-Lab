#!/usr/bin/env python3
"""E24-E31 可视化对比。独立运行，不依赖模块import。
python3 gen_e24_e31_figures.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import json, ast
from scipy import stats as sp_stats

ROOT = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/validation")
OUTDIR = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/reports/figures/step_all")
OUTDIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "figure.dpi": 300, "savefig.dpi": 300, "savefig.bbox": "tight",
    "svg.fonttype": "none", "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.5, "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "grid.alpha": 0.3,
})

EXP_COLORS = {
    "E24": "#484878", "E25": "#7884B4", "E26": "#B4C0E4", "E27": "#E4CCD8",
    "E28": "#CC6677", "E29": "#88CCEE", "E30": "#44AA99", "E31": "#DDCC77",
}
STRAT_COLORS = {"supervised": "#0F4D92", "grpo": "#E53935"}
PASS_COLORS = {"PASS": "#2E9E44", "FAIL": "#E53935"}

EXPERIMENTS = {
    "E24": "glare_e24_patent_split_20260629",
    "E25": "glare_e25_warmlr_optimization_20260629",
    "E26": "glare_e26_patent_320_83_20260630",
    "E27": "glare_e27_warmlr_320_83_20260630",
    "E28": "glare_e28_lr_sweep_20260629",
    "E29": "glare_e29_retro_modern_20260629",
    "E30": "glare_e30_grpo_20260630",
    "E31": "glare_e31_paper_grpo_20260630",
}

LR_MAP = {
    "lr_5e4": 5e-4, "lr_7e4": 7e-4, "lr_8e4": 8e-4, "lr_9e4": 9e-4,
    "lr_1p5e3": 1.5e-3, "lr_1e3": 1e-3,
    "warm_lr": 1e-3, "fb_amp": 3e-3, "high_weight": 3e-4,
    "curriculum": 3e-3, "combo_moderate": 1e-3,
    "combo_lr5e4_w3_r2": 5e-4, "half_decoy_lr5e4_r2": 5e-4,
    "deep_r0": 7e-4, "ens5_r0": 7e-4, "hard_neg_r1": 7e-4,
    "two_phase_r1": 3e-4, "lr_anneal_r1": 3e-4,
    "fb_amp_r2": 3e-3, "lr_7e4_r2": 7e-4, "lr_8e4_r2": 8e-4,
    "warm_lr_r2": 1e-3, "warm_lr_replica": 1e-3,
    "lr_7e4_10ep": 7e-4, "lr_7e4_grpo": 7e-4,
    "half_decoy": 1e-3,
}
LR_MAP.update({f"grpo_{s}": v for s, v in {
    "default": 7e-4, "high_lambda": 7e-4, "low_beta": 7e-4, "5e4": 5e-4,
    "half_decoy": 7e-4, "r2": 7e-4, "two_phase": 3e-4, "hard_neg": 7e-4,
    "3e4": 3e-4, "1e3": 1e-3, "10ep": 7e-4, "3K_decoy": 7e-4,
    "ens5": 7e-4, "combo_w2": 5e-4, "hard_neg_3K": 7e-4,
    "half_decoy_5e4": 5e-4, "r2_high_lam": 7e-4,
}.items()})
LR_MAP.update({"sup_5e4": 5e-4, "sup_7e4": 7e-4, "sup_half_decoy_5e4": 5e-4})

DECOY_MAP = {
    "grpo_half_decoy": "Half (5K)", "grpo_3K_decoy": "3K",
    "grpo_hard_neg": "Hard Negative", "grpo_hard_neg_3K": "Hard Negative",
    "grpo_half_decoy_5e4": "Half (5K)", "sup_half_decoy_5e4": "Half (5K)",
    "grpo_two_phase": "Two-Phase", "two_phase_r1": "Two-Phase",
    "half_decoy": "Half (5K)", "half_decoy_lr5e4_r2": "Half (5K)",
    "hard_neg_r1": "Hard Negative",
    "e31_d50": "Tiny (50)", "e31_d100": "Tiny (100)", "e31_d200": "Tiny (200)", "e31_sup": "Tiny (100)",
}
DEFAULT_DECOY = "Full (10K)"

W_MAP = {"combo_moderate": 1.5, "combo_lr5e4_w3_r2": 3.0,
         "grpo_combo_w2": 2.0, "high_weight": 2.5}

GRPO_NAMES = {"grpo_default", "grpo_high_lambda", "grpo_low_beta", "grpo_5e4"}


def try_float(v, default=3e-4):
    """Robust float conversion."""
    if v is None: return default
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, list): v = v[-1] if v else default
    if isinstance(v, str):
        if v.startswith("["):
            try: v = ast.literal_eval(v)[-1]
            except: return default
        else:
            try: return float(v)
            except: return default
    try: return float(v)
    except: return default


def parse_config(name, cfg_dict):
    """Extract all params from config name and optional config dict."""
    cfg = cfg_dict or {}

    # Strategy
    strat = cfg.get("r1_strategy") or cfg.get("strat") or "supervised"
    if name.startswith("e31_"):
        strat = cfg.get("strat", "grpo")
        if name == "e31_sup": strat = "supervised"
    if name in GRPO_NAMES: strat = "grpo"

    # LR
    lr = try_float(cfg.get("r1_lr") or cfg.get("lr") or LR_MAP.get(name, 3e-4))

    # Decoy
    dc = cfg.get("r1_decoy") or cfg.get("dc")
    if dc is None:
        dc = DECOY_MAP.get(name, DEFAULT_DECOY)
    elif isinstance(dc, (int, float)):
        dc = f"Tiny ({int(dc)})"
    dc_family = dc if isinstance(dc, str) and not dc.isdigit() else DEFAULT_DECOY

    # Epochs
    ep = 5
    if cfg and "r1_ep" in cfg:
        ep = cfg["r1_ep"]
    elif cfg and "ep" in cfg:
        ep = cfg["ep"]
    if isinstance(ep, list): ep = sum(ep)
    if isinstance(ep, str) and ep.startswith("["):
        try: ep = sum(ast.literal_eval(ep))
        except: pass
    if "10ep" in name: ep = 10
    ep = int(ep)

    # ensemble
    ens = cfg.get("ens") or cfg.get("ensemble_size", 3)
    if ens is None: ens = 5 if "ens5" in name else 3
    ens = int(ens)

    # weight
    sw = cfg.get("strong_w_mult", 1.0) or 1.0
    if sw == 1.0 and name in W_MAP: sw = W_MAP[name]
    sw = float(sw)

    # Number of rounds
    has_r2 = "r2" in name.lower()
    is_two_phase = "two_phase" in name or "two_phase" in str(cfg.get("r1_decoy", ""))
    is_hard_neg = "hard_neg" in name or "hard_neg" in str(cfg.get("r1_decoy", ""))
    is_combo = sw > 1.0 or "combo" in name.lower()

    return {
        "strategy": strat, "lr_r1": lr, "decoy_family": dc_family,
        "epochs_r1": ep, "ensemble_size": ens, "strong_w": sw,
        "has_r2": has_r2, "is_two_phase": is_two_phase,
        "is_hard_neg": is_hard_neg, "is_combo": is_combo,
    }


def lr_family_label(lr):
    if lr <= 3.1e-4: return "3e-4"
    elif lr <= 5.1e-4: return "5e-4"
    elif lr <= 7.1e-4: return "7e-4"
    elif lr <= 8.1e-4: return "8e-4"
    elif lr <= 9.1e-4: return "9e-4"
    elif lr <= 1.1e-3: return "1e-3"
    elif lr <= 1.6e-3: return "1.5e-3"
    return "3e-3"


def build_dataframe():
    rows = []
    for exp, dname in EXPERIMENTS.items():
        exp_dir = ROOT / dname
        if not exp_dir.exists(): continue
        for sf in sorted(exp_dir.rglob("summary.json")):
            pname = sf.parent.name
            if "shared" in str(sf) or pname in ("", "master_summary.json"):
                continue
            try:
                raw = json.load(open(sf))
            except Exception:
                continue
            if not isinstance(raw, dict): continue

            name = raw.get("name", pname)
            rs = raw.get("rounds", [])
            if len(rs) < 2: continue

            cfg = raw.get("config") or {}
            params = parse_config(name, cfg)

            r0, r_last = rs[0], rs[-1]
            num_r = len(rs)

            rows.append({
                "experiment": exp, "config_name": name,
                "num_rounds": num_r,
                "strategy": params["strategy"],
                "lr_r1": params["lr_r1"], "lr_family": lr_family_label(params["lr_r1"]),
                "decoy_family": params["decoy_family"],
                "epochs_r1": params["epochs_r1"],
                "ensemble_size": params["ensemble_size"],
                "strong_w": params["strong_w"],
                "has_r2": params["has_r2"],
                "is_hard_neg": params["is_hard_neg"],
                "is_two_phase": params["is_two_phase"],
                "is_combo": params["is_combo"],
                "R0_ROC": r0.get("roc"), "R1_ROC": r_last.get("roc"),
                "R0_rank_strong": r0.get("rank_strong"),
                "R_final_rank_strong": r_last.get("rank_strong"),
                "R0_rank_all13": r0.get("rank_all13"),
                "R_final_rank_all13": r_last.get("rank_all13"),
                "delta_roc": raw.get("delta_roc"),
                "delta_rank_strong": raw.get("delta_rank_strong"),
                "delta_rank_all13": raw.get("delta_rank_all13"),
                "PASS": raw.get("success_rank_improved", False) and raw.get("success_roc_preserved", False),
            })

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["experiment", "config_name"])
    print(f"Compiled {len(df)} configs: PASS={df['PASS'].sum()}/{len(df)}")
    return df


def save_pub(fig, name):
    for fmt in ["png", "svg"]:
        fig.savefig(OUTDIR / f"{name}.{fmt}", format=fmt)
    plt.close(fig)


def add_label(ax, label):
    ax.text(-0.08, 1.05, label, transform=ax.transAxes, fontsize=10, fontweight="bold", va="top")


def style_ax(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.3, linewidth=0.3)


# ── FIGURE 1: Leaderboard ──
def fig1_leaderboard(df):
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.5))
    ax, ax2 = axes

    # Panel a: ΔROC vs ΔRank scatter
    add_label(ax, "a")
    for exp in sorted(df["experiment"].unique()):
        sub = df[df["experiment"] == exp]
        p = sub["PASS"]
        ax.scatter(sub.loc[~p, "delta_rank_strong"], sub.loc[~p, "delta_roc"],
                   c=EXP_COLORS[exp], marker="o", s=30, alpha=0.35, edgecolors="none")
        ax.scatter(sub.loc[p, "delta_rank_strong"], sub.loc[p, "delta_roc"],
                   c=EXP_COLORS[exp], marker="o", s=55, alpha=0.9,
                   edgecolors="white", linewidths=0.5, label=exp,
                   zorder=5)

    ax.axhline(y=-0.03, color="#767676", linestyle="--", lw=0.8, alpha=0.7)
    ax.axvline(x=0, color="#767676", linestyle="--", lw=0.8, alpha=0.7)
    ax.fill_between([-20000, 0], -0.03, 0.15, alpha=0.05, color="#2E9E44")
    ax.text(-15000, 0.13, "PASS zone", fontsize=6.5, color="#2E9E44", fontstyle="italic")
    ax.set_xlabel("Δ Rank-Strong (← improvement)")
    ax.set_ylabel("Δ ROC")
    ax.legend(frameon=False, fontsize=5.5, ncol=2, markerscale=0.7, loc="upper left")
    style_ax(ax)

    # Annotate top performers
    best = df.nlargest(5, "R1_ROC")
    for _, r in best.iterrows():
        dy = 0.008 if r["delta_rank_strong"] < -200 else 0.015
        ax.annotate(f'{r["experiment"]} {r["config_name"]}',
                    (r["delta_rank_strong"], r["delta_roc"]),
                    xytext=(r["delta_rank_strong"] + 100, r["delta_roc"] + dy),
                    fontsize=5, alpha=0.85,
                    arrowprops=dict(arrowstyle="->", color="#555", lw=0.3, connectionstyle="arc3,rad=0.1"))

    # Panel b: PASS rate by experiment
    add_label(ax2, "b")
    es = df.groupby("experiment").agg(total=("PASS", "count"), passed=("PASS", "sum")).reset_index()
    es["fail"] = es["total"] - es["passed"]
    x = np.arange(len(es))
    ax2.bar(x, es["passed"], 0.6, color="#2E9E44", alpha=0.8, label="PASS")
    ax2.bar(x, es["fail"], 0.6, bottom=es["passed"], color="#E53935", alpha=0.5, label="FAIL")
    for i, r in es.iterrows():
        ax2.text(i, r["total"] + 0.5, f'{int(r["passed"])}/{int(r["total"])}\n({r["passed"]/r["total"]*100:.0f}%)',
                ha="center", fontsize=6)
    ax2.set_xticks(x); ax2.set_xticklabels(es["experiment"])
    ax2.set_ylabel("Config count"); ax2.set_ylim(0, es["total"].max() + 4)
    ax2.legend(frameon=False, fontsize=6.5)
    style_ax(ax2)

    fig.tight_layout()
    save_pub(fig, "fig1_leaderboard")


# ── FIGURE 2: Method Family Comparison (ΔRank) ──
def fig2_method_families(df):
    families = [
        ("lr_family", "LR Strategy"),
        ("decoy_family", "Decoy Strategy"),
        ("epochs_r1", "Training Epochs"),
        ("has_r2", "Rounds (2 vs 3)"),
        ("strong_w", "Weight Multiplier"),
        ("is_hard_neg", "Hard Negative Mining"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(8.5, 7))

    for (col, title), ax in zip(families, axes.flatten()):
        df_p = df.copy()

        if col == "has_r2":
            df_p["cat"] = df_p["has_r2"].map({True: "3-Round", False: "2-Round"})
            order = ["2-Round", "3-Round"]
        elif col == "epochs_r1":
            df_p["cat"] = df_p["epochs_r1"].apply(lambda x: f"{int(x)} ep")
            order = sorted(df_p["cat"].unique())
        elif col == "strong_w":
            def wcat(w):
                if w <= 1.0: return "w=1.0"
                if w <= 1.6: return "w=1.5"
                if w <= 2.1: return "w=2.0"
                return "w≥2.5"
            df_p["cat"] = df_p["strong_w"].apply(wcat)
            order = ["w=1.0", "w=1.5", "w=2.0", "w≥2.5"]
        elif col == "is_hard_neg":
            df_p["cat"] = df_p["is_hard_neg"].map({True: "Hard Neg", False: "Standard"})
            order = ["Standard", "Hard Neg"]
        else:
            df_p["cat"] = df_p[col]
            order = sorted(df_p["cat"].unique())

        order = [o for o in order if (df_p["cat"] == o).sum() > 0]
        palette = sns.color_palette("vlag", len(order)) if len(order) > 1 else ["#7884B4"]

        sns.boxplot(data=df_p, y="cat", x="delta_rank_strong", order=order,
                     ax=ax, palette=palette, width=0.5, linewidth=0.5, fliersize=0,
                     showmeans=True, meanprops={"marker": "D", "markersize": 4, "markerfacecolor": "#E53935"})
        sns.stripplot(data=df_p, y="cat", x="delta_rank_strong", order=order,
                       ax=ax, color="black", alpha=0.2, size=2.5, jitter=True)
        ax.axvline(x=0, color="#767676", linestyle="--", lw=0.6)

        # K-W test
        groups = [df_p[df_p["cat"] == o]["delta_rank_strong"].dropna().values for o in order if (df_p["cat"] == o).sum() > 3]
        p_str = ""
        if len(groups) >= 2:
            try:
                h, p = sp_stats.kruskal(*groups)
                p_str = f" (K-W p={p:.3f})" if p >= 0.001 else " (K-W p<0.001)"
            except: pass
        ax.set_title(f"{title}{p_str}", fontsize=7.5, color="#555")
        ax.set_ylabel(""); ax.set_xlabel("Δ Rank-Strong (← improvement)")
        style_ax(ax)

    fig.tight_layout(pad=1.5)
    save_pub(fig, "fig2_method_families_rank")


# ── FIGURE 3: Method Family Comparison (ΔROC) ──
def fig3_method_families_roc(df):
    families = [
        ("lr_family", "LR Strategy"),
        ("decoy_family", "Decoy Strategy"),
        ("epochs_r1", "Training Epochs"),
        ("has_r2", "Rounds (2 vs 3)"),
        ("strong_w", "Weight Multiplier"),
        ("is_hard_neg", "Hard Negative Mining"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(8.5, 7))

    for (col, title), ax in zip(families, axes.flatten()):
        df_p = df.copy()

        if col == "has_r2":
            df_p["cat"] = df_p["has_r2"].map({True: "3-Round", False: "2-Round"})
            order = ["2-Round", "3-Round"]
        elif col == "epochs_r1":
            df_p["cat"] = df_p["epochs_r1"].apply(lambda x: f"{int(x)} ep")
            order = sorted(df_p["cat"].unique())
        elif col == "strong_w":
            def wcat(w):
                if w <= 1.0: return "w=1.0"
                if w <= 1.6: return "w=1.5"
                if w <= 2.1: return "w=2.0"
                return "w≥2.5"
            df_p["cat"] = df_p["strong_w"].apply(wcat)
            order = ["w=1.0", "w=1.5", "w=2.0", "w≥2.5"]
        elif col == "is_hard_neg":
            df_p["cat"] = df_p["is_hard_neg"].map({True: "Hard Neg", False: "Standard"})
            order = ["Standard", "Hard Neg"]
        else:
            df_p["cat"] = df_p[col]
            order = sorted(df_p["cat"].unique())

        order = [o for o in order if (df_p["cat"] == o).sum() > 0]
        palette = sns.color_palette("vlag", len(order)) if len(order) > 1 else ["#7884B4"]

        sns.boxplot(data=df_p, y="cat", x="delta_roc", order=order,
                     ax=ax, palette=palette, width=0.5, linewidth=0.5, fliersize=0,
                     showmeans=True, meanprops={"marker": "D", "markersize": 4, "markerfacecolor": "#E53935"})
        sns.stripplot(data=df_p, y="cat", x="delta_roc", order=order,
                       ax=ax, color="black", alpha=0.2, size=2.5, jitter=True)
        ax.axvline(x=-0.03, color="#E53935", linestyle=":", lw=0.6, alpha=0.7)
        ax.axvline(x=0, color="#767676", linestyle="--", lw=0.6)
        ax.axvspan(-0.03, 0.03, alpha=0.03, color="#2E9E44")

        groups = [df_p[df_p["cat"] == o]["delta_roc"].dropna().values for o in order if (df_p["cat"] == o).sum() > 3]
        p_str = ""
        if len(groups) >= 2:
            try:
                h, p = sp_stats.kruskal(*groups)
                p_str = f" (K-W p={p:.3f})" if p >= 0.001 else " (K-W p<0.001)"
            except: pass
        ax.set_title(f"{title}{p_str}", fontsize=7.5, color="#555")
        ax.set_ylabel(""); ax.set_xlabel("Δ ROC")
        style_ax(ax)

    fig.tight_layout(pad=1.5)
    save_pub(fig, "fig3_method_families_roc")


# ── FIGURE 4: GRPO vs Supervised ──
def fig4_grpo(df):
    fig, axes = plt.subplots(1, 3, figsize=(8.5, 3.5))
    ax0, ax1, ax2 = axes

    # Panel a: GRPO collapse (E30 W1) vs Supervised
    add_label(ax0, "a")
    grpo_w1 = df[df["config_name"].isin(GRPO_NAMES)]
    sup_e30 = df[(df["experiment"] == "E30") & (~df["config_name"].isin(GRPO_NAMES))]

    bp0 = ax0.boxplot([grpo_w1["delta_roc"], sup_e30["delta_roc"]], positions=[0, 1],
                       widths=0.4, patch_artist=True, showmeans=True,
                       meanprops={"marker": "D", "markersize": 5, "markerfacecolor": "#E53935"})
    bp0["boxes"][0].set_facecolor("#E53935"); bp0["boxes"][0].set_alpha(0.5)
    bp0["boxes"][1].set_facecolor("#0F4D92"); bp0["boxes"][1].set_alpha(0.5)
    ax0.scatter(np.random.normal(0, 0.03, len(grpo_w1)), grpo_w1["delta_roc"],
                c="#E53935", alpha=0.5, s=10, zorder=5)
    ax0.scatter(np.random.normal(1, 0.03, len(sup_e30)), sup_e30["delta_roc"],
                c="#0F4D92", alpha=0.5, s=10, zorder=5)
    ax0.axhline(y=-0.03, color="#767676", linestyle="--", lw=0.6)
    ax0.axhline(y=0, color="#767676", linestyle="-", lw=0.3, alpha=0.5)
    ax0.set_xticks([0, 1])
    ax0.set_xticklabels(["GRPO\n(E30 W1, collapsed)", "Supervised\n(E30 W2-5)"], fontsize=6)
    ax0.set_ylabel("Δ ROC")
    try:
        u, p = sp_stats.mannwhitneyu(grpo_w1["delta_roc"], sup_e30["delta_roc"])
        ax0.set_title(f"GRPO Collapse vs Supervised (M-W p={p:.4f})", fontsize=7.5, color="#555")
    except:
        ax0.set_title("GRPO Collapse vs Supervised", fontsize=7.5)
    style_ax(ax0)

    # Panel b: E31 — fixed GRPO vs supervised
    add_label(ax1, "b")
    e31 = df[df["experiment"] == "E31"]
    for _, r in e31.iterrows():
        c = STRAT_COLORS.get(r["strategy"], "#888")
        m = "^" if r["strategy"] == "grpo" else "s"
        ax1.scatter(r["delta_rank_strong"], r["delta_roc"], c=c, marker=m,
                    s=80, edgecolors="white", lw=0.5, zorder=5)
        lbl = r["config_name"].replace("e31_", "")
        ax1.annotate(lbl, (r["delta_rank_strong"], r["delta_roc"]),
                     xytext=(r["delta_rank_strong"] + 1, r["delta_roc"] + 0.001),
                     fontsize=6)
    ax1.axhline(y=-0.03, color="#767676", linestyle="--", lw=0.6)
    ax1.axvline(x=0, color="#767676", linestyle="--", lw=0.6)
    ax1.set_xlabel("Δ Rank-Strong"); ax1.set_ylabel("Δ ROC")
    ax1.set_title("E31: Fixed GRPO (tiny decoy + no norm)", fontsize=7.5)
    ax1.legend(handles=[
        Line2D([0], [0], marker="^", color="w", markerfacecolor=STRAT_COLORS["grpo"], markersize=6, label="GRPO"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=STRAT_COLORS["supervised"], markersize=6, label="Supervised"),
    ], frameon=False, fontsize=6)
    style_ax(ax1)

    # Panel c: Final ROC vs Rank-Strong bubble
    add_label(ax2, "c")
    grpo_all = df[df["strategy"] == "grpo"]
    sup_all = df[df["strategy"] != "grpo"]
    ax2.scatter(sup_all["R_final_rank_strong"], sup_all["R1_ROC"], c="#0F4D92", alpha=0.3,
                s=30, label="Supervised", edgecolors="none")
    ax2.scatter(grpo_all["R_final_rank_strong"], grpo_all["R1_ROC"], c="#E53935", alpha=0.6,
                s=40, marker="^", label="GRPO", edgecolors="white", lw=0.3)
    ax2.set_xlabel("Final Rank-Strong (↓ better)")
    ax2.set_ylabel("Final ROC")
    ax2.set_title("ROC vs Ranking: All 60 Configs", fontsize=7.5)
    ax2.legend(frameon=False, fontsize=6)
    style_ax(ax2)

    fig.tight_layout(pad=1.5)
    save_pub(fig, "fig4_grpo_comparison")


# ── FIGURE 5: Top Configs Bar Chart ──
def fig5_top_configs(df):
    pass_df = df[df["PASS"]].copy()
    pass_df["combined"] = -pass_df["delta_rank_strong"] / 100 + pass_df["delta_roc"] * 100
    top = pass_df.nlargest(15, "combined")

    fig, ax = plt.subplots(figsize=(8, 5))
    y = range(len(top))
    colors = [EXP_COLORS.get(e, "#888") for e in top["experiment"]]
    ax.barh(y, top["combined"], color=colors, alpha=0.85, height=0.6)

    for i, (_, r) in enumerate(top.iterrows()):
        label = f'{r["experiment"]} {r["config_name"]}'
        ax.text(-0.3, i, label, ha="right", va="center", fontsize=6, family="monospace")
        info = f'ROC={r["R1_ROC"]:.3f}  ΔROC={r["delta_roc"]:+.3f}  ΔRank={r["delta_rank_strong"]:+.0f}  '
        if r["num_rounds"] >= 3: info += "3-round "
        if r["is_hard_neg"]: info += "hard-neg "
        if r["is_combo"]: info += "combo "
        ax.text(r["combined"] + 0.05, i, info, ha="left", va="center", fontsize=5, color="#555")

    ax.set_yticks([])
    ax.set_xlabel("Combined Score (−ΔRank/100 + ΔROC×100)")
    ax.axvline(x=0, color="#767676", lw=0.5, linestyle="--")
    ax.legend(handles=[mpatches.Patch(facecolor=c, alpha=0.85, label=e) for e, c in EXP_COLORS.items()],
              frameon=False, fontsize=6, ncol=4, loc="lower right")
    ax.set_title("Top 15 PASS Configs by Combined Score", fontsize=9)
    style_ax(ax)
    fig.tight_layout()
    save_pub(fig, "fig5_top_configs")


# ── FIGURE 6: Heatmap ──
def fig6_heatmap(df):
    df_s = df.sort_values(["experiment", "delta_rank_strong"]).copy()
    metrics = ["R0_ROC", "R1_ROC", "R0_rank_strong", "R_final_rank_strong",
               "delta_roc", "delta_rank_strong", "delta_rank_all13"]
    labels = ["R0 ROC", "R1 ROC", "R0 Rank", "Final Rank",
              "Δ ROC", "Δ Rank-Str", "Δ Rank-All13"]

    data = df_s[metrics].copy()
    data_norm = data.copy()
    for col in metrics:
        m, s = data[col].mean(), data[col].std()
        if s > 0: data_norm[col] = (data[col] - m) / s

    n = len(df_s)
    fig, ax = plt.subplots(figsize=(7.5, max(8, n * 0.22)))
    cmap = sns.diverging_palette(240, 10, as_cmap=True)
    im = ax.imshow(data_norm.values, aspect="auto", cmap=cmap, vmin=-2.5, vmax=2.5)

    ax.set_xticks(range(len(metrics))); ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=6.5)
    ax.set_yticks(range(n))
    ax.set_yticklabels([f"{r['experiment']} {r['config_name'][:22]}" for _, r in df_s.iterrows()], fontsize=5)

    for i, (_, r) in enumerate(df_s.iterrows()):
        c = PASS_COLORS["PASS"] if r["PASS"] else PASS_COLORS["FAIL"]
        ax.annotate("✓" if r["PASS"] else "✗", (len(metrics) + 0.2, i),
                    fontsize=7, color=c, ha="center", va="center", weight="bold")

    cbar = fig.colorbar(im, ax=ax, shrink=0.5, aspect=30, pad=0.01)
    cbar.set_label("Z-score", fontsize=7); cbar.ax.tick_params(labelsize=6)
    ax.set_title(f"E24-E31 Full Heatmap ({n} configs)", fontsize=8.5, pad=8)
    fig.tight_layout(pad=1.0)
    save_pub(fig, "fig6_heatmap")


# ── Main ──
if __name__ == "__main__":
    print("Building master dataframe...")
    df = build_dataframe()
    df.to_csv(OUTDIR / "compiled_data.csv", index=False)

    print("Generating figures...")
    fig1_leaderboard(df)
    print("  ✓ fig1_leaderboard")
    fig2_method_families(df)
    print("  ✓ fig2_method_families_rank")
    fig3_method_families_roc(df)
    print("  ✓ fig3_method_families_roc")
    fig4_grpo(df)
    print("  ✓ fig4_grpo_comparison")
    fig5_top_configs(df)
    print("  ✓ fig5_top_configs")
    fig6_heatmap(df)
    print("  ✓ fig6_heatmap")

    # Summary stats
    report = {
        "total": len(df),
        "passed": int(df["PASS"].sum()),
        "pass_rate": f"{df['PASS'].mean()*100:.0f}%",
        "best_roc": float(df["R1_ROC"].max()),
        "best_roc_config": str(df.loc[df["R1_ROC"].idxmax(), "config_name"]),
        "best_rank": float(df["delta_rank_strong"].min()),
        "best_rank_config": str(df.loc[df["delta_rank_strong"].idxmin(), "config_name"]),
        "by_experiment": {
            exp: {"total": int(len(g)), "passed": int(g["PASS"].sum()),
                  "best_roc": float(g["R1_ROC"].max())}
            for exp, g in df.groupby("experiment")
        }
    }
    with open(OUTDIR / "summary.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(df)} configs, {report['pass_rate']} PASS")
    print(f"  Best ROC: {report['best_roc_config']} ({report['best_roc']:.3f})")
    print(f"  Best Rank: {report['best_rank_config']} ({report['best_rank']:.0f})")
    print(f"  Output: {OUTDIR}/")
