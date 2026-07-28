"""
e-drug lab ADMET prediction service
Based on admet-ai: 22+ ADMET properties + RDKit rule filtering
Pure computation, no FastAPI/DB coupling
"""
import io
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# Fix gbk encoding issues on Windows — admet-ai uses unicode chars
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rdkit import Chem
from rdkit.Chem import Descriptors, FilterCatalog

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading ADMET-AI model...")
        # admet-ai 基于 lightning，本机 GPU driver 过旧会崩；强制 CPU 跑（ADMET 模型小，CPU 可接受）
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        from admet_ai import ADMETModel
        _model = ADMETModel()
        logger.info("ADMET-AI model loaded")
    return _model


ADMET_CATEGORIES = {
    "absorption": [
        "Caco-2_Wang", "HIA_Hou", "Pgp_Substrate_Martin",
        "Pgp_Inhibitor_Martin", "Lipophilicity_AstraZeneca",
        "Solubility_AqSolDB", "CYP2C9_Substrate_CarbonMangels",
        "CYP2D6_Substrate_CarbonMangels", "CYP3A4_Substrate_CarbonMangels",
        "CYP2C9_Inhibitor_Ditvi", "CYP2D6_Inhibitor_Ditvi",
        "CYP3A4_Inhibitor_Ditvi",
    ],
    "distribution": ["BBB_Martins", "PPBR_AZ", "VDss_Lombardo"],
    "metabolism": [
        "Half_Life_Obach", "CYP2C9_Substrate_CarbonMangels",
        "CYP2D6_Substrate_CarbonMangels", "CYP3A4_Substrate_CarbonMangels",
    ],
    "excretion": ["Clearance_Hepatocyte_AZ", "Clearance_Microsome_AZ"],
    "toxicity": [
        "LD50_Zhu", "hERG", "DILI", "Skin_Reaction",
        "Carcinogens_Lagunin", "AMES",
    ],
}

PROPERTY_LABELS = {
    "Caco-2_Wang": "Caco-2 Permeability",
    "HIA_Hou": "Human Intestinal Absorption",
    "Pgp_Substrate_Martin": "P-gp Substrate",
    "Pgp_Inhibitor_Martin": "P-gp Inhibitor",
    "Lipophilicity_AstraZeneca": "Lipophilicity (LogD)",
    "Solubility_AqSolDB": "Aqueous Solubility",
    "CYP2C9_Substrate_CarbonMangels": "CYP2C9 Substrate",
    "CYP2D6_Substrate_CarbonMangels": "CYP2D6 Substrate",
    "CYP3A4_Substrate_CarbonMangels": "CYP3A4 Substrate",
    "CYP2C9_Inhibitor_Ditvi": "CYP2C9 Inhibitor",
    "CYP2D6_Inhibitor_Ditvi": "CYP2D6 Inhibitor",
    "CYP3A4_Inhibitor_Ditvi": "CYP3A4 Inhibitor",
    "BBB_Martins": "Blood-Brain Barrier",
    "PPBR_AZ": "Plasma Protein Binding",
    "VDss_Lombardo": "Volume of Distribution",
    "Half_Life_Obach": "Half-Life",
    "Clearance_Hepatocyte_AZ": "Hepatic Clearance",
    "Clearance_Microsome_AZ": "Microsomal Clearance",
    "LD50_Zhu": "LD50 (Toxicity)",
    "hERG": "hERG Inhibition",
    "DILI": "Drug-Induced Liver Injury",
    "Skin_Reaction": "Skin Sensitization",
    "Carcinogens_Lagunin": "Carcinogenicity",
    "AMES": "Ames Mutagenicity",
}


@dataclass
class AdmetPrediction:
    smiles: str
    name: Optional[str] = None
    properties: dict = field(default_factory=dict)
    category_results: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "smiles": self.smiles, "name": self.name,
            "properties": self.properties, "category_results": self.category_results,
            "warnings": self.warnings,
        }


@dataclass
class FilterResult:
    smiles: str
    name: Optional[str] = None
    passed: bool = True
    rules: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "smiles": self.smiles, "name": self.name,
            "passed": self.passed, "rules": self.rules, "violations": self.violations,
        }


def _extract_properties(raw):
    """Extract properties from admet-ai output (dict or DataFrame)."""
    properties = {}
    category_results = {}

    if raw is None:
        return properties, category_results

    # admet-ai may return a dict or a pandas DataFrame
    if isinstance(raw, dict):
        # Dict mode — keys are property names, values are numbers/strings
        for k, v in raw.items():
            if k == "smiles":
                continue
            try:
                if hasattr(v, "item"):
                    v = v.item()
                properties[str(k)] = v
            except Exception:
                pass
    elif hasattr(raw, "iloc") and hasattr(raw, "columns"):
        # DataFrame mode — single-row or multi-row
        row = raw.iloc[0]
        for col in raw.columns:
            try:
                val = row[col]
                if hasattr(val, "item"):
                    val = val.item()
                properties[str(col)] = val
            except Exception:
                pass

    # Build category results from extracted properties
    for category, keys in ADMET_CATEGORIES.items():
        cat_results = {}
        for key in keys:
            if key in properties:
                cat_results[PROPERTY_LABELS.get(key, key)] = properties[key]
        if cat_results:
            category_results[category] = cat_results

    return properties, category_results


def predict_single(smiles: str, name: Optional[str] = None) -> AdmetPrediction:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return AdmetPrediction(smiles=smiles, name=name, warnings=["Invalid SMILES"])
    model = _get_model()
    try:
        df = model.predict(smiles=smiles)
    except Exception as e:
        logger.error("ADMET prediction failed [%s]: %s", smiles[:50], str(e).encode("ascii", errors="replace").decode("ascii"))
        return AdmetPrediction(smiles=smiles, name=name, warnings=[f"Prediction failed: {str(e).encode('ascii', errors='replace').decode('ascii')}"])
    properties, category_results = _extract_properties(df)
    return AdmetPrediction(smiles=smiles, name=name, properties=properties, category_results=category_results)


def _extract_single_from_batch(raw, index: int):
    """Extract properties for a single molecule from batch prediction output."""
    properties = {}
    category_results = {}

    if raw is None:
        return properties, category_results

    if isinstance(raw, dict):
        # admet-ai returns a flat dict for single SMILES; for batch it may return list of dicts or DataFrame
        # If it's a dict at top level, try to find the index-th entry
        for k, v in raw.items():
            if k == "smiles":
                continue
            try:
                if isinstance(v, (list, tuple)) and index < len(v):
                    val = v[index]
                elif hasattr(v, "iloc") and len(v) > index:
                    val = v.iloc[index]
                else:
                    continue
                if hasattr(val, "item"):
                    val = val.item()
                properties[str(k)] = val
            except Exception:
                pass
    elif hasattr(raw, "iloc") and hasattr(raw, "columns") and len(raw) > index:
        # DataFrame mode
        row = raw.iloc[index]
        for col in raw.columns:
            try:
                val = row[col]
                if hasattr(val, "item"):
                    val = val.item()
                properties[str(col)] = val
            except Exception:
                pass
    elif isinstance(raw, (list, tuple)) and index < len(raw):
        # List of dicts
        item = raw[index]
        if isinstance(item, dict):
            for k, v in item.items():
                if k == "smiles":
                    continue
                try:
                    if hasattr(v, "item"):
                        v = v.item()
                    properties[str(k)] = v
                except Exception:
                    pass

    for category, keys in ADMET_CATEGORIES.items():
        cat_results = {}
        for key in keys:
            if key in properties:
                cat_results[PROPERTY_LABELS.get(key, key)] = properties[key]
        if cat_results:
            category_results[category] = cat_results

    return properties, category_results


def predict_batch(smiles_list: list[str], names: Optional[list[str]] = None, batch_size: int = 32) -> list[AdmetPrediction]:
    if not smiles_list:
        return []
    model = _get_model()
    results = []
    for i in range(0, len(smiles_list), batch_size):
        batch = smiles_list[i:i + batch_size]
        batch_names = names[i:i + batch_size] if names else [None] * len(batch)
        try:
            raw = model.predict(smiles=batch)
        except Exception as e:
            error_msg = str(e).encode("ascii", errors="replace").decode("ascii")
            logger.error("Batch ADMET prediction failed (batch %d): %s", i, error_msg)
            for smi, nm in zip(batch, batch_names):
                results.append(AdmetPrediction(smiles=smi, name=nm, warnings=[f"Batch failed: {error_msg}"]))
            continue
        for j, (smi, nm) in enumerate(zip(batch, batch_names)):
            properties, category_results = _extract_single_from_batch(raw, j)
            results.append(AdmetPrediction(smiles=smi, name=nm, properties=properties, category_results=category_results))
    return results


_pains_catalog = None


def _get_pains_catalog():
    global _pains_catalog
    if _pains_catalog is None:
        params = FilterCatalog.FilterCatalogParams()
        params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
        _pains_catalog = FilterCatalog.FilterCatalog(params)
    return _pains_catalog


def _check_lipinski(mol):
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = Descriptors.NumHDonors(mol)
    hba = Descriptors.NumHAcceptors(mol)
    violations = []
    if mw > 500:
        violations.append(f"MW={mw:.1f} > 500")
    if logp > 5:
        violations.append(f"LogP={logp:.2f} > 5")
    if hbd > 5:
        violations.append(f"HBD={hbd} > 5")
    if hba > 10:
        violations.append(f"HBA={hba} > 10")
    return {
        "name": "Lipinski RO5",
        "passed": len(violations) == 0,
        "values": {"MW": round(mw, 2), "LogP": round(logp, 2), "HBD": hbd, "HBA": hba},
        "violations": violations,
    }


def _check_veber(mol):
    rotb = Descriptors.NumRotatableBonds(mol)
    tpsa = Descriptors.TPSA(mol)
    violations = []
    if rotb > 10:
        violations.append(f"RotBonds={rotb} > 10")
    if tpsa > 140:
        violations.append(f"TPSA={tpsa:.1f} > 140")
    return {
        "name": "Veber",
        "passed": len(violations) == 0,
        "values": {"RotatableBonds": rotb, "TPSA": round(tpsa, 2)},
        "violations": violations,
    }


def _check_pains(mol):
    catalog = _get_pains_catalog()
    match = catalog.GetFirstMatch(mol)
    if match:
        return {
            "name": "PAINS",
            "passed": False,
            "values": {"matched_pattern": match.GetDescription()},
            "violations": [f"PAINS hit: {match.GetDescription()}"],
        }
    return {"name": "PAINS", "passed": True, "values": {}, "violations": []}


RULE_CHECKERS = {
    "lipinski": _check_lipinski,
    "veber": _check_veber,
    "pains": _check_pains,
}


def apply_druglikeness_filter(
    smiles_list: list[str],
    rules: Optional[list[str]] = None,
    names: Optional[list[str]] = None,
) -> list[FilterResult]:
    if rules is None:
        rules = ["lipinski", "veber", "pains"]
    results = []
    for i, smiles in enumerate(smiles_list):
        nm = names[i] if names and i < len(names) else None
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            results.append(FilterResult(smiles=smiles, name=nm, passed=False, violations=["Invalid SMILES"]))
            continue
        rule_results = {}
        all_violations = []
        passed_all = True
        for rule_name in rules:
            checker = RULE_CHECKERS.get(rule_name)
            if checker is None:
                rule_results[rule_name] = {"name": rule_name, "passed": True, "values": {}, "violations": [f"Unknown rule: {rule_name}"]}
                continue
            result = checker(mol)
            rule_results[rule_name] = result
            if not result["passed"]:
                passed_all = False
                all_violations.extend(result["violations"])
        results.append(FilterResult(smiles=smiles, name=nm, passed=passed_all, rules=rule_results, violations=all_violations))
    return results


def check_health() -> dict:
    try:
        model = _get_model()
        test = model.predict(smiles="CC")
        return {"status": "healthy", "model_loaded": True, "test_prediction_ok": test is not None and len(test) > 0}
    except Exception as e:
        return {"status": "unhealthy", "model_loaded": False, "error": str(e)}
