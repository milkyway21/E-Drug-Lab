"""RDKit 工具集：分子标准化、11 项化学有效性硬检、骨架/片段提取、Morgan 相似度、SMILES 字符串相似度、Lilly 规则、Lipinski。

为 VAV1_DiffGui_GLARE_RL_Project 11 步流水线服务，纯 IO 边界，不掺流程逻辑。
复用 e-drug-lab 的 sa_score / sdf_parser 思路，但不耦合。
"""
from __future__ import annotations

from typing import Optional

from rdkit import Chem
from rdkit.Chem import AllChem, BRICS, Descriptors, DataStructs, QED
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem import FilterCatalog

# CRBN 分子胶锚定片段：glutarimide（来那度胺/沙利度胺核心）与 imide
# 作为 frag_cond 生成时的优先锚定片段 SMARTS（多写法覆盖互变异构）
CRBN_GLUTARIMIDE_SCAFFOLDS = [
    "O=C1CCC(=O)NC1",          # glutarimide 标准写法
    "O=C1CC(=O)NC(=O)C1",      # glutarimide 另一写法
    "O=C1NC(=O)CCC1",          # glutarimide（N 在不同位置）
    "C1CC(=O)NC(=O)C1",        # 不含显式 O= 的环骨架（容忍写法）
    "O=C1NC(=O)CCC1",          # imide 环
]
CRBN_GLUTARIMIDE_SMARTS = [Chem.MolFromSmarts(s) for s in CRBN_GLUTARIMIDE_SCAFFOLDS if Chem.MolFromSmarts(s)]


# ---------------------------------------------------------------------------
# 1. 分子标准化（步骤1 patent 预处理）
# ---------------------------------------------------------------------------
def _strip_salts(mol: Chem.Mol) -> Chem.Mol:
    """剥离盐/溶剂小片段，保留最大片段。"""
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    if len(frags) <= 1:
        return mol
    # 保留重原子数最多的片段
    frags_sorted = sorted(frags, key=lambda m: m.GetNumHeavyAtoms(), reverse=True)
    return frags_sorted[0]


def _neutralize(mol: Chem.Mol) -> Chem.Mol:
    """中和形式电荷（Na+/Cl- 等被剥离后，中和羧酸/胺的正负电荷）。"""
    pattern = Chem.MolFromSmarts("[+1!h0!$([*]~[-1,-2,-3,-4]),-1!$([*]~[+1,+2,+3,+4])]")
    at_matches = mol.GetSubstructMatches(pattern)
    if not at_matches:
        return mol
    for matches in at_matches:
        for atom_idx in matches:
            atom = mol.GetAtomWithIdx(atom_idx)
            chg = atom.GetFormalCharge()
            if chg == 1 and atom.GetTotalNumHs() > 0:
                atom.SetFormalCharge(0)
                atom.SetNumExplicitHs(atom.GetTotalNumHs() - 1)
            elif chg == -1:
                atom.SetFormalCharge(0)
                atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
    return mol


def standardize(smiles: str) -> dict:
    """RDKit 标准化：canonical_smiles / inchikey / mol_valid / duplicate_flag / salt_strip_flag / neutralized_smiles。

    duplicate_flag 在单分子层面恒为 False，由调用方在批量去重时设置。
    """
    result = {
        "smiles_raw": smiles,
        "mol_valid": False,
        "canonical_smiles": None,
        "neutralized_smiles": None,
        "inchikey": None,
        "duplicate_flag": False,
        "salt_strip_flag": False,
    }
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return result
    result["mol_valid"] = True

    # canonical
    try:
        result["canonical_smiles"] = Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        result["canonical_smiles"] = smiles

    # 盐剥离
    stripped = _strip_salts(mol)
    if stripped.GetNumHeavyAtoms() != mol.GetNumHeavyAtoms():
        result["salt_strip_flag"] = True
        mol = stripped

    # 中和
    neutral = _neutralize(mol)
    try:
        result["neutralized_smiles"] = Chem.MolToSmiles(neutral, canonical=True)
    except Exception:
        result["neutralized_smiles"] = result["canonical_smiles"]

    # InChIKey
    try:
        result["inchikey"] = Chem.MolToInchiKey(neutral)
    except Exception:
        result["inchikey"] = None

    return result


# ---------------------------------------------------------------------------
# 2. 11 项化学有效性硬检（步骤3）
# ---------------------------------------------------------------------------
_REACTIVE_SMARTS = [
    Chem.MolFromSmarts(s) for s in [
        "[Si]", "[As]", "[Se]",  # 不常见杂原子
        "C=[N-]", "C=[N+]",       # 异常亚胺
        "[*]#[*]#[*]",            # 累积多键
        "N=N",                    # 偶氮（潜在毒性）
        "[CX3](=O)[OX2H1]",      # 羧酸（标记，未必剔）
    ] if Chem.MolFromSmarts(s)
]


def validity_check_11(smiles: str) -> dict:
    """11 项化学有效性硬检。返回每项 pass/fail + overall + reasons。"""
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    mol = Chem.MolFromSmiles(smiles)
    # 1. RDKit 可解析
    checks["1_rdkit_parseable"] = mol is not None
    if mol is None:
        reasons.append("RDKit 无法解析")
        return {"checks": checks, "overall": False, "reasons": reasons}

    # 确保 RingInfo / 属性缓存初始化（避免复杂分子后续操作触发 C++ 段错误）
    try:
        Chem.SanitizeMol(mol)
        mol.UpdatePropertyCache(strict=False)
        Chem.GetSymmSSSR(mol)
    except Exception:
        pass

    # 2. canonical SMILES 可生成
    try:
        Chem.MolToSmiles(mol, canonical=True)
        checks["2_canonical_smiles"] = True
    except Exception:
        checks["2_canonical_smiles"] = False
        reasons.append("无法生成 canonical SMILES")

    # 3. InChIKey 可生成
    try:
        Chem.MolToInchiKey(mol)
        checks["3_inchikey"] = True
    except Exception:
        checks["3_inchikey"] = False
        reasons.append("无法生成 InChIKey")

    # 4. 连通性：不允许多片段盐作为主分子
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    checks["4_single_fragment"] = len(frags) == 1
    if len(frags) > 1:
        reasons.append(f"多片段（{len(frags)}），疑似盐形式")

    # 5. 价态合理
    try:
        Chem.SanitizeMol(mol, sanitizeOps=Chem.SanitizeFlags.SANITIZE_PROPERTIES)
        checks["5_valence"] = True
    except Exception:
        checks["5_valence"] = False
        reasons.append("价态异常")

    # 6. 芳香性可感知
    try:
        Chem.SanitizeMol(mol, sanitizeOps=Chem.SanitizeFlags.SANITIZE_KEKULIZE)
        checks["6_aromaticity"] = True
    except Exception:
        checks["6_aromaticity"] = False
        reasons.append("芳香性/kekule 异常")

    # 7. 形式电荷不过度异常
    total_charge = sum(a.GetFormalCharge() for a in mol.GetAtoms())
    checks["7_formal_charge"] = abs(total_charge) <= 2
    if abs(total_charge) > 2:
        reasons.append(f"形式电荷异常 {total_charge}")

    # 8. 无明显反应性结构
    reactive_hit = any(mol.HasSubstructMatch(p) for p in _REACTIVE_SMARTS)
    checks["8_no_reactive"] = not reactive_hit
    if reactive_hit:
        reasons.append("含反应性/警示结构")

    # 9. 无严重 PAINS / toxicophore
    try:
        params = FilterCatalog.FilterCatalogParams()
        params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
        catalog = FilterCatalog.FilterCatalog(params)
        pains_hit = catalog.GetFirstMatch(mol) is not None
    except Exception:
        pains_hit = False
    checks["9_no_pains"] = not pains_hit
    if pains_hit:
        reasons.append("PAINS 命中")

    # 10. 三维 SDF 可重构（生成 3D 构象）
    can_3d = False
    try:
        m2 = Chem.AddHs(mol)
        if AllChem.EmbedMolecule(m2, randomSeed=2023, useRandomCoords=True) == 0:
            can_3d = True
    except Exception:
        can_3d = False
    checks["10_3d_reconstructable"] = can_3d
    if not can_3d:
        reasons.append("3D 构象无法重构")

    # 11. 键长/键角/构象应变无严重异常（粗检：MMFF 优化能量不过高）
    strain_ok = True
    if can_3d:
        try:
            mp = AllChem.MMFFGetMoleculeProperties(m2)
            if mp is not None:
                ff = AllChem.MMFFGetMoleculeForceField(m2, mp)
                energy = ff.CalcEnergy()
                # 经验阈值：> 200 kcal/mol 视为严重应变
                strain_ok = energy < 200.0
                if not strain_ok:
                    reasons.append(f"构象应变过高 ({energy:.1f} kcal/mol)")
        except Exception:
            strain_ok = True  # MMFF 失败不阻断
    checks["11_no_severe_strain"] = strain_ok

    overall = all(checks.values())
    return {"checks": checks, "overall": overall, "reasons": reasons}


# ---------------------------------------------------------------------------
# 3. 骨架/片段提取（步骤2 frag_cond 输入）
# ---------------------------------------------------------------------------
def has_crbn_anchor(smiles: str) -> bool:
    """是否含 CRBN imide/glutarimide 锚定片段。"""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    return any(mol.HasSubstructMatch(p) for p in CRBN_GLUTARIMIDE_SMARTS)


def extract_scaffold_fragment(smiles: str, prefer_crbn: bool = True) -> dict:
    """从参考分子提取锚定片段：优先 CRBN imide/glutarimide 子结构，否则 Bemis-Murcko 骨架，再否则 BRICS 片段。

    返回 {source_scaffold_id, source_fragment_smiles, fragment_type, scaffold_smiles}。
    用于 DiffGui frag_cond 模式的 model.frag 输入（需另写 SDF）。
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"source_scaffold_id": None, "source_fragment_smiles": None, "fragment_type": "invalid", "scaffold_smiles": None}

    # 1. 优先 CRBN 锚定片段
    if prefer_crbn:
        for smart_mol in CRBN_GLUTARIMIDE_SMARTS:
            if mol.HasSubstructMatch(smart_mol):
                # 截取匹配子结构为片段
                match = mol.GetSubstructMatch(smart_mol)
                frag = Chem.PathToSubmol(mol, list(match))
                if frag is not None:
                    return {
                        "source_scaffold_id": smiles[:40],
                        "source_fragment_smiles": Chem.MolToSmiles(frag),
                        "fragment_type": "crbn_anchor",
                        "scaffold_smiles": MurckoScaffold.MurckoScaffoldSmiles(mol=mol),
                    }

    # 2. Bemis-Murcko 骨架
    try:
        scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=False)
        if scaffold:
            return {
                "source_scaffold_id": smiles[:40],
                "source_fragment_smiles": scaffold,
                "fragment_type": "murcko_scaffold",
                "scaffold_smiles": scaffold,
            }
    except Exception:
        pass

    # 3. BRICS 片段分解（取最大片段）
    try:
        frags = BRICS.BRICSDecompose(mol)
        if frags:
            # 选非 [*] 端点最大的
            cleaned = []
            for f in frags:
                f = f.replace("[*]", "")
                m = Chem.MolFromSmiles(f)
                if m:
                    cleaned.append(m)
            if cleaned:
                biggest = max(cleaned, key=lambda m: m.GetNumHeavyAtoms())
                return {
                    "source_scaffold_id": smiles[:40],
                    "source_fragment_smiles": Chem.MolToSmiles(biggest),
                    "fragment_type": "brics_fragment",
                    "scaffold_smiles": MurckoScaffold.MurckoScaffoldSmiles(mol=mol),
                }
    except Exception:
        pass

    return {"source_scaffold_id": smiles[:40], "source_fragment_smiles": smiles, "fragment_type": "fallback_whole", "scaffold_smiles": None}


def fragment_to_sdf(fragment_smiles: str, sdf_path: str) -> str:
    """把片段 SMILES 写成 3D SDF（供 DiffGui model.frag 使用）。"""
    mol = Chem.MolFromSmiles(fragment_smiles)
    if mol is None:
        raise ValueError(f"无效片段 SMILES: {fragment_smiles}")
    mol = Chem.AddHs(mol)
    AllChem.EmbedMolecule(mol, randomSeed=2023)
    try:
        AllChem.MMFFOptimizeMolecule(mol)
    except Exception:
        pass
    mol = Chem.RemoveHs(mol)
    Chem.MolToMolFile(mol, sdf_path)
    return sdf_path


# ---------------------------------------------------------------------------
# 4. Morgan 相似度（步骤6 去重 + 步骤9 与36自合成相似）
# ---------------------------------------------------------------------------
def _morgan_fp(mol: Chem.Mol, radius: int = 2, n_bits: int = 2048):
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)


def morgan_tanimoto(query_smiles: str, reference_smiles_list: list[str], radius: int = 2, n_bits: int = 2048) -> dict:
    """计算 query 与一批 reference 的 Morgan Tanimoto，返回 max + nearest。"""
    qmol = Chem.MolFromSmiles(query_smiles)
    if qmol is None:
        return {"max_morgan_tanimoto": 0.0, "nearest_ref_id": None, "all_sims": []}
    qfp = _morgan_fp(qmol, radius, n_bits)
    sims = []
    best, best_id = 0.0, None
    for i, ref_smi in enumerate(reference_smiles_list):
        rmol = Chem.MolFromSmiles(ref_smi)
        if rmol is None:
            sims.append(0.0)
            continue
        s = DataStructs.TanimotoSimilarity(qfp, _morgan_fp(rmol, radius, n_bits))
        sims.append(float(s))
        if s > best:
            best, best_id = float(s), i
    return {"max_morgan_tanimoto": best, "nearest_ref_id": best_id, "all_sims": sims}


def morgan_tanimoto_batch(
    candidate_smiles: list[str],
    reference_smiles_list: list[str],
    radius: int = 2,
    n_bits: int = 2048,
) -> list[dict]:
    """批量：每个 candidate 对所有 reference 的最大 Tanimoto + nearest index。"""
    ref_fps = []
    for smi in reference_smiles_list:
        m = Chem.MolFromSmiles(smi)
        ref_fps.append(_morgan_fp(m, radius, n_bits) if m else None)
    out = []
    for cand in candidate_smiles:
        cm = Chem.MolFromSmiles(cand)
        if cm is None:
            out.append({"max_morgan_tanimoto": 0.0, "nearest_ref_id": None})
            continue
        cfp = _morgan_fp(cm, radius, n_bits)
        best, best_id = 0.0, None
        for i, rfp in enumerate(ref_fps):
            if rfp is None:
                continue
            s = DataStructs.TanimotoSimilarity(cfp, rfp)
            if s > best:
                best, best_id = float(s), i
        out.append({"max_morgan_tanimoto": best, "nearest_ref_id": best_id})
    return out


# ---------------------------------------------------------------------------
# 5. SMILES 字符串相似度（辅助，步骤9）
# ---------------------------------------------------------------------------
def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        cur = [i + 1]
        for j, cb in enumerate(b):
            cur.append(min(prev[j + 1] + 1, cur[j] + 1, prev[j] + (ca != cb)))
        prev = cur
    return prev[-1]


def smiles_string_similarity(s1: str, s2: str) -> float:
    """normalized Levenshtein similarity ∈ [0,1]，1 表示完全相同。"""
    if not s1 and not s2:
        return 1.0
    d = _levenshtein(s1, s2)
    return 1.0 - d / max(len(s1), len(s2))


# ---------------------------------------------------------------------------
# 6. Lilly MedChem 规则 + Lipinski（步骤4）
# ---------------------------------------------------------------------------
_LILLY_RULES = [
    # (name, SMARTS, penalty) —— 简化版 Lilly 药物化学警示规则
    ("acyclic_C_chain_long", Chem.MolFromSmarts("[CX4;R0][CX4;R0][CX4;R0][CX4;R0][CX4;R0][CX4;R0]"), 20),
    ("thiol", Chem.MolFromSmarts("[#6][SX2H1]"), 50),
    ("aldehyde", Chem.MolFromSmarts("[CX3H1](=O)[#6]"), 30),
    ("imine_schiff", Chem.MolFromSmarts("[CX2]=[NX2]"), 30),
    ("diazene", Chem.MolFromSmarts("[NX2]=[NX2]"), 50),
    ("peroxide", Chem.MolFromSmarts("[OX2][OX2]"), 50),
    ("beta_lactam", Chem.MolFromSmarts("C1(=O)NC1"), 0),  # 分子胶非目标，仅标记
]
_LILLY_RULES = [(n, p, pen) for n, p, pen in _LILLY_RULES if p is not None]


def lilly_score(mol: Chem.Mol) -> dict:
    """Lilly MedChem 规则打分：penalty 越高越差。score = sum(penalty)；>100 视为不合格。

    返回 {lilly_score, passed, deductions, descriptions}。
    """
    total = 0
    deductions = []
    for name, patt, pen in _LILLY_RULES:
        if mol.HasSubstructMatch(patt):
            total += pen
            deductions.append(f"{name}:{pen}")
    return {
        "lilly_score": total,
        "passed": total <= 100,
        "deductions": total,
        "descriptions": "; ".join(deductions),
    }


def lipinski_pass_count(mol: Chem.Mol) -> dict:
    """Lipinski RO5 满足条数（0-4）。<4 视为不合格。"""
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    count = sum([mw <= 500, logp <= 5, hbd <= 5, hba <= 10])
    return {
        "lipinski_pass_count": count,
        "passed": count >= 4,
        "mw": round(mw, 2),
        "logp": round(logp, 2),
        "hbd": hbd,
        "hba": hba,
    }


def druglikeness_descriptors(mol: Chem.Mol) -> dict:
    """一次性算全步骤4 需要的描述符。"""
    return {
        "mw": round(Descriptors.MolWt(mol), 2),
        "logp": round(Descriptors.MolLogP(mol), 2),
        "tpsa": round(Descriptors.TPSA(mol), 2),
        "qed": round(QED.qed(mol), 4),
        "hbd": Descriptors.NumHDonors(mol),
        "hba": Descriptors.NumHAcceptors(mol),
        "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
        "aromatic_rings": Chem.Lipinski.NumAromaticRings(mol),
    }


# ---------------------------------------------------------------------------
# 7. 去重辅助（步骤6）
# ---------------------------------------------------------------------------
def inchikey_first_block(inchikey: Optional[str]) -> Optional[str]:
    if not inchikey:
        return None
    return inchikey.split("-")[0]


def dedup_check(
    candidate: dict,
    ref_canonical_set: set[str],
    ref_inchikey_set: set[str],
    ref_inchikey_firstblock_set: set[str],
    ref_morgan_fps: list,
    radius: int = 2,
    n_bits: int = 2048,
    near_dup_threshold: float = 0.95,
) -> dict:
    """单分子去重判定。candidate 需含 canonical_smiles/inchikey/mol。

    返回 flags + reject（是否剔除）+ reason。
    规则：canonical 同/InChIKey 同/Morgan=1.0 → 剔除；InChIKey 首段同 → same_connectivity 默认剔；
         Morgan≥0.95 → near_duplicate 不进最终优先。
    """
    can = candidate.get("canonical_smiles")
    ik = candidate.get("inchikey")
    ik_first = inchikey_first_block(ik)
    mol = candidate.get("mol")

    flags = []
    reject = False
    reason = None

    if can and can in ref_canonical_set:
        reject, reason = True, "canonical_smiles 完全相同"
        flags.append("exact_smiles_dup")
    elif ik and ik in ref_inchikey_set:
        reject, reason = True, "InChIKey 完全相同"
        flags.append("exact_inchikey_dup")
    elif mol is not None:
        cfp = _morgan_fp(mol, radius, n_bits)
        from rdkit import DataStructs as _DS
        max_sim = 0.0
        for rfp in ref_morgan_fps:
            if rfp is None:
                continue
            s = _DS.TanimotoSimilarity(cfp, rfp)
            if s > max_sim:
                max_sim = s
        if max_sim >= 0.999:
            reject, reason = True, "Morgan Tanimoto = 1.0"
            flags.append("morgan_dup")
        elif max_sim >= near_dup_threshold:
            flags.append("near_duplicate")
            reason = f"Morgan Tanimoto {max_sim:.3f} ≥ {near_dup_threshold}（near_duplicate，不进最终优先）"
        if ik_first and ik_first in ref_inchikey_firstblock_set and not reject:
            flags.append("same_connectivity")
            reject, reason = True, "InChIKey 首段相同（same_connectivity）"

    return {"reject": reject, "reason": reason, "flags": flags}
