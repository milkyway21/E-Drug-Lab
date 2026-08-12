#!/usr/bin/env python3
"""导入 MD 反馈并合并到特征表（骨架；校验 molecule_id / schema / QC 门禁）。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback-json", required=True, help="含 molecule_id, md_vec, md_mask, reward_total, qc_pass")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    rows = json.loads(Path(args.feedback_json).read_text())
    if isinstance(rows, dict):
        rows = rows.get("molecules") or rows.get("rows") or []
    accepted, rejected = [], []
    for r in rows:
        if not r.get("qc_pass", True):
            rejected.append({**r, "reject_reason": "qc_fail"})
            continue
        if int(r.get("md_mask", 0)) != 1:
            rejected.append({**r, "reject_reason": "md_mask!=1"})
            continue
        if not r.get("molecule_id"):
            rejected.append({**r, "reject_reason": "missing_id"})
            continue
        accepted.append(r)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "accepted.json").write_text(json.dumps(accepted, indent=2), encoding="utf-8")
    (out / "rejected.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "n_accepted": len(accepted), "n_rejected": len(rejected)}))


if __name__ == "__main__":
    main()
