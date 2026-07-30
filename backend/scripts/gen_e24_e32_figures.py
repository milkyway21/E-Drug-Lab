#!/usr/bin/env python3
"""E24-E32 visualization — 8 Nature-style figures, reads compiled_data.csv directly."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import json, ast
from scipy import stats as sp_stats

CSV_PATH = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/reports/figures/step_all/compiled_data.csv")
OUTDIR  = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/reports/figures/step_all")
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
    "E24":"#484878","E25":"#7884B4","E26":"#B4C0E4","E27":"#E4CCD8",
    "E28":"#CC6677","E29":"#88CCEE","E30":"#44AA99","E31":"#DDCC77",
    "E32":"#117733",
}
STRAT_COLORS = {"supervised":"#0F4D92","grpo":"#E53935"}
PASS_COLORS  = {"PASS":"#2E9E44","FAIL":"#E53935"}
SELECT_COLORS = {"greedy":"#E41A1C","grpo":"#377EB8","uncertainty":"#4DAF4A","random":"#984EA3","ts":"#FF7F00","-":"#999999"}

LR_MAP = {}
for k,v in {
    "lr_5e4":5e-4,"lr_7e4":7e-4,"lr_8e4":8e-4,"lr_9e4":9e-4,
    "lr_1p5e3":1.5e-3,"lr_1e3":1e-3,
    "warm_lr":1e-3,"fb_amp":3e-3,"high_weight":3e-4,
    "curriculum":3e-3,"combo_moderate":1e-3,
    "combo_lr5e4_w3_r2":5e-4,"half_decoy_lr5e4_r2":5e-4,
    "deep_r0":7e-4,"ens5_r0":7e-4,"hard_neg_r1":7e-4,
    "two_phase_r1":3e-4,"lr_anneal_r1":3e-4,
    "fb_amp_r2":3e-3,"lr_7e4_r2":7e-4,"lr_8e4_r2":8e-4,
    "warm_lr_r2":1e-3,"warm_lr_replica":1e-3,
    "lr_7e4_10ep":7e-4,"lr_7e4_grpo":7e-4,
    "half_decoy":1e-3,
}.items(): LR_MAP[k]=v
for k,v in {
    "default":7e-4,"high_lambda":7e-4,"low_beta":7e-4,"5e4":5e-4,
    "half_decoy":7e-4,"r2":7e-4,"two_phase":3e-4,"hard_neg":7e-4,
    "3e4":3e-4,"1e3":1e-3,"10ep":7e-4,"3K_decoy":7e-4,
    "ens5":7e-4,"combo_w2":5e-4,"hard_neg_3K":7e-4,
    "half_decoy_5e4":5e-4,"r2_high_lam":7e-4,
}.items(): LR_MAP[f"grpo_{k}"]=v
for k,v in {"sup_5e4":5e-4,"sup_7e4":7e-4,"sup_half_decoy_5e4":5e-4}.items(): LR_MAP[k]=v

DECOY_MAP = {
    "grpo_half_decoy":"Half (5K)","grpo_3K_decoy":"3K",
    "grpo_hard_neg":"Hard Negative","grpo_hard_neg_3K":"Hard Negative",
    "grpo_half_decoy_5e4":"Half (5K)","sup_half_decoy_5e4":"Half (5K)",
    "grpo_two_phase":"Two-Phase","two_phase_r1":"Two-Phase",
    "half_decoy":"Half (5K)","half_decoy_lr5e4_r2":"Half (5K)",
    "hard_neg_r1":"Hard Negative",
    "e31_d50":"Tiny (50)","e31_d100":"Tiny (100)","e31_d200":"Tiny (200)","e31_sup":"Tiny (100)",
}
DEFAULT_DECOY = "Full (10K)"
W_MAP = {"combo_moderate":1.5,"combo_lr5e4_w3_r2":3.0,"grpo_combo_w2":2.0,"high_weight":2.5}
GRPO_NAMES = {"grpo_default","grpo_high_lambda","grpo_low_beta","grpo_5e4"}

def save_pub(fig, name):
    for fmt in ["png","svg"]:
        fig.savefig(OUTDIR / f"{name}.{fmt}", format=fmt)
    plt.close(fig)

def add_label(ax, label):
    ax.text(-0.08, 1.05, label, transform=ax.transAxes, fontsize=10, fontweight="bold", va="top")

def style_ax(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.3, linewidth=0.3)

def lr_family_label(lr_val):
    if lr_val <= 3.1e-4: return "3e-4"
    elif lr_val <= 5.1e-4: return "5e-4"
    elif lr_val <= 7.1e-4: return "7e-4"
    elif lr_val <= 8.1e-4: return "8e-4"
    elif lr_val <= 9.1e-4: return "9e-4"
    elif lr_val <= 1.1e-3: return "1e-3"
    elif lr_val <= 1.6e-3: return "1.5e-3"
    return "3e-3"

def parse_lr(v):
    if v is None or (isinstance(v,float) and np.isnan(v)): return 3e-4
    if isinstance(v,(int,float)): return float(v)
    if isinstance(v,str):
        s=v.strip()
        if s.startswith("["):
            try: parts=ast.literal_eval(s); return float(parts[-1]) if parts else 3e-4
            except: return 3e-4
        try: return float(s)
        except: return 3e-4
    return 3e-4

def derive_features(row):
    name=str(row["config_name"]); exp=str(row["experiment"])
    n_rounds=int(row["num_rounds"]); lr_val=parse_lr(row["lr_r1"])
    feat={"lr_family":lr_family_label(lr_val),"epochs_r1":int(row["epochs_r1"]),"ensemble_size":int(row["ensemble_size"])}
    if exp=="E32":
        feat["decoy_family"]="Full (10K)"; feat["has_r2"]=True
        feat["is_hard_neg"]="hard_neg" in name.lower(); feat["is_two_phase"]=False
        feat["is_combo"]=False; feat["strong_w"]=1.0
        feat["select_strategy"]=str(row.get("select_strategy","-")) if pd.notna(row.get("select_strategy")) else "-"
        feat["train_strategy"]=str(row.get("train_strategy","supervised")) if pd.notna(row.get("train_strategy")) else "supervised"
        feat["strategy"]=feat["train_strategy"]
        return feat
    dc=DECOY_MAP.get(name,DEFAULT_DECOY)
    feat["decoy_family"]=dc
    feat["has_r2"]="r2" in name.lower() or n_rounds>=3
    feat["is_hard_neg"]="hard_neg" in name or "hard_neg" in str(dc)
    feat["is_two_phase"]="two_phase" in name or "Two-Phase" in str(dc)
    sw=W_MAP.get(name,1.0); feat["strong_w"]=float(sw)
    feat["is_combo"]=sw>1.0 or "combo" in name.lower()
    feat["select_strategy"]="-"
    feat["train_strategy"]=str(row.get("strategy","supervised")) if pd.notna(row.get("strategy")) else "supervised"
    return feat

def load_dataframe():
    df=pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} rows from {CSV_PATH.name}")
    df["select_strategy"]=df["select_strategy"].fillna("-")
    mask=df["train_strategy"].isna(); df.loc[mask,"train_strategy"]=df.loc[mask,"strategy"]
    mask_s=df["strategy"].isna(); df.loc[mask_s,"strategy"]=df.loc[mask_s,"train_strategy"]
    df["PASS"]=df["PASS"].astype(bool)
    features=df.apply(derive_features, axis=1, result_type="expand")
    for col in features.columns: df[col]=features[col]
    df["strategy"]=df["strategy"].fillna("supervised")
    df["delta_roc"]=df["Delta_ROC"]; df["delta_rank_strong"]=df["Delta_Rank_Strong"]
    df["delta_rank_all13"]=df["Delta_Rank_All13"]; df["delta_prauc"]=df["Delta_PRAUC"]
    df["R0_rank_strong"]=df["R0_Rank_Strong"]; df["R_final_rank_strong"]=df["Rf_Rank_Strong"]
    df["R0_rank_all13"]=df["R0_Rank_All13"]; df["R_final_rank_all13"]=df["Rf_Rank_All13"]
    n_e32=(df["experiment"]=="E32").sum()
    print(f"  E24-E31: {len(df)-n_e32} configs, E32: {n_e32} configs, PASS={df['PASS'].sum()}/{len(df)}")
    return df

# ═══ FIGURE 1: Leaderboard ═══
def fig1_leaderboard(df):
    fig,axes=plt.subplots(1,2,figsize=(9,4.5)); ax,ax2=axes
    add_label(ax,"a")
    for exp in sorted(df["experiment"].unique()):
        sub=df[df["experiment"]==exp]; p=sub["PASS"]
        ax.scatter(sub.loc[~p,"delta_rank_strong"],sub.loc[~p,"delta_roc"],
                   c=EXP_COLORS[exp],marker="o",s=30,alpha=0.35,edgecolors="none")
        ax.scatter(sub.loc[p,"delta_rank_strong"],sub.loc[p,"delta_roc"],
                   c=EXP_COLORS[exp],marker="o",s=55,alpha=0.9,
                   edgecolors="white",linewidths=0.5,label=exp,zorder=5)
    ax.axhline(y=-0.03,color="#767676",linestyle="--",lw=0.8,alpha=0.7)
    ax.axvline(x=0,color="#767676",linestyle="--",lw=0.8,alpha=0.7)
    ax.fill_between([-20000,0],-0.03,0.3,alpha=0.05,color="#2E9E44")
    ax.text(-15000,0.22,"PASS zone",fontsize=6.5,color="#2E9E44",fontstyle="italic")
    ax.set_xlabel("Delta Rank-Strong (arrowleft improvement)"); ax.set_ylabel("Delta ROC")
    ax.legend(frameon=False,fontsize=5,ncol=3,markerscale=0.7,loc="upper left")
    ax.annotate("E32 pool ~10K  |  E24-E31 pool ~48K",xy=(0.98,0.02),xycoords="axes fraction",
                fontsize=5.5,color="#767676",ha="right",va="bottom",
                bbox=dict(boxstyle="round,pad=0.3",facecolor="white",alpha=0.7,edgecolor="#ccc",lw=0.3))
    best5=df.nlargest(5,"R1_ROC")
    for _,r in best5.iterrows():
        dy=0.012 if r["delta_rank_strong"]<-200 else 0.02
        ax.annotate(f'{r["experiment"]} {r["config_name"]}',
                    (r["delta_rank_strong"],r["delta_roc"]),
                    xytext=(r["delta_rank_strong"]+100,r["delta_roc"]+dy),
                    fontsize=5,alpha=0.85,
                    arrowprops=dict(arrowstyle="->",color="#555",lw=0.3,connectionstyle="arc3,rad=0.1"))
    style_ax(ax)
    add_label(ax2,"b")
    es=df.groupby("experiment").agg(total=("PASS","count"),passed=("PASS","sum")).reset_index()
    es["fail"]=es["total"]-es["passed"]; x=np.arange(len(es))
    ax2.bar(x,es["passed"],0.5,color="#2E9E44",alpha=0.8,label="PASS",edgecolor="white",lw=0.3)
    ax2.bar(x,es["fail"],0.5,bottom=es["passed"],color="#E53935",alpha=0.4,label="FAIL",edgecolor="white",lw=0.3)
    for i,r in es.iterrows():
        ax2.text(i,r["total"]+0.5,f'{int(r["passed"])}/{int(r["total"])}\n({r["passed"]/r["total"]*100:.0f}%)',ha="center",fontsize=6)
    ax2.set_xticks(x); ax2.set_xticklabels(es["experiment"],fontsize=7)
    ax2.set_ylabel("Config count"); ax2.set_ylim(0,es["total"].max()+4)
    ax2.legend(frameon=False,fontsize=6.5); style_ax(ax2)
    fig.tight_layout(); save_pub(fig,"fig1_leaderboard")

# ═══ FIGURE 2: Method Families (Delta Rank, 2x4) ═══
def fig2_method_families(df):
    families=[
        ("lr_family","LR Strategy"),("decoy_family","Decoy Strategy"),
        ("epochs_r1","Training Epochs"),("has_r2","Rounds (2 vs >=3)"),
        ("strong_w","Weight Multiplier"),("is_hard_neg","Hard Negative Mining"),
        ("select_strategy","AL Select Strategy"),("train_strategy","Train Strategy"),
    ]
    fig,axes=plt.subplots(2,4,figsize=(11,7.5))
    for (col,title),ax in zip(families,axes.flatten()):
        dp=df.copy()
        if col=="has_r2":
            dp["cat"]=dp["has_r2"].map({True:">=3-Round",False:"2-Round"}); order=["2-Round",">=3-Round"]
        elif col=="epochs_r1":
            dp["cat"]=dp["epochs_r1"].apply(lambda x:f"{int(x)} ep"); order=sorted(dp["cat"].unique(),key=lambda s:int(s.split()[0]))
        elif col=="strong_w":
            def wcat(w):
                if w<=1.0: return "w=1.0"
                if w<=1.6: return "w=1.5"
                if w<=2.1: return "w=2.0"
                return "w>=2.5"
            dp["cat"]=dp["strong_w"].apply(wcat); order=["w=1.0","w=1.5","w=2.0","w>=2.5"]
        elif col=="is_hard_neg":
            dp["cat"]=dp["is_hard_neg"].map({True:"Hard Neg",False:"Standard"}); order=["Standard","Hard Neg"]
        elif col=="select_strategy":
            dp["cat"]=dp["select_strategy"]; order=[o for o in ["greedy","grpo","uncertainty","random","ts","-"] if o in dp["cat"].unique()]
        elif col=="train_strategy":
            dp["cat"]=dp["train_strategy"]; order=sorted(dp["cat"].unique())
        else:
            dp["cat"]=dp[col]; order=sorted(dp["cat"].unique())
        order=[o for o in order if (dp["cat"]==o).sum()>0]
        if col=="select_strategy": pal=[SELECT_COLORS.get(o,"#888") for o in order]
        elif col=="train_strategy": pal=[STRAT_COLORS.get(o,"#888") for o in order]
        elif len(order)>1: pal=sns.color_palette("vlag",len(order))
        else: pal=["#7884B4"]
        sns.boxplot(data=dp,y="cat",x="delta_rank_strong",order=order,
                     hue="cat",ax=ax,palette=pal,legend=False,
                     width=0.5,linewidth=0.5,fliersize=0,
                     showmeans=True,meanprops={"marker":"D","markersize":4,"markerfacecolor":"#E53935"})
        sns.stripplot(data=dp,y="cat",x="delta_rank_strong",order=order,
                       hue="cat",ax=ax,color="black",alpha=0.2,size=2.5,jitter=True,legend=False)
        ax.axvline(x=0,color="#767676",linestyle="--",lw=0.6)
        groups=[dp[dp["cat"]==o]["delta_rank_strong"].dropna().values for o in order if (dp["cat"]==o).sum()>3]
        p_str=""
        if len(groups)>=2:
            try: h,p=sp_stats.kruskal(*groups); p_str=f" (K-W p={p:.3f})" if p>=0.001 else " (K-W p<0.001)"
            except: pass
        ax.set_title(f"{title}{p_str}",fontsize=7.5,color="#555")
        ax.set_ylabel(""); ax.set_xlabel("Delta Rank-Strong (arrowleft improvement)"); style_ax(ax)
    fig.tight_layout(pad=1.5); save_pub(fig,"fig2_method_families_rank")

# ═══ FIGURE 3: Method Families (Delta ROC, 2x4) ═══
def fig3_method_families_roc(df):
    families=[
        ("lr_family","LR Strategy"),("decoy_family","Decoy Strategy"),
        ("epochs_r1","Training Epochs"),("has_r2","Rounds (2 vs >=3)"),
        ("strong_w","Weight Multiplier"),("is_hard_neg","Hard Negative Mining"),
        ("select_strategy","AL Select Strategy"),("train_strategy","Train Strategy"),
    ]
    fig,axes=plt.subplots(2,4,figsize=(11,7.5))
    for (col,title),ax in zip(families,axes.flatten()):
        dp=df.copy()
        if col=="has_r2":
            dp["cat"]=dp["has_r2"].map({True:">=3-Round",False:"2-Round"}); order=["2-Round",">=3-Round"]
        elif col=="epochs_r1":
            dp["cat"]=dp["epochs_r1"].apply(lambda x:f"{int(x)} ep"); order=sorted(dp["cat"].unique(),key=lambda s:int(s.split()[0]))
        elif col=="strong_w":
            def wcat(w):
                if w<=1.0: return "w=1.0"
                if w<=1.6: return "w=1.5"
                if w<=2.1: return "w=2.0"
                return "w>=2.5"
            dp["cat"]=dp["strong_w"].apply(wcat); order=["w=1.0","w=1.5","w=2.0","w>=2.5"]
        elif col=="is_hard_neg":
            dp["cat"]=dp["is_hard_neg"].map({True:"Hard Neg",False:"Standard"}); order=["Standard","Hard Neg"]
        elif col=="select_strategy":
            dp["cat"]=dp["select_strategy"]; order=[o for o in ["greedy","grpo","uncertainty","random","ts","-"] if o in dp["cat"].unique()]
        elif col=="train_strategy":
            dp["cat"]=dp["train_strategy"]; order=sorted(dp["cat"].unique())
        else:
            dp["cat"]=dp[col]; order=sorted(dp["cat"].unique())
        order=[o for o in order if (dp["cat"]==o).sum()>0]
        if col=="select_strategy": pal=[SELECT_COLORS.get(o,"#888") for o in order]
        elif col=="train_strategy": pal=[STRAT_COLORS.get(o,"#888") for o in order]
        elif len(order)>1: pal=sns.color_palette("vlag",len(order))
        else: pal=["#7884B4"]
        sns.boxplot(data=dp,y="cat",x="delta_roc",order=order,
                     hue="cat",ax=ax,palette=pal,legend=False,
                     width=0.5,linewidth=0.5,fliersize=0,
                     showmeans=True,meanprops={"marker":"D","markersize":4,"markerfacecolor":"#E53935"})
        sns.stripplot(data=dp,y="cat",x="delta_roc",order=order,
                       hue="cat",ax=ax,color="black",alpha=0.2,size=2.5,jitter=True,legend=False)
        ax.axvline(x=-0.03,color="#E53935",linestyle=":",lw=0.6,alpha=0.7)
        ax.axvline(x=0,color="#767676",linestyle="--",lw=0.6)
        ax.axvspan(-0.03,0.03,alpha=0.03,color="#2E9E44")
        groups=[dp[dp["cat"]==o]["delta_roc"].dropna().values for o in order if (dp["cat"]==o).sum()>3]
        p_str=""
        if len(groups)>=2:
            try: h,p=sp_stats.kruskal(*groups); p_str=f" (K-W p={p:.3f})" if p>=0.001 else " (K-W p<0.001)"
            except: pass
        ax.set_title(f"{title}{p_str}",fontsize=7.5,color="#555")
        ax.set_ylabel(""); ax.set_xlabel("Delta ROC"); style_ax(ax)
    fig.tight_layout(pad=1.5); save_pub(fig,"fig3_method_families_roc")

# ═══ FIGURE 4: GRPO vs Supervised ═══
def fig4_grpo(df):
    fig,axes=plt.subplots(1,3,figsize=(9.5,3.8)); ax0,ax1,ax2=axes
    add_label(ax0,"a")
    e32_grpo_train=df[(df["experiment"]=="E32")&(df["train_strategy"]=="grpo")]
    grpo_w1=df[df["config_name"].isin(GRPO_NAMES)]
    sup_e30=df[(df["experiment"]=="E30")&(~df["config_name"].isin(GRPO_NAMES))]
    positions=[0,1,2]; labels=["GRPO\n(E30 W1)","Sup.\n(E30 W2-5)","GRPO-train\n(E32 AL)"]
    data_sets=[grpo_w1["delta_roc"],sup_e30["delta_roc"],e32_grpo_train["delta_roc"]]
    colors=["#E53935","#0F4D92","#117733"]
    bp=ax0.boxplot(data_sets,positions=positions,widths=0.4,patch_artist=True,
                    showmeans=True,meanprops={"marker":"D","markersize":5,"markerfacecolor":"#FFD700"})
    for patch,c in zip(bp["boxes"],colors): patch.set_facecolor(c); patch.set_alpha(0.5)
    for i,d in enumerate(data_sets):
        if len(d)>0: ax0.scatter(np.random.normal(positions[i],0.03,len(d)),d,c=colors[i],alpha=0.5,s=10,zorder=5)
    ax0.axhline(y=-0.03,color="#767676",linestyle="--",lw=0.6)
    ax0.axhline(y=0,color="#767676",linestyle="-",lw=0.3,alpha=0.5)
    ax0.set_xticks(positions); ax0.set_xticklabels(labels,fontsize=6); ax0.set_ylabel("Delta ROC")
    try:
        u,p=sp_stats.kruskal(*(d.dropna() for d in data_sets if len(d)>0))
        ax0.set_title(f"GRPO Collapse vs Supervised vs AL (K-W p={p:.3f})",fontsize=7.5,color="#555")
    except: ax0.set_title("GRPO Collapse vs Supervised vs AL",fontsize=7.5)
    style_ax(ax0)

    add_label(ax1,"b")
    e31=df[df["experiment"]=="E31"]; e32_sup=df[(df["experiment"]=="E32")&(df["train_strategy"]=="supervised")]
    for _,r in e31.iterrows():
        c=STRAT_COLORS.get(r["strategy"],"#888"); m="^" if r["strategy"]=="grpo" else "s"
        ax1.scatter(r["delta_rank_strong"],r["delta_roc"],c=c,marker=m,s=70,edgecolors="white",lw=0.5,zorder=5)
        ax1.annotate(r["config_name"].replace("e31_",""),(r["delta_rank_strong"],r["delta_roc"]),
                     xytext=(r["delta_rank_strong"]+1,r["delta_roc"]+0.001),fontsize=6)
    for _,r in e32_sup.iterrows():
        ax1.scatter(r["delta_rank_strong"],r["delta_roc"],c="#117733",marker="D",s=70,edgecolors="white",lw=0.5,zorder=6)
        ax1.annotate(r["config_name"].replace("e32_",""),(r["delta_rank_strong"],r["delta_roc"]),
                     xytext=(r["delta_rank_strong"]+5,r["delta_roc"]+0.002),fontsize=5.5,color="#117733")
    ax1.axhline(y=-0.03,color="#767676",linestyle="--",lw=0.6)
    ax1.axvline(x=0,color="#767676",linestyle="--",lw=0.6)
    ax1.set_xlabel("Delta Rank-Strong"); ax1.set_ylabel("Delta ROC")
    ax1.set_title("E31 Fixed-GRPO + E32 AL (sup-train)",fontsize=7.5)
    ax1.legend(handles=[
        Line2D([0],[0],marker="^",color="w",markerfacecolor=STRAT_COLORS["grpo"],markersize=6,label="GRPO (E31)"),
        Line2D([0],[0],marker="s",color="w",markerfacecolor=STRAT_COLORS["supervised"],markersize=6,label="Sup (E31)"),
        Line2D([0],[0],marker="D",color="w",markerfacecolor="#117733",markersize=6,label="Sup (E32 AL)"),
    ],frameon=False,fontsize=6); style_ax(ax1)

    add_label(ax2,"c")
    grpo_all=df[df["strategy"]=="grpo"]; sup_all=df[df["strategy"]!="grpo"]
    ax2.scatter(sup_all["R_final_rank_strong"],sup_all["R1_ROC"],c="#0F4D92",alpha=0.3,s=30,label="Supervised",edgecolors="none")
    ax2.scatter(grpo_all["R_final_rank_strong"],grpo_all["R1_ROC"],c="#E53935",alpha=0.5,s=40,marker="^",label="GRPO",edgecolors="white",lw=0.3)
    e32_all=df[df["experiment"]=="E32"]
    ax2.scatter(e32_all["R_final_rank_strong"],e32_all["R1_ROC"],c="#117733",alpha=0.8,s=50,marker="D",label="E32 (AL)",edgecolors="white",lw=0.4,zorder=6)
    ax2.set_xlabel("Final Rank-Strong (downarrow better)"); ax2.set_ylabel("Final ROC")
    ax2.set_title("ROC vs Ranking: All 70 Configs",fontsize=7.5)
    ax2.legend(frameon=False,fontsize=6)
    ax2.annotate("E32 pool ~10K | E24-E31 pool ~48K",xy=(0.98,0.98),xycoords="axes fraction",
                fontsize=5.5,color="#767676",ha="right",va="top",
                bbox=dict(boxstyle="round,pad=0.3",facecolor="white",alpha=0.7,edgecolor="#ccc",lw=0.3))
    style_ax(ax2)
    fig.tight_layout(pad=1.5); save_pub(fig,"fig4_grpo_comparison")

# ═══ FIGURE 5: Top Configs ═══
def fig5_top_configs(df):
    pass_df=df[df["PASS"]].copy()
    pass_df["combined"]=-pass_df["delta_rank_strong"]/100+pass_df["delta_roc"]*100
    top=pass_df.nlargest(18,"combined")
    fig,ax=plt.subplots(figsize=(8.5,6))
    y=range(len(top)); colors=[EXP_COLORS.get(e,"#888") for e in top["experiment"]]
    ax.barh(y,top["combined"],color=colors,alpha=0.85,height=0.6)
    for i,(_,r) in enumerate(top.iterrows()):
        label=f'{r["experiment"]} {r["config_name"]}'
        ax.text(-0.3,i,label,ha="right",va="center",fontsize=6,family="monospace")
        info=f'ROC={r["R1_ROC"]:.3f}  DROC={r["delta_roc"]:+.3f}  DRank={r["delta_rank_strong"]:+.0f}'
        if r["num_rounds"]>=3: info+="  multi-round"
        if r["experiment"]=="E32": info+=f'  [{r["select_strategy"]}|{r["train_strategy"]}]'
        ax.text(r["combined"]+0.05,i,info,ha="left",va="center",fontsize=5,color="#555")
    ax.set_yticks([]); ax.set_xlabel("Combined Score (-DRank/100 + DROCx100)")
    ax.axvline(x=0,color="#767676",lw=0.5,linestyle="--")
    ax.legend(handles=[mpatches.Patch(facecolor=c,alpha=0.85,label=e) for e,c in EXP_COLORS.items()],
              frameon=False,fontsize=6,ncol=5,loc="lower right")
    ax.set_title("Top 18 PASS Configs by Combined Score",fontsize=9); style_ax(ax)
    fig.tight_layout(); save_pub(fig,"fig5_top_configs")

# ═══ FIGURE 6: Heatmap ═══
def fig6_heatmap(df):
    df_s=df.sort_values(["experiment","delta_rank_strong"]).copy()
    metrics=["R0_ROC","R1_ROC","R0_PRAUC","R1_PRAUC","R0_Combined","R1_Combined",
             "delta_roc","delta_prauc","R0_rank_strong","R_final_rank_strong",
             "delta_rank_strong","delta_rank_all13"]
    labels=["R0 ROC","R1 ROC","R0 PR-AUC","R1 PR-AUC","R0 Comb","R1 Comb",
            "Delta ROC","Delta PR-AUC","R0 Rank","Final Rank",
            "Delta Rank-Str","Delta Rank-All13"]
    data=df_s[metrics].copy(); data_norm=data.copy()
    for col in metrics:
        m,s=data[col].mean(),data[col].std()
        data_norm[col]=(data[col]-m)/s if s>0 else 0
    n=len(df_s)
    fig,ax=plt.subplots(figsize=(9.5,max(8,n*0.22)))
    cmap=sns.diverging_palette(240,10,as_cmap=True)
    im=ax.imshow(data_norm.values,aspect="auto",cmap=cmap,vmin=-2.5,vmax=2.5)
    ax.set_xticks(range(len(metrics))); ax.set_xticklabels(labels,rotation=45,ha="right",fontsize=6.5)
    ax.set_yticks(range(n))
    ylabels=[]
    for _,r in df_s.iterrows():
        nm=r["config_name"]
        if len(nm)>24: nm=nm[:22]+".."
        ylabels.append(f'{r["experiment"]} {nm}')
    ax.set_yticklabels(ylabels,fontsize=5)
    for i,(_,r) in enumerate(df_s.iterrows()):
        c=PASS_COLORS["PASS"] if r["PASS"] else PASS_COLORS["FAIL"]
        extra=f" [{r['select_strategy'][:4]}]" if r["experiment"]=="E32" else ""
        ax.annotate(("v" if r["PASS"] else "x")+extra,(len(metrics)+0.2,i),
                    fontsize=6.5,color=c,ha="left",va="center",weight="bold")
    cbar=fig.colorbar(im,ax=ax,shrink=0.5,aspect=30,pad=0.02)
    cbar.set_label("Z-score",fontsize=7); cbar.ax.tick_params(labelsize=6)
    ax.set_title(f"E24-E32 Full Heatmap ({n} configs)",fontsize=8.5,pad=8)
    fig.tight_layout(pad=1.2); save_pub(fig,"fig6_heatmap")

# ═══ FIGURE 7 (NEW): PR-AUC Comparison ═══
def fig7_prauc_comparison(df):
    fig,axes=plt.subplots(1,2,figsize=(9,4.2)); ax,ax2=axes
    add_label(ax,"a")
    for exp in sorted(df["experiment"].unique()):
        sub=df[df["experiment"]==exp]; p=sub["PASS"]
        ax.scatter(sub.loc[~p,"delta_roc"],sub.loc[~p,"delta_prauc"],
                   c=EXP_COLORS[exp],marker="o",s=30,alpha=0.35,edgecolors="none")
        ax.scatter(sub.loc[p,"delta_roc"],sub.loc[p,"delta_prauc"],
                   c=EXP_COLORS[exp],marker="o",s=55,alpha=0.9,
                   edgecolors="white",linewidths=0.5,label=exp,zorder=5)
    ax.axhline(y=0,color="#767676",linestyle="--",lw=0.8,alpha=0.5)
    ax.axvline(x=-0.03,color="#E53935",linestyle=":",lw=0.8,alpha=0.5)
    ax.axvline(x=0,color="#767676",linestyle="--",lw=0.5,alpha=0.5)
    ax.fill_between([-0.3,0.3],0,0.08,alpha=0.05,color="#2E9E44")
    best_prauc=df.nlargest(5,"delta_prauc")
    for _,r in best_prauc.iterrows():
        ax.annotate(f'{r["experiment"]} {r["config_name"]}',
                    (r["delta_roc"],r["delta_prauc"]),
                    xytext=(r["delta_roc"]+0.01,r["delta_prauc"]+0.005),
                    fontsize=5,alpha=0.85,
                    arrowprops=dict(arrowstyle="->",color="#555",lw=0.3,connectionstyle="arc3,rad=0.1"))
    ax.set_xlabel("Delta ROC"); ax.set_ylabel("Delta PR-AUC")
    ax.legend(frameon=False,fontsize=5.5,ncol=3,markerscale=0.7,loc="upper left")
    ax.annotate("PR-AUC threshold: pDC50 >= 6.5\nE32 pool ~10K; E24-E31 pool ~48K",
                xy=(0.98,0.02),xycoords="axes fraction",
                fontsize=5.5,color="#767676",ha="right",va="bottom",
                bbox=dict(boxstyle="round,pad=0.3",facecolor="white",alpha=0.7,edgecolor="#ccc",lw=0.3))
    style_ax(ax)

    add_label(ax2,"b")
    for exp in sorted(df["experiment"].unique()):
        sub=df[df["experiment"]==exp]
        ax2.scatter(sub["R0_PRAUC"],sub["R1_PRAUC"],
                    c=EXP_COLORS[exp],s=35,alpha=0.7,edgecolors="white",lw=0.3,label=exp)
    lim_min=min(df["R0_PRAUC"].min(),df["R1_PRAUC"].min())-0.02
    lim_max=max(df["R0_PRAUC"].max(),df["R1_PRAUC"].max())+0.02
    ax2.plot([lim_min,lim_max],[lim_min,lim_max],color="#767676",linestyle="--",lw=0.6,alpha=0.5)
    ax2.fill_between([lim_min,lim_max],[lim_min,lim_max],lim_max,alpha=0.05,color="#2E9E44")
    ax2.text(0.88,0.96,"PR-AUC uparrow\n(improved)",transform=ax2.transAxes,fontsize=6,color="#2E9E44",fontstyle="italic",ha="center")
    ax2.set_xlabel("R0 PR-AUC (before)"); ax2.set_ylabel("R1 PR-AUC (after)")
    ax2.set_xlim(lim_min,lim_max); ax2.set_ylim(lim_min,lim_max)
    ax2.legend(frameon=False,fontsize=5.5,ncol=3,markerscale=0.7,loc="lower right")
    ax2.set_title("PR-AUC: Before vs After Finetuning",fontsize=8,color="#555")
    style_ax(ax2)
    fig.tight_layout(); save_pub(fig,"fig7_prauc_comparison")

# ═══ FIGURE 8 (NEW): Combined Score Leaderboard ═══
def fig8_combined_leaderboard(df):
    df_sorted=df.sort_values("R1_Combined",ascending=True).copy(); n=len(df_sorted)
    fig,ax=plt.subplots(figsize=(8,max(10,n*0.25)))
    y=range(n); colors=[EXP_COLORS.get(e,"#888") for e in df_sorted["experiment"]]
    ax.barh(y,df_sorted["R1_Combined"],color=colors,alpha=0.85,height=0.7,edgecolor="white",lw=0.3)
    for i,(_,r) in enumerate(df_sorted.iterrows()):
        if r["PASS"]: ax.barh(i,r["R1_Combined"],color=colors[i],alpha=1.0,height=0.7,edgecolor="white",lw=0.3)
        label=f'{r["experiment"]} {r["config_name"]}'
        if r["experiment"]=="E32": label+=f' [{r["select_strategy"]}|{r["train_strategy"]}]'
        ax.text(0.4,i,label,ha="right",va="center",fontsize=5.5,family="monospace",
                color="#333" if r["PASS"] else "#aaa")
        ax.text(r["R1_Combined"]+0.005,i,f'{r["R1_Combined"]:.3f}',ha="left",va="center",fontsize=5,
                color="#333" if r["PASS"] else "#aaa")
        if r["PASS"]: ax.annotate(" v",(r["R1_Combined"]+0.04,i),fontsize=7,color="#2E9E44",ha="left",va="center",weight="bold")
    ax.set_yticks([]); ax.set_xlabel("R1 Combined Score"); ax.set_xlim(0,1.05)
    ax.axvline(x=0.5,color="#767676",lw=0.5,linestyle="--",alpha=0.3); ax.axvline(x=0.8,color="#2E9E44",linestyle="--",lw=0.6,alpha=0.5)
    ax.legend(handles=[mpatches.Patch(facecolor=c,alpha=0.85,label=e) for e,c in EXP_COLORS.items()],
              frameon=False,fontsize=6,ncol=5,loc="lower right")
    ax.set_title(f"R1 Combined Score Leaderboard -- All {n} Configs (v = PASS)",fontsize=9); style_ax(ax)
    fig.tight_layout(); save_pub(fig,"fig8_combined_leaderboard")

# ═══ Main ═══
if __name__=="__main__":
    print("="*60); print("E24-E32 Figure Generator (CSV-driven)"); print("="*60)
    print("\n[1/2] Loading compiled_data.csv..."); df=load_dataframe()
    print("\n[2/2] Generating 8 figures...")
    fig1_leaderboard(df); print("  done fig1_leaderboard")
    fig2_method_families(df); print("  done fig2_method_families_rank")
    fig3_method_families_roc(df); print("  done fig3_method_families_roc")
    fig4_grpo(df); print("  done fig4_grpo_comparison")
    fig5_top_configs(df); print("  done fig5_top_configs")
    fig6_heatmap(df); print("  done fig6_heatmap")
    fig7_prauc_comparison(df); print("  done fig7_prauc_comparison (NEW)")
    fig8_combined_leaderboard(df); print("  done fig8_combined_leaderboard (NEW)")
    report={
        "total":len(df),"passed":int(df["PASS"].sum()),"pass_rate":f"{df['PASS'].mean()*100:.0f}%",
        "best_roc":float(df["R1_ROC"].max()),"best_roc_config":str(df.loc[df["R1_ROC"].idxmax(),"config_name"]),
        "best_prauc":float(df["R1_PRAUC"].max()),"best_prauc_config":str(df.loc[df["R1_PRAUC"].idxmax(),"config_name"]),
        "best_combined":float(df["R1_Combined"].max()),"best_combined_config":str(df.loc[df["R1_Combined"].idxmax(),"config_name"]),
        "best_rank":float(df["delta_rank_strong"].min()),"best_rank_config":str(df.loc[df["delta_rank_strong"].idxmin(),"config_name"]),
        "by_experiment":{exp:{"total":int(len(g)),"passed":int(g["PASS"].sum()),"best_roc":float(g["R1_ROC"].max()),"best_combined":float(g["R1_Combined"].max())} for exp,g in df.groupby("experiment")},
    }
    with open(OUTDIR/"summary_e32.json","w") as f: json.dump(report,f,indent=2,ensure_ascii=False)
    print(f"\n{'='*60}")
    print(f"Done! {len(df)} configs across 9 experiments")
    print(f"  PASS: {report['pass_rate']} ({report['passed']}/{report['total']})")
    print(f"  Best ROC:        {report['best_roc_config']} ({report['best_roc']:.3f})")
    print(f"  Best PR-AUC:     {report['best_prauc_config']} ({report['best_prauc']:.3f})")
    print(f"  Best Combined:   {report['best_combined_config']} ({report['best_combined']:.3f})")
    print(f"  Best Rank-Strong:{report['best_rank_config']} ({report['best_rank']:.0f})")
    print(f"  Output: {OUTDIR}/")
    print(f"{'='*60}")
