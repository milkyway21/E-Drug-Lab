"""RDKit physicochemical evaluation + PAINS."""
from __future__ import annotations

from typing import Any, Optional


def evaluate_smiles(smiles: str) -> dict[str, Any]:
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, Lipinski, QED
        from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    except ImportError as exc:
        return {
            "status": "skipped_missing_dependency",
            "error": f"rdkit_unavailable:{exc}",
            "smiles": smiles,
        }

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"status": "failed", "error": "invalid_smiles", "smiles": smiles}

    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    catalog = FilterCatalog(params)
    pains_hits = [entry.GetDescription() for entry in catalog.GetMatches(mol)]

    return {
        "status": "ok",
        "smiles": smiles,
        "MW": float(Descriptors.MolWt(mol)),
        "cLogP": float(Descriptors.MolLogP(mol)),
        "TPSA": float(Descriptors.TPSA(mol)),
        "HBD": int(Lipinski.NumHDonors(mol)),
        "HBA": int(Lipinski.NumHAcceptors(mol)),
        "RotatableBonds": int(Lipinski.NumRotatableBonds(mol)),
        "QED": float(QED.qed(mol)),
        "PAINS": pains_hits,
        "PAINS_flag": bool(pains_hits),
    }


def evaluate_ligand_record(smiles: Optional[str]) -> dict[str, Any]:
    if not smiles:
        return {"status": "skipped", "error": "no_smiles"}
    return evaluate_smiles(smiles)
