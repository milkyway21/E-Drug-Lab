"""分子骨架提取服务 —— 轻量级 RDKit 工具，不做数据库持久化。
供分子库构建和生成流程前置步骤使用。

支持：Bemis-Murcko 骨架泛化 + 详细骨架 + 去重 + 分组 + 2D 渲染。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from rdkit import Chem
from rdkit.Chem import AllChem, Draw
from rdkit.Chem.Scaffolds import MurckoScaffold


# ---------------------------------------------------------------------------
# 核心提取
# ---------------------------------------------------------------------------
def extract_scaffolds(smiles_list: list[str], names: Optional[list[str]] = None) -> dict:
    """批量提取 Bemis-Murcko 骨架。

    Args:
        smiles_list: SMILES 列表
        names: 可选的分子名列表，与 smiles_list 等长

    Returns:
        {
            "molecules": [{idx, name, smiles, murcko_generic, murcko_detailed, murcko_framework, success}],
            "unique_scaffolds": [{scaffold_smiles, member_count, representative_name, representative_smiles}],
            "scaffold_groups": {scaffold_smiles: [{idx, name, smiles}]},
            "stats": {total, success, failed, unique_generic, unique_framework},
        }
    """
    if names is None:
        names = [f"mol_{i:04d}" for i in range(len(smiles_list))]

    molecules = []
    scaffold_groups: dict[str, list[dict]] = defaultdict(list)
    failed = 0

    for idx, smi in enumerate(smiles_list):
        name = names[idx] if idx < len(names) else f"mol_{idx:04d}"
        mol = Chem.MolFromSmiles(str(smi))
        if mol is None:
            molecules.append(
                {
                    "idx": idx,
                    "name": name,
                    "smiles": str(smi),
                    "murcko_generic": None,
                    "murcko_detailed": None,
                    "murcko_framework": None,
                    "success": False,
                }
            )
            failed += 1
            continue

        try:
            Chem.SanitizeMol(mol)
        except Exception:
            pass

        generic = None
        detailed = None
        framework = None

        try:
            generic = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)
        except Exception:
            pass

        try:
            detailed = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
        except Exception:
            pass

        try:
            fw_mol = MurckoScaffold.GetScaffoldForMol(mol)
            if fw_mol:
                framework = Chem.MolToSmiles(fw_mol)
        except Exception:
            pass

        entry = {
            "idx": idx,
            "name": name,
            "smiles": str(smi),
            "murcko_generic": generic,
            "murcko_detailed": detailed,
            "murcko_framework": framework,
            "success": True,
        }
        molecules.append(entry)
        if generic:
            scaffold_groups[generic].append({"idx": idx, "name": name, "smiles": str(smi)})

    # 去重
    unique_generic: dict[str, dict] = {}
    unique_framework: dict[str, dict] = {}
    for m in molecules:
        if m["success"] and m["murcko_generic"] and m["murcko_generic"] not in unique_generic:
            unique_generic[m["murcko_generic"]] = {
                "scaffold_smiles": m["murcko_generic"],
                "representative_name": m["name"],
                "representative_smiles": m["smiles"],
            }
        if m["success"] and m["murcko_framework"] and m["murcko_framework"] not in unique_framework:
            unique_framework[m["murcko_framework"]] = {
                "scaffold_smiles": m["murcko_framework"],
                "representative_name": m["name"],
                "representative_smiles": m["smiles"],
            }

    # 按成员数排序
    sorted_unique = sorted(
        [{"scaffold_smiles": k, "member_count": len(scaffold_groups[k]), **v}
         for k, v in unique_generic.items()],
        key=lambda x: -x["member_count"],
    )

    return {
        "molecules": molecules,
        "unique_scaffolds": sorted_unique,
        "scaffold_groups": {k: v for k, v in scaffold_groups.items()},
        "stats": {
            "total": len(smiles_list),
            "success": len(smiles_list) - failed,
            "failed": failed,
            "unique_generic": len(unique_generic),
            "unique_framework": len(unique_framework),
        },
    }


# ---------------------------------------------------------------------------
# 从化合物库提取
# ---------------------------------------------------------------------------
def extract_from_library_sdf(sdf_path: str) -> dict:
    """从 SDF 文件提取所有分子的 Murcko 骨架。"""
    supplier = Chem.SDMolSupplier(sdf_path)
    smiles_list = []
    names = []
    for i, mol in enumerate(supplier):
        if mol is None:
            continue
        try:
            smi = Chem.MolToSmiles(mol)
            name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"mol_{i:04d}"
        except Exception:
            continue
        smiles_list.append(smi)
        names.append(name)
    return extract_scaffolds(smiles_list, names)


# ---------------------------------------------------------------------------
# 2D 骨架图渲染
# ---------------------------------------------------------------------------
def draw_scaffold(smiles: str, size: tuple[int, int] = (400, 300)) -> bytes | None:
    """把骨架 SMILES 渲染为 PNG 字节流。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    try:
        AllChem.Compute2DCoords(mol)
        img = Draw.MolToImage(mol, size=size)
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 健康检查（无外部依赖）
# ---------------------------------------------------------------------------
def check_health() -> dict:
    return {"rdkit_available": True, "murcko_scaffold": True}
