"""湿实验交接服务 — 桥接计算筛选与药物化学湿实验环节。

覆盖药物科学家在送合成/测活性前通常需要的信息：
- 化合物注册号、可合成性（SA）、结构警报（PAINS/Brenk/NIH）
- 手性中心、反应性基团、DMSO 母液配制
- PubChem 精确匹配（商业化合物线索）
- 合成订单包 + 活性测定结果回填模板（兼容 GLARE wetlab 导入）
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem import FilterCatalog

from app.services.sa_score import compute_sa_score
from app.services.xlsx_report import build_xlsx_bytes

logger = logging.getLogger(__name__)

# 湿实验常见需关注反应性基团（SMARTS → 描述）
REACTIVE_GROUP_PATTERNS: list[tuple[str, str]] = [
    ("[CH1](=O)", "醛基 — 易氧化/聚合"),
    ("N=C=O", "异氰酸酯 — 高反应性"),
    ("C(=O)Cl", "酰氯 — 腐蚀性/需无水"),
    ("C1OC1", "环氧 — 开环反应性"),
    ("[N+](=O)[O-]", "硝基 — 还原/代谢关注"),
    ("S(=O)(=O)Cl", "磺酰氯 — 高反应性"),
    ("C#N", "腈基 — 水解/毒性关注"),
]

@dataclass
class WetlabMoleculePrep:
    compound_id: str
    smiles: str
    name: Optional[str] = None
    rank: Optional[int] = None
    molecular_weight: Optional[float] = None
    logp: Optional[float] = None
    tpsa: Optional[float] = None
    hbd: Optional[int] = None
    hba: Optional[int] = None
    rotatable_bonds: Optional[int] = None
    qed: Optional[float] = None
    sa_score: Optional[float] = None
    chiral_centers: int = 0
    achiral: bool = True
    lipinski_pass: bool = True
    veber_pass: bool = True
    structural_alerts: list[str] = field(default_factory=list)
    structural_warnings: list[str] = field(default_factory=list)
    reactive_groups: list[str] = field(default_factory=list)
    synthesis_risk: str = "low"
    dmso_stock_mg_10mm_1ml: Optional[float] = None
    dmso_note: str = ""
    pubchem_cid: Optional[int] = None
    pubchem_url: Optional[str] = None
    sourcing_hint: str = "unknown"
    wetlab_ready: bool = True
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compound_id": self.compound_id,
            "smiles": self.smiles,
            "name": self.name,
            "rank": self.rank,
            "molecular_weight": self.molecular_weight,
            "logp": self.logp,
            "tpsa": self.tpsa,
            "hbd": self.hbd,
            "hba": self.hba,
            "rotatable_bonds": self.rotatable_bonds,
            "qed": self.qed,
            "sa_score": self.sa_score,
            "chiral_centers": self.chiral_centers,
            "achiral": self.achiral,
            "lipinski_pass": self.lipinski_pass,
            "veber_pass": self.veber_pass,
            "structural_alerts": self.structural_alerts,
            "structural_warnings": self.structural_warnings,
            "reactive_groups": self.reactive_groups,
            "synthesis_risk": self.synthesis_risk,
            "dmso_stock_mg_10mm_1ml": self.dmso_stock_mg_10mm_1ml,
            "dmso_note": self.dmso_note,
            "pubchem_cid": self.pubchem_cid,
            "pubchem_url": self.pubchem_url,
            "sourcing_hint": self.sourcing_hint,
            "wetlab_ready": self.wetlab_ready,
            "blockers": self.blockers,
            "notes": self.notes,
        }


def _make_compound_id(target_code: str, batch_id: str, index: int) -> str:
    safe_target = "".join(c for c in (target_code or "UNK").upper() if c.isalnum())[:12] or "UNK"
    safe_batch = "".join(c for c in (batch_id or "B1") if c.isalnum())[:8] or "B1"
    return f"EDL-{safe_target}-{safe_batch}-{index:03d}"


def _check_structural_alerts(mol: Chem.Mol) -> tuple[list[str], list[str]]:
    """返回 (硬阻断警报, 软警告)。"""
    blockers: list[str] = []
    warnings: list[str] = []
    pains_params = FilterCatalog.FilterCatalogParams()
    pains_params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
    pains_catalog = FilterCatalog.FilterCatalog(pains_params)
    pains_match = pains_catalog.GetFirstMatch(mol)
    if pains_match:
        blockers.append(f"PAINS: {pains_match.GetDescription()}")

    for catalog_name in (
        FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK,
        FilterCatalog.FilterCatalogParams.FilterCatalogs.NIH,
    ):
        params = FilterCatalog.FilterCatalogParams()
        params.AddCatalog(catalog_name)
        catalog = FilterCatalog.FilterCatalog(params)
        match = catalog.GetFirstMatch(mol)
        if match:
            warnings.append(f"{catalog_name.name}: {match.GetDescription()}")
    return blockers, warnings


def _check_reactive_groups(mol: Chem.Mol) -> list[str]:
    found: list[str] = []
    for smarts, label in REACTIVE_GROUP_PATTERNS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern and mol.HasSubstructMatch(pattern):
            found.append(label)
    return found


def _count_chiral_centers(mol: Chem.Mol) -> int:
    try:
        return int(rdMolDescriptors.CalcNumAtomStereoCenters(mol))
    except Exception:
        return 0


def _dmso_stock_mg(mw: float, concentration_mm: float = 10.0, volume_ml: float = 1.0) -> float:
    """母液质量 (mg) = MW × 浓度(mM) × 体积(L)。"""
    return round(mw * concentration_mm * (volume_ml / 1000.0), 2)


def _assess_synthesis_risk(
    sa: Optional[float],
    alert_blockers: list[str],
    alert_warnings: list[str],
    reactive: list[str],
    chiral: int,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = list(alert_blockers)
    notes: list[str] = list(alert_warnings)

    if sa is not None and sa > 6.0:
        blockers.append(f"SA={sa:.1f} > 6.0，合成难度高")
    elif sa is not None and sa > 4.5:
        notes.append(f"SA={sa:.1f}，建议资深合成化学家评估路线")

    if len(reactive) >= 2:
        notes.append("含多个反应性基团，储存与配制需注意")

    if chiral > 0:
        notes.append(f"含 {chiral} 个手性中心，需明确立体化学（对映体/非对映体）")

    if blockers:
        return "high", blockers, notes
    if notes or reactive:
        extra = [f"反应性: {r}" for r in reactive[:2]]
        return "medium", blockers, notes + extra
    return "low", blockers, notes


def lookup_pubchem(smiles: str, timeout: float = 8.0) -> dict[str, Any]:
    """PubChem 精确 SMILES 匹配，用于商业化合物采购线索。"""
    try:
        encoded = urllib.parse.quote(smiles, safe="")
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{encoded}/cids/JSON"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        cids = data.get("IdentifierList", {}).get("CID", [])
        if cids:
            cid = int(cids[0])
            return {
                "pubchem_cid": cid,
                "pubchem_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
                "sourcing_hint": "pubchem_exact_match",
            }
    except Exception as exc:
        logger.debug("PubChem lookup failed for %s: %s", smiles[:40], exc)
    return {
        "pubchem_cid": None,
        "pubchem_url": None,
        "sourcing_hint": "custom_synthesis",
    }


def analyze_molecule(
    smiles: str,
    *,
    name: Optional[str] = None,
    rank: Optional[int] = None,
    index: int = 1,
    target_code: str = "UNK",
    batch_id: str = "B1",
    check_pubchem: bool = True,
    dmso_concentration_mm: float = 10.0,
    dmso_volume_ml: float = 1.0,
) -> WetlabMoleculePrep:
    compound_id = _make_compound_id(target_code, batch_id, index)
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return WetlabMoleculePrep(
            compound_id=compound_id,
            smiles=smiles,
            name=name,
            rank=rank,
            wetlab_ready=False,
            synthesis_risk="high",
            blockers=["无效 SMILES"],
            sourcing_hint="invalid",
        )

    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = Descriptors.TPSA(mol)
    hbd = Lipinski.NumHDonors(mol)
    hba = Lipinski.NumHAcceptors(mol)
    rotb = Lipinski.NumRotatableBonds(mol)
    try:
        from rdkit.Chem import QED
        qed = QED.qed(mol)
    except Exception:
        qed = None

    sa = compute_sa_score(mol)
    alert_blockers, alert_warnings = _check_structural_alerts(mol)
    reactive = _check_reactive_groups(mol)
    chiral = _count_chiral_centers(mol)

    lipinski_pass = mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10
    veber_pass = rotb <= 10 and tpsa <= 140

    risk, blockers, notes = _assess_synthesis_risk(sa, alert_blockers, alert_warnings, reactive, chiral)

    dmso_mg = _dmso_stock_mg(mw, dmso_concentration_mm, dmso_volume_ml)
    dmso_note = f"{dmso_concentration_mm} mM in {dmso_volume_ml} mL DMSO → 称量 {dmso_mg} mg"

    pubchem = lookup_pubchem(smiles) if check_pubchem else {
        "pubchem_cid": None, "pubchem_url": None, "sourcing_hint": "skipped",
    }

    if pubchem["sourcing_hint"] == "pubchem_exact_match":
        notes.append("PubChem 有精确匹配 — 可优先查 Enamine/MCule/MolPort 现货")

    wetlab_ready = len(blockers) == 0

    return WetlabMoleculePrep(
        compound_id=compound_id,
        smiles=smiles,
        name=name,
        rank=rank,
        molecular_weight=round(mw, 2),
        logp=round(logp, 2),
        tpsa=round(tpsa, 2),
        hbd=hbd,
        hba=hba,
        rotatable_bonds=rotb,
        qed=round(qed, 3) if qed is not None else None,
        sa_score=round(sa, 2) if sa is not None else None,
        chiral_centers=chiral,
        achiral=chiral == 0,
        lipinski_pass=lipinski_pass,
        veber_pass=veber_pass,
        structural_alerts=alert_blockers,
        structural_warnings=alert_warnings,
        reactive_groups=reactive,
        synthesis_risk=risk,
        dmso_stock_mg_10mm_1ml=dmso_mg,
        dmso_note=dmso_note,
        pubchem_cid=pubchem.get("pubchem_cid"),
        pubchem_url=pubchem.get("pubchem_url"),
        sourcing_hint=str(pubchem.get("sourcing_hint", "unknown")),
        wetlab_ready=wetlab_ready,
        blockers=blockers,
        notes=notes,
    )


def analyze_batch(
    molecules: list[dict[str, Any]],
    *,
    target_code: str = "UNK",
    batch_id: str = "B1",
    check_pubchem: bool = True,
    dmso_concentration_mm: float = 10.0,
    dmso_volume_ml: float = 1.0,
) -> list[WetlabMoleculePrep]:
    results: list[WetlabMoleculePrep] = []
    for i, mol in enumerate(molecules, start=1):
        smiles = mol.get("smiles") or ""
        results.append(
            analyze_molecule(
                smiles,
                name=mol.get("name"),
                rank=mol.get("rank"),
                index=i,
                target_code=target_code,
                batch_id=batch_id,
                check_pubchem=check_pubchem,
                dmso_concentration_mm=dmso_concentration_mm,
                dmso_volume_ml=dmso_volume_ml,
            )
        )
    return results


def build_order_pack_xlsx(
    preps: list[WetlabMoleculePrep],
    *,
    target_name: str = "",
    assay_type: str = "BRET / pDC50",
    cell_line: str = "",
    target_protein: str = "",
    round_id: int = 1,
) -> bytes:
    """多 Sheet 订单包：合成订单 + DMSO 配制 + 活性回填模板 + 检查清单。"""
    order_headers = [
        "compound_id", "rank", "name", "smiles", "MW", "SA", "QED", "LogP", "TPSA",
        "chiral_centers", "synthesis_risk", "sourcing_hint", "pubchem_cid", "pubchem_url",
        "structural_alerts", "structural_warnings", "reactive_groups", "wetlab_ready", "blockers", "notes",
    ]
    order_rows = [order_headers]
    for p in preps:
        order_rows.append([
            p.compound_id, p.rank, p.name or "", p.smiles,
            p.molecular_weight, p.sa_score, p.qed, p.logp, p.tpsa,
            p.chiral_centers, p.synthesis_risk, p.sourcing_hint,
            p.pubchem_cid or "", p.pubchem_url or "",
            "; ".join(p.structural_alerts), "; ".join(p.structural_warnings), "; ".join(p.reactive_groups),
            p.wetlab_ready, "; ".join(p.blockers), "; ".join(p.notes),
        ])

    dmso_headers = ["compound_id", "name", "MW", "target_conc_mM", "volume_mL", "weigh_mg", "solvent", "note"]
    dmso_rows = [dmso_headers]
    for p in preps:
        dmso_rows.append([
            p.compound_id, p.name or "", p.molecular_weight,
            10.0, 1.0, p.dmso_stock_mg_10mm_1ml, "DMSO", p.dmso_note,
        ])

    # GLARE import_wetlab 兼容列 + 常见湿实验字段
    assay_headers = [
        "compound_id", "smiles", "name", "pDC50", "BRET EC50(nM)", "IC50_nM",
        "assay_type", "cell_line", "target", "round_id", "date", "operator", "notes",
    ]
    assay_rows = [assay_headers]
    for p in preps:
        assay_rows.append([
            p.compound_id, p.smiles, p.name or "", "", "", "",
            assay_type, cell_line, target_protein or target_name, round_id, "", "", "",
        ])

    checklist = [
        ["湿实验交接检查清单", ""],
        ["靶点", target_name or target_protein],
        ["轮次", round_id],
        ["候选数", len(preps)],
        ["可送测 (wetlab_ready)", sum(1 for p in preps if p.wetlab_ready)],
        ["需合成 (custom_synthesis)", sum(1 for p in preps if p.sourcing_hint == "custom_synthesis")],
        ["PubChem 现货线索", sum(1 for p in preps if p.sourcing_hint == "pubchem_exact_match")],
        ["高风险合成", sum(1 for p in preps if p.synthesis_risk == "high")],
        ["含手性中心", sum(1 for p in preps if p.chiral_centers > 0)],
        ["", ""],
        ["实验建议", ""],
        ["1", "优先送 wetlab_ready=true 且无 blockers 的分子"],
        ["2", "手性分子需明确对映体纯度与构型"],
        ["3", "测活性后填写 Assay_Results sheet，上传至 GLARE import-wetlab"],
        ["4", "结构警报命中分子建议化学家复核后再合成"],
    ]

    return build_xlsx_bytes([
        ("Synthesis_Order", order_rows),
        ("DMSO_Stock_Prep", dmso_rows),
        ("Assay_Results", assay_rows),
        ("Checklist", checklist),
    ])
