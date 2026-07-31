"""VAV1 RL Pipeline 可视化：step3/4/5/7/8/9 独立单图 + step9 top20 分子对照网格。

生成 PNG+SVG 到 project_root/reports/figures/step{N}/。
step3-8 用 matplotlib 数据分析风格，step9 分子平面图用 RDKit 绘制。
GLARE 和亲和度使用原始数据（非混合权重）。
"""
import sys
sys.path.insert(0, '/data/ye/e-drug-lab/backend')

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import pandas as pd
import numpy as np
from pathlib import Path
import json
import ast

# Nature 风格
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "figure.dpi": 200, "savefig.dpi": 200, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
})

ROOT = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project")
FIGS = ROOT / "reports/figures"
PRJ = ROOT

def save(fig, step, name):
    for ext in ("png", "svg"):
        p = FIGS / f"step{step}" / f"{name}.{ext}"
        fig.savefig(p, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved step{step}/{name}")

# ================================================================
# STEP 3 — Validity + ADMET
# ================================================================
def step3_plots():
    print("STEP 3: ADMET")
    df = pd.read_csv(PRJ / "screening/step3_validity_admet_all.csv")

    # 3a — validity pass/fail pie
    fig, ax = plt.subplots(figsize=(3, 3))
    vc = df["validity_pass"].value_counts()
    colors = ["#2ecc71" if k else "#e74c3c" for k in vc.index]
    ax.pie(vc.values, labels=["Pass" if k else "Fail" for k in vc.index],
           autopct="%1.1f%%", colors=colors, startangle=90, explode=(0.02, 0.1))
    ax.set_title("Chemical Validity (11 checks)")
    save(fig, 3, "3a_validity_pie")

    # 3b — ADMET endpoint pass/warning/fail stacked bar (top 20 endpoints)
    endpoint_counts = {"pass": 0, "warning": 0, "fail": 0}
    ep_names = []
    ep_pass, ep_warn, ep_fail = [], [], []
    # parse endpoint_labels
    all_labels = []
    for _, r in df.iterrows():
        try:
            d = ast.literal_eval(str(r["endpoint_labels"]))
            if isinstance(d, dict):
                all_labels.append(d)
        except Exception:
            pass
    if all_labels:
        all_eps = sorted(set().union(*[d.keys() for d in all_labels]))
        for ep in all_eps[:24]:
            ep_names.append(ep)
            p = sum(d.get(ep) == "pass" for d in all_labels)
            w = sum(d.get(ep) == "warning" for d in all_labels)
            f = sum(d.get(ep) == "fail" for d in all_labels)
            ep_pass.append(p); ep_warn.append(w); ep_fail.append(f)

    if ep_names:
        fig, ax = plt.subplots(figsize=(8, 5))
        x = np.arange(len(ep_names))
        ax.barh(x, ep_pass, color="#2ecc71", label="Pass")
        ax.barh(x, ep_warn, left=ep_pass, color="#f39c12", label="Warning")
        ax.barh(x, ep_fail, left=[p+w for p,w in zip(ep_pass, ep_warn)], color="#e74c3c", label="Fail")
        ax.set_yticks(x)
        ax.set_yticklabels(ep_names, fontsize=6)
        ax.set_xlabel("Molecule count")
        ax.set_title("ADMET Endpoint Classification (922 candidates)")
        ax.legend(fontsize=7, loc="lower right")
        save(fig, 3, "3b_admet_endpoints")

    # 3c — rejection reason breakdown
    reasons = df["reject_reason"].dropna().str.extract(r"(^[^:;]+)")[0].value_counts().head(8)
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.barh(range(len(reasons)), reasons.values, color="#e74c3c", alpha=0.8)
    ax.set_yticks(range(len(reasons)))
    ax.set_yticklabels(reasons.index, fontsize=6)
    ax.set_xlabel("Molecules rejected")
    ax.set_title("Top Rejection Reasons (Step 3)")
    save(fig, 3, "3c_reject_reasons")


# ================================================================
# STEP 4 — Druglikeness
# ================================================================
def step4_plots():
    print("STEP 4: Druglikeness")
    df = pd.read_csv(PRJ / "screening/step4_druglikeness_round1_all.csv")

    # 4a — QED distribution
    fig, ax = plt.subplots(figsize=(4, 3))
    qed = pd.to_numeric(df["qed"], errors="coerce").dropna()
    ax.hist(qed, bins=40, color="#3498db", edgecolor="white", linewidth=0.5)
    ax.axvline(0.3, color="#e74c3c", linestyle="--", linewidth=1.2, label="QED≥0.3 cutoff")
    ax.set_xlabel("QED")
    ax.set_ylabel("Count")
    ax.set_title(f"QED Distribution (n={len(qed)})")
    ax.legend(fontsize=7)
    save(fig, 4, "4a_qed_hist")

    # 4b — SA distribution
    sa = pd.to_numeric(df["sa"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(sa, bins=40, color="#2ecc71", edgecolor="white", linewidth=0.5)
    ax.axvline(5, color="#e74c3c", linestyle="--", linewidth=1.2, label="SA<5 cutoff")
    ax.set_xlabel("SA Score")
    ax.set_ylabel("Count")
    ax.set_title(f"SA Distribution (n={len(sa)})")
    ax.legend(fontsize=7)
    save(fig, 4, "4b_sa_hist")

    # 4c — LogP histogram
    logp = pd.to_numeric(df["logp"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(logp, bins=50, color="#9b59b6", edgecolor="white", linewidth=0.5)
    ax.axvline(1.0, color="gray", linestyle="--", linewidth=0.8)
    ax.axvline(3.5, color="gray", linestyle="--", linewidth=0.8, label="LogP 1–3.5")
    ax.axvspan(1, 3.5, alpha=0.1, color="#9b59b6")
    ax.set_xlabel("LogP")
    ax.set_ylabel("Count")
    ax.set_title(f"LogP Distribution (n={len(logp)})")
    ax.legend(fontsize=7)
    save(fig, 4, "4c_logp_hist")

    # 4d — TPSA histogram
    tpsa = pd.to_numeric(df["tpsa"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(tpsa, bins=50, color="#e67e22", edgecolor="white", linewidth=0.5)
    ax.axvline(40, color="gray", linestyle="--", linewidth=0.8)
    ax.axvline(90, color="gray", linestyle="--", linewidth=0.8, label="TPSA 40–90")
    ax.axvspan(40, 90, alpha=0.1, color="#e67e22")
    ax.set_xlabel("TPSA (Å²)")
    ax.set_ylabel("Count")
    ax.set_title(f"TPSA Distribution (n={len(tpsa)})")
    ax.legend(fontsize=7)
    save(fig, 4, "4d_tpsa_hist")

    # 4e — Lipinski pass count
    lpc = df["lipinski_pass_count"].dropna().astype(int)
    fig, ax = plt.subplots(figsize=(3, 3))
    counts = lpc.value_counts().sort_index()
    colors = ["#e74c3c" if i < 4 else "#2ecc71" for i in counts.index]
    ax.bar(counts.index, counts.values, color=colors, alpha=0.8)
    ax.set_xlabel("Lipinski Pass Count")
    ax.set_ylabel("Molecules")
    ax.set_title("Lipinski RO5 Compliance")
    ax.axvline(3.5, color="gray", linestyle="--", linewidth=0.8)
    save(fig, 4, "4e_lipinski")

    # 4f — rejection reason breakdown
    reasons = df["reject_reason"].dropna()
    if len(reasons) > 0:
        rc = reasons.value_counts().head(6)
        fig, ax = plt.subplots(figsize=(5, 2.5))
        ax.barh(range(len(rc)), rc.values, color="#e74c3c", alpha=0.8)
        ax.set_yticks(range(len(rc)))
        ax.set_yticklabels(rc.index, fontsize=6)
        ax.set_xlabel("Rejected")
        ax.set_title("Step 4 Rejection Reasons")
        save(fig, 4, "4f_reject_reasons")


# ================================================================
# STEP 5 — Affinity（使用原始 Vina 分数，不用混合权重）
# ================================================================
def step5_plots():
    print("STEP 5: Affinity (raw Vina scores from round_200)")
    # 从 round_200 原始评估表取真实 Vina 分数（step5 是占位，vina_score 全 NaN）
    r200 = pd.read_excel("/data/ye/e-drug-lab/backend/outputs/rl_rounds/round_200/merged/round_200_merged_eval.xlsx")
    vina_col = "Vina_Dock_亲和力"
    if vina_col not in r200.columns:
        for c in r200.columns:
            if "vina" in c.lower() or "亲和力" in c:
                vina_col = c
                break
    vina = pd.to_numeric(r200[vina_col], errors="coerce").dropna()
    print(f"  Vina col='{vina_col}', n={len(vina)}, mean={vina.mean():.1f}")

    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(vina, bins=50, color="#1abc9c", edgecolor="white", linewidth=0.5)
    ax.axvline(-6, color="#e74c3c", linestyle="--", linewidth=1.2, label="<= -6 kcal/mol target")
    ax.set_xlabel("Vina Dock Score (kcal/mol, lower = better)")
    ax.set_ylabel("Count")
    ax.set_title(f"Raw Vina Docking Affinity (round_200, n={len(vina)})")
    ax.legend(fontsize=7)
    save(fig, 5, "5a_vina_hist")


# ================================================================
# STEP 7 — GLARE（使用原始 select_prob，不用混合权重）
# ================================================================
def step7_plots():
    print("STEP 7: GLARE ranking (raw data)")
    df = pd.read_csv(PRJ / "glare/step7_glare_ranked_all.csv")

    # 7a — glare_select_prob histogram
    prob = pd.to_numeric(df["glare_select_prob"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(prob, bins=30, color="#8e44ad", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("GLARE Select Probability")
    ax.set_ylabel("Count")
    ax.set_title(f"GLARE Select Prob Distribution (n={len(prob)}), encoder=ginl")
    save(fig, 7, "7a_select_prob_hist")

    # 7b — uncertainty vs select_prob scatter
    unc = pd.to_numeric(df["glare_uncertainty"], errors="coerce").dropna()
    if len(prob) == len(unc):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.scatter(prob, unc, s=3, alpha=0.6, c="#8e44ad", edgecolors="none")
        ax.set_xlabel("Select Probability")
        ax.set_ylabel("Uncertainty (Ensemble std)")
        ax.set_title(f"GLARE Uncertainty vs Select Prob (n={len(prob)})")
        save(fig, 7, "7b_uncertainty_scatter")

    # 7c — rank vs select_prob
    rank = pd.to_numeric(df["glare_rank"], errors="coerce").dropna()
    if len(prob) == len(rank):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.plot(rank, prob.sort_values(ascending=False).values, linewidth=0.8, color="#8e44ad")
        ax.set_xlabel("GLARE Rank")
        ax.set_ylabel("Select Probability")
        ax.set_title("GLARE Rank vs Select Probability")
        save(fig, 7, "7c_rank_vs_prob")


# ================================================================
# STEP 8 — Final Ranking
# ================================================================
def step8_plots():
    print("STEP 8: Final Ranking")
    df = pd.read_csv(PRJ / "screening/step8_final_ranked_all.csv")

    # 8a — final_score histogram
    fs = pd.to_numeric(df["final_score"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(fs, bins=30, color="#c0392b", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Final Score")
    ax.set_ylabel("Count")
    ax.set_title(f"Final Score Distribution (weights: 0.05/0.15/0.80)", fontsize=8)
    save(fig, 8, "8a_final_score_hist")

    # 8b — Top 20 bar chart
    top20 = df.head(20).copy()
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.barh(range(20), top20["final_score"].values[::-1], color="#c0392b", alpha=0.8)
    ax.set_yticks(range(20))
    ax.set_yticklabels([f"Rank {i+1}" for i in range(20)[::-1]], fontsize=6)
    ax.set_xlabel("Final Score")
    ax.set_title("Top 20 — Final Ranking (0.05×model + 0.15×affinity + 0.80×glare)")
    save(fig, 8, "8b_top20_bars")


# ================================================================
# STEP 9 — Similarity: top20 分子平面图 + 最近邻参考分子对照网格
# ================================================================
def step9_plots():
    print("STEP 9: Similarity — top20 molecule grid")
    from rdkit import Chem
    from rdkit.Chem import Draw, AllChem
    from io import BytesIO

    df = pd.read_csv(PRJ / "similarity/step9_top20_by_similarity.csv")
    ref = pd.read_excel("/data/ye/e-drug-lab/glaretrain/DataSet-GNN-SMILES-pDC50.xlsx")
    ref.columns = [c.strip() for c in ref.columns]
    ref_map = {}
    for _, r in ref.iterrows():
        ref_map[str(r.iloc[0])] = str(r.iloc[1])

    # 9a — Morgan similarity distribution histogram
    morgan = pd.to_numeric(df["max_morgan_tanimoto_all"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(morgan, bins=30, color="#2980b9", edgecolor="white", linewidth=0.5)
    ax.axvline(0.70, color="#e74c3c", linestyle="--", linewidth=1.2, label="Tanimoto≥0.70")
    ax.set_xlabel("Max Morgan Tanimoto (vs 439 known)")
    ax.set_ylabel("Count")
    ax.set_title(f"Similarity to 439 Known Molecules (0 molecules ≥0.70)")
    ax.legend(fontsize=7)
    save(fig, 9, "9a_morgan_tanimoto_hist")

    # 9b — SMILES similarity distribution
    smi_sim = pd.to_numeric(df["smiles_string_similarity"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.hist(smi_sim, bins=30, color="#27ae60", edgecolor="white", linewidth=0.5)
    ax.set_xlabel("SMILES String Similarity (Levenshtein)")
    ax.set_ylabel("Count")
    ax.set_title(f"SMILES String Similarity Distribution")
    save(fig, 9, "9b_smiles_sim_hist")

    # 9c — Top20 分子双列对照网格（candidate | reference）
    top20 = df.head(20)
    mols_cand = []
    mols_ref = []
    labels = []
    for i, (_, r) in enumerate(top20.iterrows()):
        cand_smi = str(r["candidate_smiles"])
        ref_smi = ref_map.get(str(r["nearest_ref_id"]), "")
        m_c = Chem.MolFromSmiles(cand_smi)
        m_r = Chem.MolFromSmiles(ref_smi) if ref_smi else None
        if m_c is None:
            continue
        mols_cand.append(m_c)
        mols_ref.append(m_r)
        tan = r["max_morgan_tanimoto_all"]
        rid = str(r["nearest_ref_id"])[:10]
        labels.append(f"C{i+1} | Tan={tan:.3f}\nR: {rid}")

    # 分两批画（每批 10 对 = 20 个分子图，否则图太大）
    for batch_start in range(0, len(mols_cand), 10):
        b_end = min(batch_start + 10, len(mols_cand))
        bmols = []
        bleg  = []
        for j in range(batch_start, b_end):
            bmols.append(mols_cand[j])
            bleg.append(f"C{j+1} | T={top20.iloc[j]['max_morgan_tanimoto_all']:.3f}")
            if mols_ref[j] is not None:
                bmols.append(mols_ref[j])
                bleg.append(f"{str(top20.iloc[j]['nearest_ref_id'])[:10]}")
            else:
                bmols.append(Chem.MolFromSmiles("C"))
                bleg.append("N/A")
        n = len(bmols)
        rows = (n + 3) // 4
        # 使用 GridImage
        fig = None
        try:
            img = Draw.MolsToGridImage(
                bmols, molsPerRow=4, subImgSize=(350, 300),
                legends=bleg, returnPNG=False
            )
            img.save(str(FIGS / "step9" / f"9c_top20_pairs_batch{batch_start//10}.png"))
            print(f"  saved step9/9c_top20_pairs_batch{batch_start//10}.png")
        except Exception as e:
            print(f"  mol grid error: {e}")


# ================================================================
# RUN
# ================================================================
if __name__ == "__main__":
    step3_plots()
    step4_plots()
    step5_plots()
    step7_plots()
    step8_plots()
    step9_plots()
    print("\nAll figures generated.")
