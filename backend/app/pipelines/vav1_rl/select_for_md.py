#!/usr/bin/env python3
"""从候选池选出值得做 MD 的分子（骨架；不自动跑 Desmond）。

选点分数（可配置权重）：
  S = w1*P(active) + w2*U + w3*Diversity + w4*Novelty + w5*MD_missing

用法示例：
  python -m app.pipelines.vav1_rl.select_for_md \\
    --ranked ranks.json --out md_candidates.csv --top-k 20
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Select molecules for MD (skeleton)")
    ap.add_argument("--ranked", required=True, help="query 输出 JSON 或含 score 的列表")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--w-active", type=float, default=0.35)
    ap.add_argument("--w-unc", type=float, default=0.25)
    ap.add_argument("--w-md-missing", type=float, default=0.40)
    ap.add_argument("--already-md", default=None, help="已有 MD 的 molecule_id 列表 JSON")
    args = ap.parse_args()

    raw = json.loads(Path(args.ranked).read_text())
    rows = raw["ranked"] if isinstance(raw, dict) and "ranked" in raw else raw
    done = set()
    if args.already_md and Path(args.already_md).is_file():
        done = set(json.loads(Path(args.already_md).read_text()))

    scored = []
    for r in rows:
        mid = str(r.get("molecule_id") or "")
        if mid in done:
            continue
        p = float(r.get("glare_select_prob") or r.get("score") or 0.0)
        u = float(r.get("glare_uncertainty") or 0.0)
        md_miss = 0.0 if r.get("md_observed") else 1.0
        s = args.w_active * p + args.w_unc * u + args.w_md_missing * md_miss
        scored.append({**r, "md_select_score": s, "reason": f"P={p:.3f},U={u:.3f},MDmiss={md_miss}"})
    scored.sort(key=lambda x: x["md_select_score"], reverse=True)
    top = scored[: args.top_k]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".json":
        out.write_text(json.dumps({"candidates": top, "n": len(top)}, indent=2), encoding="utf-8")
    else:
        import csv
        if not top:
            out.write_text("", encoding="utf-8")
        else:
            keys = list(top[0].keys())
            with out.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(top)
    print(json.dumps({"ok": True, "n": len(top), "out": str(out)}))


if __name__ == "__main__":
    main()
