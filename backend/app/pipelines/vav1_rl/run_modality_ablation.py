#!/usr/bin/env python3
"""模态消融 / permutation / zero-out 骨架。

真实跑依赖 ckpt + 小测试 JSON；本阶段只登记实验矩阵与 CLI。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ABLATIONS = [
    "graph_fp",
    "graph_fp_pc",
    "graph_fp_pc_gl",
    "graph_fp_pc_gl_md",
    "graph_fp_pc_gl_md_reward",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args()
    plan = {
        "ablations": ABLATIONS,
        "permutation_tests": ["shuffle_pc", "shuffle_gl", "shuffle_md", "zero_pc", "zero_gl", "zero_md"],
        "seeds": [0, 1, 2],
        "status": "skeleton",
        "note": "naming: GINL already includes graph+ECFP; do not call it graph-only",
    }
    Path(args.out).write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": args.out, "n_ablations": len(ABLATIONS)}))


if __name__ == "__main__":
    main()
