#!/usr/bin/env python3
"""E47–E53 分阶段消融：strip → PC → Glide R0 → Expand → MD。

E47: 数据门禁（strip / physchem / MD QC）— 不训练
E48: ginl + strip
E49: ginl_pc
E50: ginl_pc_gl（R0 专利 Glide）
E51: R1 Expand（wetlab），无 MD（从 E50 ckpt --prev）
E52: R1 Expand + MD（需 E47 MD gate；md_adv + 可选残差）
E53: 对照旧基线写 summary

默认：ensemble=3, epochs=50, GRPO；评估 patent_test ROC + wetlab13 排序。
用法:
  cd backend && CUDA_VISIBLE_DEVICES=0 \\
    /home/user/anaconda3/envs/diffgui_new/bin/python scripts/run_e47_e53_ablation.py
  # 或通过 adapter（较慢）:
  .venv/bin/python scripts/run_e47_e53_ablation.py --via-adapter
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem
from sklearn.metrics import roc_auc_score

ROOT = Path("/data/ye/e-drug-lab/backend")
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs/vav1_rl_project/validation/glare_e47_e53_ablation"
BINDING = ROOT / "outputs/vav1_rl_project/binding_RL"
PATENT = ROOT / "outputs/vav1_rl_project/data/processed/patent_403_cleaned.csv"
TRAIN_CSV = ROOT / "outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709/data/patent_train_303.csv"
TEST_CSV = ROOT / "outputs/vav1_rl_project/validation/glare_e33_full_patent_20260709/data/patent_test_100.csv"
WETLAB = BINDING / "wetlab_docking" / "wetlab_13_labels.csv"
LOG = ROOT / "outputs/vav1_rl_project/reports/experiment_log.md"
STRIP_QC = BINDING / "features_v1/strip_qc/strip_qc_summary.json"
PC_QC = BINDING / "features_v1/physchem/physchem_qc_report.json"
MD_QC = BINDING / "features_v1/md/md_qc_report.json"


def norm(smi: str) -> str | None:
    m = Chem.MolFromSmiles(smi)
    return Chem.MolToSmiles(m) if m else None


def load_patent_split():
    full = pd.read_csv(PATENT)
    train_ids = set(pd.read_csv(TRAIN_CSV)["molecule_id"].astype(str))
    test_ids = set(pd.read_csv(TEST_CSV)["molecule_id"].astype(str))
    id_col = "molecule_id"
    smi_col = "canonical_smiles" if "canonical_smiles" in full.columns else "smiles"

    def pack(ids):
        smiles, labels, weights, mids = [], [], [], []
        for _, r in full.iterrows():
            mid = str(r[id_col])
            if mid not in ids:
                continue
            s = norm(str(r[smi_col]))
            if not s:
                continue
            la = int(r["label_active"])
            if la not in (0, 1):
                continue
            smiles.append(s)
            labels.append(1 if la == 1 else 0)
            weights.append(float(r.get("sample_weight", 1.0)))
            mids.append(mid)
        return smiles, labels, weights, mids

    return pack(train_ids), pack(test_ids)


def load_wetlab():
    df = pd.read_csv(WETLAB)
    id_col = "SDF_ID" if "SDF_ID" in df.columns else "molecule_id"
    smi_col = "SMILES" if "SMILES" in df.columns else "smiles"
    lab_col = "label" if "label" in df.columns else "label_active"
    smiles, labels, weights, mids = [], [], [], []
    for _, r in df.iterrows():
        s = norm(str(r[smi_col]))
        if not s:
            continue
        mid = str(r[id_col])
        la = int(r[lab_col])
        w = float(r.get("weight", 5.0 if la == 1 else 1.0))
        # R1 小样本：阳性放大
        if la == 1:
            w = max(w, 5.0)
        smiles.append(s)
        labels.append(la)
        weights.append(w)
        mids.append(mid)
    return smiles, labels, weights, mids


def e47_gates() -> dict:
    out = {"strip": None, "physchem": None, "md": None, "gate_pass": False}
    for name, path in [("strip", STRIP_QC), ("physchem", PC_QC), ("md", MD_QC)]:
        if not path.is_file():
            out[name] = {"exists": False, "gate_pass": False}
            continue
        d = json.loads(path.read_text())
        if name == "strip":
            gp = bool(d.get("all_pass"))
        else:
            gp = bool(d.get("gate_pass"))
        out[name] = {"exists": True, "gate_pass": gp, "summary": {k: d.get(k) for k in list(d)[:12]}}
    out["gate_pass"] = all(out[k].get("gate_pass") for k in ("strip", "physchem", "md"))
    return out


def train_via_cli(ckpt, data_json, architecture, epochs, ensemble, prev=None, md_adv_eta=0.0, extra=None):
    """直接在 diffgui_new 调 CLI（避免再套 conda）。"""
    import subprocess
    cmd = [
        "/home/user/anaconda3/envs/diffgui_new/bin/python", "-m",
        "app.pipelines.vav1_rl.glare_gnn_cli", "train",
        "--ckpt", str(ckpt), "--data", str(data_json),
        "--epochs", str(epochs), "--ensemble", str(ensemble),
        "--architecture", architecture,
        "--md_adv_eta", str(md_adv_eta),
        "--disable-ig",
    ]
    if prev:
        cmd += ["--prev", str(prev)]
    if extra:
        cmd += extra
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=7200)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip().startswith("{")]
    if p.returncode != 0 and not lines:
        return {"ok": False, "error": (p.stderr or p.stdout)[-2000:], "code": p.returncode}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": (p.stderr or p.stdout)[-2000:]}


def query_via_cli(ckpt, smiles_json, ensemble):
    import subprocess
    cmd = [
        "/home/user/anaconda3/envs/diffgui_new/bin/python", "-m",
        "app.pipelines.vav1_rl.glare_gnn_cli", "query",
        "--ckpt", str(ckpt), "--smiles", str(smiles_json),
        "--ensemble", str(ensemble),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")
    p = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=3600)
    lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip().startswith("{")]
    if not lines:
        return {"ok": False, "error": (p.stderr or p.stdout)[-2000:]}
    return json.loads(lines[-1])


def eval_roc(ckpt, test_pack, ensemble):
    smiles, labels, _, mids = test_pack
    smi_path = OUT / "_tmp_test_smiles.json"
    payload = [{"smiles": s, "molecule_id": m} for s, m in zip(smiles, mids)]
    smi_path.write_text(json.dumps(payload))
    qr = query_via_cli(ckpt, smi_path, ensemble)
    if not qr.get("ok"):
        return {"ok": False, "error": qr.get("error")}
    # 优先 molecule_id，其次 smiles_raw / smiles
    score_by_id = {}
    score_by_smi = {}
    for r in qr["ranked"]:
        if r.get("molecule_id") is not None:
            score_by_id[str(r["molecule_id"])] = r["glare_select_prob"]
        for key in (r.get("smiles_raw"), r.get("smiles")):
            if key:
                score_by_smi[key] = r["glare_select_prob"]
    y, s = [], []
    for smi, lab, mid in zip(smiles, labels, mids):
        sc = score_by_id.get(str(mid))
        if sc is None:
            sc = score_by_smi.get(smi)
        if sc is None:
            continue
        y.append(lab)
        s.append(sc)
    if len(set(y)) < 2:
        return {"ok": False, "error": "single_class", "n_matched": len(y), "n_pos": int(sum(y)), "n_neg": int(len(y) - sum(y))}
    auc = float(roc_auc_score(y, s))
    return {"ok": True, "roc_auc": auc, "n": len(y)}


def eval_wetlab_rank(ckpt, ensemble):
    smiles, labels, _, mids = load_wetlab()
    payload = [{"smiles": s, "molecule_id": m} for s, m in zip(smiles, mids)]
    smi_path = OUT / "_tmp_wl_smiles.json"
    smi_path.write_text(json.dumps(payload))
    qr = query_via_cli(ckpt, smi_path, ensemble)
    if not qr.get("ok"):
        return {"ok": False, "error": qr.get("error")}
    by_id = {str(r.get("molecule_id")): r for r in qr["ranked"] if r.get("molecule_id") is not None}
    by_smi = {}
    for r in qr["ranked"]:
        for key in (r.get("smiles_raw"), r.get("smiles")):
            if key:
                by_smi[key] = r
    rows = []
    for smi, lab, mid in zip(smiles, labels, mids):
        r = by_id.get(str(mid)) or by_smi.get(smi)
        rows.append({"id": mid, "label": lab, "rank": int(r["glare_rank"]) if r else None,
                     "score": float(r["glare_select_prob"]) if r else None})
    rows_sorted = sorted([r for r in rows if r["rank"] is not None], key=lambda x: x["rank"])
    # re-rank among wetlab only if absolute ranks span a larger pool — here pool==wetlab
    pos_ranks = [r["rank"] for r in rows if r["label"] == 1 and r["rank"] is not None]
    return {
        "ok": True,
        "n": len(rows),
        "n_matched": len(rows_sorted),
        "pos_ids": [r["id"] for r in rows if r["label"] == 1],
        "pos_ranks": pos_ranks,
        "mean_pos_rank": float(np.mean(pos_ranks)) if pos_ranks else None,
        "ranking": rows,
    }


def write_train_json(path, smiles, labels, weights, mids):
    data = [
        {"smiles": s, "label": int(lb), "weight": float(w), "molecule_id": mid}
        for s, lb, w, mid in zip(smiles, labels, weights, mids)
    ]
    path.write_text(json.dumps(data))


def append_experiment_log(summary: dict):
    block = [
        "\n\n---\n\n",
        "## E47–E53 GLARE 多模态残差消融（2026-07-24）\n\n",
        "方案：strip + PhysChem 残差 + 专利 Glide 残差（R0）+ MD GRPO shaping（R1+）。\n\n",
        "```json\n",
        json.dumps(summary, indent=2, ensure_ascii=False),
        "\n```\n",
    ]
    with LOG.open("a", encoding="utf-8") as f:
        f.write("".join(block))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--ensemble", type=int, default=3)
    ap.add_argument("--smoke", action="store_true", help="epochs=2 ensemble=1 冒烟")
    ap.add_argument("--skip-train", action="store_true")
    ap.add_argument("--reeval", action="store_true", help="仅对已有 ckpt 重跑评估")
    args = ap.parse_args()
    epochs = 2 if args.smoke else args.epochs
    ensemble = 1 if args.smoke else args.ensemble

    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S"), "epochs": epochs, "ensemble": ensemble, "runs": {}}

    # E47
    print("=== E47 data gates ===", flush=True)
    g47 = e47_gates()
    summary["runs"]["E47"] = g47
    (OUT / "E47_gates.json").write_text(json.dumps(g47, indent=2))
    print("E47 gate_pass:", g47["gate_pass"], flush=True)

    train_pack, test_pack = load_patent_split()
    print(f"train={len(train_pack[0])} test={len(test_pack[0])}", flush=True)

    if args.reeval:
        mapping = [
            ("E48", "E48_ginl.pt", "ginl"),
            ("E49", "E49_ginl_pc.pt", "ginl_pc"),
            ("E50", "E50_ginl_pc_gl.pt", "ginl_pc_gl"),
            ("E51", "E51_ginl_pc_gl_expand.pt", "ginl_pc_gl"),
            ("E52", "E52_ginl_pc_gl_md.pt", "ginl_pc_gl_md"),
        ]
        for name, fname, arch in mapping:
            ckpt = OUT / fname
            if not ckpt.is_file():
                summary["runs"][name] = {"skipped": True, "reason": "no ckpt"}
                continue
            print(f"=== reeval {name} ===", flush=True)
            roc = eval_roc(ckpt, test_pack, ensemble)
            wl = eval_wetlab_rank(ckpt, ensemble)
            summary["runs"][name] = {"architecture": arch, "roc": roc, "wetlab": wl, "checkpoint": str(ckpt)}
            (OUT / f"{name}_result.json").write_text(json.dumps(summary["runs"][name], indent=2, default=str))
        summary["runs"]["E53"] = {
            "baselines": {
                "E37b_GRPO_ens3_r2_rank_note": "#4174 on MolFactory (historical)",
                "protocol_here": "patent_test ROC-AUC (0/1 only) + wetlab13 mean_pos_rank",
            },
            "comparison_table": {
                k: {
                    "roc_auc": summary["runs"].get(k, {}).get("roc", {}).get("roc_auc"),
                    "mean_pos_rank": summary["runs"].get(k, {}).get("wetlab", {}).get("mean_pos_rank"),
                }
                for k in ("E48", "E49", "E50", "E51", "E52")
            },
        }
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        append_experiment_log(summary)
        print(json.dumps(summary["runs"]["E53"], indent=2), flush=True)
        print("DONE →", OUT, flush=True)
        return

    if args.skip_train:
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
        return

    configs = [
        ("E48", "ginl", None, 0.0, False),
        ("E49", "ginl_pc", None, 0.0, False),
        ("E50", "ginl_pc_gl", None, 0.0, False),
    ]
    ckpts = {}
    for name, arch, prev_key, md_eta, expand in configs:
        print(f"=== {name} arch={arch} ===")
        ckpt = OUT / f"{name}_{arch}.pt"
        data_path = OUT / f"{name}_train.json"
        write_train_json(data_path, *train_pack)
        t0 = time.time()
        tr = train_via_cli(ckpt, data_path, arch, epochs, ensemble, md_adv_eta=md_eta)
        elapsed = time.time() - t0
        print(tr)
        roc = eval_roc(ckpt, test_pack, ensemble) if tr.get("ok") else {"ok": False}
        wl = eval_wetlab_rank(ckpt, ensemble) if tr.get("ok") else {"ok": False}
        summary["runs"][name] = {
            "architecture": arch, "train": tr, "roc": roc, "wetlab": wl, "elapsed_s": elapsed,
        }
        if tr.get("ok"):
            ckpts[name] = ckpt
        (OUT / f"{name}_result.json").write_text(json.dumps(summary["runs"][name], indent=2, default=str))

    # E51: Expand wetlab on E50, no MD
    if "E50" in ckpts:
        print("=== E51 Expand no-MD ===")
        wl_s, wl_y, wl_w, wl_id = load_wetlab()
        # patent + wetlab
        ts, ty, tw, tid = train_pack
        data_path = OUT / "E51_train.json"
        write_train_json(
            data_path,
            ts + wl_s, ty + wl_y, tw + wl_w, tid + wl_id,
        )
        ckpt = OUT / "E51_ginl_pc_gl_expand.pt"
        t0 = time.time()
        tr = train_via_cli(
            ckpt, data_path, "ginl_pc_gl", epochs, ensemble,
            prev=str(ckpts["E50"]), md_adv_eta=0.0,
        )
        roc = eval_roc(ckpt, test_pack, ensemble) if tr.get("ok") else {"ok": False}
        wl = eval_wetlab_rank(ckpt, ensemble) if tr.get("ok") else {"ok": False}
        summary["runs"]["E51"] = {
            "architecture": "ginl_pc_gl", "train": tr, "roc": roc, "wetlab": wl,
            "elapsed_s": time.time() - t0, "prev": "E50",
        }
        if tr.get("ok"):
            ckpts["E51"] = ckpt
        (OUT / "E51_result.json").write_text(json.dumps(summary["runs"]["E51"], indent=2, default=str))

    # E52: Expand + MD (blocked if E47 fail)
    if g47["gate_pass"] and "E50" in ckpts:
        print("=== E52 Expand + MD ===")
        wl_s, wl_y, wl_w, wl_id = load_wetlab()
        ts, ty, tw, tid = train_pack
        # MD 分子权重放大
        md_ids = set(json.loads(MD_QC.read_text())["molecule_ids"])
        tw2 = list(tw)
        # wetlab weights already amplified; boost MD-overlapping further
        ww2 = []
        for mid, w, y in zip(wl_id, wl_w, wl_y):
            ww2.append(w * (3.0 if mid in md_ids else 1.0))
        data_path = OUT / "E52_train.json"
        write_train_json(data_path, ts + wl_s, ty + wl_y, tw2 + ww2, tid + wl_id)
        ckpt = OUT / "E52_ginl_pc_gl_md.pt"
        t0 = time.time()
        tr = train_via_cli(
            ckpt, data_path, "ginl_pc_gl_md", epochs, ensemble,
            prev=str(ckpts["E50"]), md_adv_eta=0.5,
        )
        roc = eval_roc(ckpt, test_pack, ensemble) if tr.get("ok") else {"ok": False}
        wl = eval_wetlab_rank(ckpt, ensemble) if tr.get("ok") else {"ok": False}
        summary["runs"]["E52"] = {
            "architecture": "ginl_pc_gl_md", "train": tr, "roc": roc, "wetlab": wl,
            "elapsed_s": time.time() - t0, "prev": "E50", "md_adv_eta": 0.5,
        }
        (OUT / "E52_result.json").write_text(json.dumps(summary["runs"]["E52"], indent=2, default=str))
    else:
        summary["runs"]["E52"] = {"skipped": True, "reason": "E47 gate failed or no E50"}

    # E53 comparison vs known baselines from log
    summary["runs"]["E53"] = {
        "baselines": {
            "E37b_GRPO_ens3_r2_rank_note": "#4174 on MolFactory (historical)",
            "E38_official_ens10": "see experiment_log",
            "protocol_here": "patent_test_100 ROC-AUC + wetlab13 mean_pos_rank",
        },
        "comparison_table": {
            k: {
                "roc_auc": summary["runs"].get(k, {}).get("roc", {}).get("roc_auc"),
                "mean_pos_rank": summary["runs"].get(k, {}).get("wetlab", {}).get("mean_pos_rank"),
            }
            for k in ("E48", "E49", "E50", "E51", "E52")
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    append_experiment_log(summary)
    print(json.dumps(summary["runs"]["E53"], indent=2))
    print("DONE →", OUT)


if __name__ == "__main__":
    main()
