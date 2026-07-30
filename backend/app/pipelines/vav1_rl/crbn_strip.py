"""整体切除 CRBN 锚定模块：邻氯苯 + 戊二酰亚胺/二氢尿嘧啶（C/N 连接）。

用于 GLARE 指纹/图/101D 表征预处理。Glide/MD 全配体观测不走此函数。
纯 IO：输入 SMILES → 结构化结果，不含训练流程逻辑。
"""
from __future__ import annotations

from typing import Any, Optional

from rdkit import Chem

_MIN_HEAVY_ATOMS = 5

# 匹配优先级：邻氯 C/N → 二氢尿嘧啶 N-芳基 → 邻/间/对 fallback
# [*:1] = warhead 侧保留原子；整块删除氯苯(或苯)+锚定环
_STRIP_PATTERNS: list[tuple[str, str]] = [
    (
        "C_orthoCl",
        "[*:1]-[c]1[c]([Cl])[c]([C]2[C](=O)[N][C](=O)[C][C]2)[c][c][c]1",
    ),
    (
        "N_orthoCl",
        "[*:1]-[c]1[c]([Cl])[c]([N]2[C](=O)[C][C][C](=O)2)[c][c][c]1",
    ),
    (
        "C_orthoCl_alt",
        "[*:1]-[c]1[c]([C]2[C](=O)[N][C](=O)[C][C]2)[c]([Cl])[c][c][c]1",
    ),
    # wetlab: O=C1CCN(c2cccc(*)c2Cl)C(=O)N1  — N 与 Cl 同碳、warhead 间/对位
    (
        "N_du_Cl",
        "[*:1]-[c]1[c][c][c][c]([N]2[C](=O)[N][C](=O)[C][C]2)[c]1[Cl]",
    ),
    (
        "N_du_Cl_meta",
        "[*:1]-[c]1[c][c]([N]2[C](=O)[N][C](=O)[C][C]2)[c]([Cl])[c][c]1",
    ),
    (
        "N_du_Cl_ortho",
        "[*:1]-[c]1[c]([Cl])[c]([N]2[C](=O)[N][C](=O)[C][C]2)[c][c][c]1",
    ),
    (
        "C_ortho",
        "[*:1]-[c]1[c]([C]2[C](=O)[N][C](=O)[C][C]2)[c][c][c][c]1",
    ),
    (
        "C_meta",
        "[*:1]-[c]1[c][c]([C]2[C](=O)[N][C](=O)[C][C]2)[c][c][c]1",
    ),
    (
        "C_para",
        "[*:1]-[c]1[c][c][c]([C]2[C](=O)[N][C](=O)[C][C]2)[c][c]1",
    ),
    (
        "N_ortho",
        "[*:1]-[c]1[c]([N]2[C](=O)[C][C][C](=O)2)[c][c][c][c]1",
    ),
    (
        "N_meta",
        "[*:1]-[c]1[c][c]([N]2[C](=O)[C][C][C](=O)2)[c][c][c]1",
    ),
    (
        "N_para",
        "[*:1]-[c]1[c][c][c]([N]2[C](=O)[C][C][C](=O)2)[c][c]1",
    ),
    (
        "N_du",
        "[*:1]-[c]1[c][c][c][c]([N]2[C](=O)[N][C](=O)[C][C]2)[c]1",
    ),
]

_COMPILED: list[tuple[str, Chem.Mol]] = []
for _name, _smarts in _STRIP_PATTERNS:
    _pat = Chem.MolFromSmarts(_smarts)
    if _pat is not None:
        _COMPILED.append((_name, _pat))

_GLUTARIMIDE_DETECT = [
    Chem.MolFromSmarts(s)
    for s in (
        "O=C1CCC(=O)NC1",
        "O=C1NC(=O)CCC1",
        "C1CC(=O)NC(=O)C1",
        "O=C1CCNC(=O)N1",
        "[N]1[C](=O)[N][C](=O)[C][C]1",
        "[c]-[N]1[C](=O)[N][C](=O)[C][C]1",
        "[c]-[C]1[C](=O)[N][C](=O)[C][C]1",
    )
    if Chem.MolFromSmarts(s)
]

# 切后残留：仅拒仍连在芳环上的 CRBN 式锚定（允许 warhead 另有酰亚胺）
_CRBN_MODULE_REMAIN = [
    Chem.MolFromSmarts(s)
    for s in (
        "[c]-[C]1[C](=O)[N][C](=O)[C][C]1",
        "[c]-[C]1[C](=O)[N][C](=O)[C][C][C]1",
        "[c]-[N]1[C](=O)[C][C][C](=O)1",
        "[c]-[N]1[C](=O)[C][C][C][C](=O)1",
        "[c]-[N]1[C](=O)[N][C](=O)[C][C]1",
        "[c]1([Cl])[c]([N,C]2[C](=O)[N,C][C](=O)[C][C]2)[c][c][c][c]1",
    )
    if Chem.MolFromSmarts(s)
]


def _map1_index(pat: Chem.Mol) -> Optional[int]:
    for atom in pat.GetAtoms():
        if atom.GetAtomMapNum() == 1:
            return atom.GetIdx()
    return None


def has_glutarimide(mol: Chem.Mol) -> bool:
    return any(mol.HasSubstructMatch(p) for p in _GLUTARIMIDE_DETECT if p is not None)


def has_crbn_module_remain(mol: Chem.Mol) -> bool:
    return any(mol.HasSubstructMatch(p) for p in _CRBN_MODULE_REMAIN if p is not None)


def has_ortho_cl_anchor(mol: Chem.Mol) -> bool:
    for name, pat in _COMPILED:
        if "Cl" in name and mol.HasSubstructMatch(pat):
            return True
    return False


def strip_crbn_anchor_module(smiles: str) -> dict[str, Any]:
    """切除邻氯苯–戊二酰亚胺/二氢尿嘧啶整体锚定模块。"""
    result: dict[str, Any] = {
        "smiles_raw": smiles,
        "smiles_stripped": None,
        "inchikey_stripped": None,
        "strip_mode": "failed",
        "had_glutarimide": False,
        "had_ortho_cl": False,
        "ok": False,
        "error": None,
    }
    if not smiles or not str(smiles).strip():
        result["error"] = "empty_smiles"
        return result

    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        result["error"] = "invalid_smiles"
        return result

    result["had_glutarimide"] = has_glutarimide(mol)
    result["had_ortho_cl"] = has_ortho_cl_anchor(mol)

    if not result["had_glutarimide"]:
        can = Chem.MolToSmiles(mol, canonical=True)
        result["smiles_stripped"] = can
        try:
            result["inchikey_stripped"] = Chem.MolToInchiKey(mol)
        except Exception:
            result["inchikey_stripped"] = None
        result["strip_mode"] = "no_anchor"
        result["ok"] = True
        return result

    last_err: Optional[str] = None
    for mode, pat in _COMPILED:
        if not mol.HasSubstructMatch(pat):
            continue
        map1 = _map1_index(pat)
        if map1 is None:
            last_err = f"{mode}:no_map1"
            continue
        for match in mol.GetSubstructMatches(pat):
            keep = match[map1]
            remove = set(match) - {keep}
            rw = Chem.RWMol(mol)
            for idx in sorted(remove, reverse=True):
                rw.RemoveAtom(idx)
            try:
                Chem.SanitizeMol(rw)
            except Exception as e:
                last_err = f"{mode}:sanitize:{e}"
                continue
            # 切除后可能留下游离碎片；只保留最大片段
            try:
                frags = Chem.GetMolFrags(rw, asMols=True, sanitizeFrags=True)
                if not frags:
                    last_err = f"{mode}:no_frags"
                    continue
                rw = max(frags, key=lambda m: m.GetNumHeavyAtoms())
                Chem.SanitizeMol(rw)
            except Exception as e:
                last_err = f"{mode}:frag:{e}"
                continue
            if rw.GetNumHeavyAtoms() < _MIN_HEAVY_ATOMS:
                last_err = f"{mode}:too_small"
                continue
            # 仅检查 CRBN 式芳基锚定是否仍在；warhead 上独立酰亚胺允许
            if has_crbn_module_remain(rw) and has_ortho_cl_anchor(rw):
                last_err = f"{mode}:crbn_module_remain"
                continue
            can = Chem.MolToSmiles(rw, canonical=True)
            result["smiles_stripped"] = can
            try:
                result["inchikey_stripped"] = Chem.MolToInchiKey(rw)
            except Exception:
                result["inchikey_stripped"] = None
            result["strip_mode"] = mode
            result["ok"] = True
            result["error"] = None
            return result

    result["error"] = last_err or "no_match"
    result["strip_mode"] = "failed"
    return result


def strip_smiles_or_raise(smiles: str) -> str:
    r = strip_crbn_anchor_module(smiles)
    if not r["ok"] or not r["smiles_stripped"]:
        raise ValueError(f"CRBN strip failed for {smiles!r}: {r.get('error')}")
    return r["smiles_stripped"]
