"""Convert DiffGUI samples_*.pt -> TargetDiff-format .pt for evaluate_pt_with_correct_reconstruct.py.

DiffGUI 保存格式：EasyDict{finished: [{element(np.array 原子序数), atom_pos(N×3 np.array),
smiles, rdmol, sa, qed, vina_score, ...}], failed: []}
评估器期望：{pred_ligand_pos: [tensor(N,3)], pred_ligand_v: [tensor(N,)](索引编码),
            data: {ligand_filename, protein_filename}, extra_info: [...]}

用 DiffDynamic utils.transforms 的 add_aromatic 映射做原子序数 -> 索引反映射。
集合外原子（如 Br=35）的分子跳过并告警。

用法（diffdynamic 环境，PYTHONPATH 指向 DiffDynamic）：
  conda run -n diffdynamic env PYTHONPATH=/data/ye/DiffDynamic python \
      convert_diffgui_pt_to_eval.py --input_dir <generated> --output <out.pt> \
      --protein_filename 9nfr.pdb [--atom_mode add_aromatic]
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import torch

# 依赖 DiffDynamic 的原子映射
from utils.transforms import (
    MAP_ATOM_TYPE_AROMATIC_TO_INDEX,
    MAP_ATOM_TYPE_ONLY_TO_INDEX,
    MAP_ATOM_TYPE_FULL_TO_INDEX,
)


def build_reverse_map(atom_mode: str) -> dict[int, int]:
    """原子序数 -> 索引（取非芳香/首个索引）。"""
    if atom_mode == "basic":
        return {atomic_num: idx for idx, atomic_num in MAP_ATOM_TYPE_ONLY_TO_INDEX.items()}
    if atom_mode == "add_aromatic":
        rev: dict[int, int] = {}
        for (atomic_num, is_aromatic), idx in MAP_ATOM_TYPE_AROMATIC_TO_INDEX.items():
            # 优先非芳香（is_aromatic=0）索引，其次任意
            if atomic_num not in rev or is_aromatic == 0:
                rev[atomic_num] = idx
        return rev
    if atom_mode == "full":
        rev2: dict[int, int] = {}
        for (atomic_num, _hyb, _aro), idx in MAP_ATOM_TYPE_FULL_TO_INDEX.items():
            if atomic_num not in rev2:
                rev2[atomic_num] = idx
        return rev2
    raise ValueError(f"unknown atom_mode: {atom_mode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", required=True, help="DiffGUI generated 输出目录（含 run_*/samples_*.pt）")
    ap.add_argument("--input_glob", default=None, help="可选：自定义 samples_*.pt glob 模式")
    ap.add_argument("--output", required=True, help="转换后 .pt 输出路径")
    ap.add_argument("--protein_filename", default="9nfr.pdb", help="写入 data.protein_filename（评估受体标识）")
    ap.add_argument("--ligand_filename", default="N/A", help="写入 data.ligand_filename")
    ap.add_argument("--atom_mode", default="add_aromatic", choices=["basic", "add_aromatic", "full"])
    args = ap.parse_args()

    rev = build_reverse_map(args.atom_mode)
    print(f"[convert] atom_mode={args.atom_mode} 支持原子序数: {sorted(rev.keys())}")

    # 收集所有 samples_*.pt
    if args.input_glob:
        pt_files = sorted(glob.glob(args.input_glob))
    else:
        pt_files = sorted(glob.glob(str(Path(args.input_dir) / "**" / "samples_*.pt"), recursive=True))
        if not pt_files:
            pt_files = sorted(glob.glob(str(Path(args.input_dir) / "samples_*.pt")))
    if not pt_files:
        print(f"[convert] 错误：在 {args.input_dir} 未找到 samples_*.pt", file=sys.stderr)
        sys.exit(1)
    print(f"[convert] 发现 {len(pt_files)} 个 .pt 文件:")
    for p in pt_files:
        print(f"  - {p}")

    pred_ligand_pos: list[torch.Tensor] = []
    pred_ligand_v: list[torch.Tensor] = []
    extra_info: list[dict] = []
    total = skipped = 0
    unsupported_atoms: set[int] = set()

    for pt in pt_files:
        pool = torch.load(pt, map_location="cpu", weights_only=False)
        finished = pool.get("finished", []) if isinstance(pool, dict) or hasattr(pool, "get") else []
        for mol in finished:
            total += 1
            element = np.asarray(mol["element"]).reshape(-1).astype(np.int64)
            atom_pos = np.asarray(mol["atom_pos"], dtype=np.float32)
            if atom_pos.ndim != 2 or atom_pos.shape[1] != 3:
                print(f"  [skip] mol#{total} atom_pos 形状异常 {atom_pos.shape}")
                skipped += 1
                continue
            if len(element) != atom_pos.shape[0]:
                print(f"  [skip] mol#{total} element/pos 数量不匹配 {len(element)} vs {atom_pos.shape[0]}")
                skipped += 1
                continue
            # 原子序数 -> 索引
            indices: list[int] = []
            ok = True
            for z in element.tolist():
                if z in rev:
                    indices.append(rev[z])
                else:
                    unsupported_atoms.add(z)
                    ok = False
                    break
            if not ok:
                skipped += 1
                continue
            pred_ligand_pos.append(torch.tensor(atom_pos, dtype=torch.float32))
            pred_ligand_v.append(torch.tensor(indices, dtype=torch.long))
            extra_info.append({
                "smiles": mol.get("smiles", ""),
                "source_pt": Path(pt).name,
                "sa": float(mol.get("sa", 0.0) or 0.0),
                "qed": float(mol.get("qed", 0.0) or 0.0),
                "vina_score": float(mol.get("vina_score", 0.0) or 0.0),
            })

    out = {
        "pred_ligand_pos": pred_ligand_pos,
        "pred_ligand_v": pred_ligand_v,
        "data": {
            "ligand_filename": args.ligand_filename,
            "protein_filename": args.protein_filename,
        },
        "extra_info": extra_info,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    torch.save(out, args.output)

    print(f"\n[convert] 完成：共 {total} 个分子，成功 {len(pred_ligand_pos)}，跳过 {skipped}")
    if unsupported_atoms:
        print(f"[convert] 跳过原因含不支持的原子序数: {sorted(unsupported_atoms)}（add_aromatic 仅支持 "
              f"{sorted(rev.keys())}）")
    print(f"[convert] 输出: {args.output}")
    print(f"[convert] pred_ligand_pos 样本数: {len(pred_ligand_pos)}")
    if pred_ligand_v:
        print(f"[convert] 首样本原子数: {pred_ligand_v[0].numel()}")


if __name__ == "__main__":
    main()
