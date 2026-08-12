#!/usr/bin/env python3
"""持续学习遗忘矩阵评估骨架（合成划分可跑；真 SP 齐套后再接生产目录）。

输出 continual_learning_matrix.csv / forgetting_report.json。
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds-dir", required=True, help="含 model_R*.pt 与 dataset_R*.json 的目录")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--dry-run", action="store_true", help="只写空矩阵模板，不推理")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rounds = ["R0", "R1", "R2", "R3"]
    matrix_path = out / "continual_learning_matrix.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "test_set", "roc_auc", "pr_auc", "mcc", "status"])
        for m in rounds:
            for t in rounds:
                if rounds.index(t) > rounds.index(m):
                    continue
                status = "pending_sp_or_ckpt" if args.dry_run else "not_evaluated"
                w.writerow([m, t, "", "", "", status])
    report = {
        "ok": True,
        "note": "骨架已就位；等持续学习 Glide SP 与新 ckpt 后填充数值",
        "forgetting_definition": "F_t,k = metric_{t-1,k} - metric_{t,k}",
        "matrix": str(matrix_path),
    }
    (out / "forgetting_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
