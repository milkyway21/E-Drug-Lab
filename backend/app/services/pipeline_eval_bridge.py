"""Bridge e-drug pipeline molecules to GLARE evaluated.xlsx format."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Core columns always present; target-specific columns supplied via column_mapping
GLARE_CORE_COLS = [
    "mol_id", "smiles", "canonical_smiles", "name",
    "qed", "sa", "mw", "clogp", "tpsa", "hbd", "hba", "rotatable_bonds",
    "vina_score", "oracle_score_prelim",
    "diversity_cluster", "achiral_pass", "chiral_center_count",
    "label", "label_weight", "wetlab_label",
]

DEFAULT_TARGET_COLUMNS = [
    "vav1_binding_score", "crbn_binding_score",
    "ternary_complex_score", "molecular_glue_likeness_score",
    "similarity_to_lxc401", "similarity_to_mrt6160",
]

DEFAULT_COLUMN_MAPPING: dict[str, str] = {
    "vina_score": "vina-dock.affinity_kcal_mol",
    "oracle_score_prelim": "orthogonal-rank.final_score",
}


def _canonical_smiles(smiles: str) -> str:
    if not smiles:
        return ""
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return smiles
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return smiles


def _get_nested(d: dict, *keys, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _resolve_mapped_value(mol: dict, step: dict, mapping_key: str, column_mapping: dict[str, str]) -> Any:
    """Resolve a column value from explicit mol fields or step_results via mapping."""
    if mapping_key in mol and mol[mapping_key] is not None:
        return mol[mapping_key]

    path = column_mapping.get(mapping_key)
    if not path:
        return None

    if "." in path:
        tool_key, field = path.split(".", 1)
        tool_result = step.get(tool_key) or step.get(tool_key.replace("-", "_")) or {}
        return _get_nested(tool_result, field) if isinstance(tool_result, dict) else None

    return step.get(path) or mol.get(path)


def build_evaluated_dataframe(
    molecules: list[dict[str, Any]],
    round_id: int = 1,
    *,
    column_mapping: Optional[dict[str, str]] = None,
    extra_columns: Optional[list[str]] = None,
) -> pd.DataFrame:
    mapping = {**DEFAULT_COLUMN_MAPPING, **(column_mapping or {})}
    feature_cols = list(GLARE_CORE_COLS)
    for col in extra_columns or DEFAULT_TARGET_COLUMNS:
        if col not in feature_cols:
            feature_cols.append(col)

    rows = []
    for idx, mol in enumerate(molecules):
        props = mol.get("properties") or {}
        step = mol.get("stepResults") or mol.get("step_results") or {}
        vina = step.get("vina-dock") or step.get("vina_dock") or {}
        admet = step.get("admet-ai") or step.get("admet_ai") or {}
        admet_props = admet.get("properties") if isinstance(admet.get("properties"), dict) else {}
        rank = step.get("orthogonal-rank") or step.get("orthogonal_rank") or {}

        mol_id = mol.get("id") or mol.get("mol_id") or f"PIPE_R{round_id}_M{idx:04d}"
        vina_score = (
            _get_nested(vina, "affinity_kcal_mol")
            or mol.get("docking_score")
            or mol.get("vina_score")
        )

        smiles = mol.get("smiles", "")
        row = {
            "mol_id": mol_id,
            "smiles": smiles,
            "canonical_smiles": mol.get("canonical_smiles") or _canonical_smiles(smiles),
            "name": mol.get("name") or mol.get("standardName") or mol.get("originalName") or mol_id,
            "qed": props.get("qed") or admet_props.get("QED") or admet_props.get("qed"),
            "sa": props.get("sa_score") or props.get("sa") or admet_props.get("SA"),
            "mw": props.get("molecular_weight") or props.get("mw"),
            "clogp": props.get("logp") or admet_props.get("LogP"),
            "tpsa": props.get("tpsa") or admet_props.get("TPSA"),
            "hbd": props.get("num_h_bond_donors") or admet_props.get("HBD"),
            "hba": props.get("num_h_bond_acceptors") or admet_props.get("HBA"),
            "rotatable_bonds": props.get("num_rotatable_bonds") or admet_props.get("RotBonds"),
            "vina_score": vina_score,
            "oracle_score_prelim": (
                _resolve_mapped_value(mol, step, "oracle_score_prelim", mapping)
                or rank.get("final_score")
                or mol.get("final_score")
            ),
            "diversity_cluster": mol.get("diversity_cluster", 0),
            "achiral_pass": mol.get("achiral_pass", True),
            "chiral_center_count": mol.get("chiral_center_count", 0),
            "label": mol.get("label", 0),
            "label_weight": mol.get("label_weight", 1.0),
            "wetlab_label": mol.get("wetlab_label"),
        }

        for col in extra_columns or DEFAULT_TARGET_COLUMNS:
            row[col] = _resolve_mapped_value(mol, step, col, mapping)

        rows.append(row)

    df = pd.DataFrame(rows)
    for col in feature_cols:
        if col not in df.columns:
            df[col] = None
    return df


def write_evaluated_xlsx(
    molecules: list[dict[str, Any]],
    output_path: str | Path,
    round_id: int = 1,
    *,
    column_mapping: Optional[dict[str, str]] = None,
    extra_columns: Optional[list[str]] = None,
) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = build_evaluated_dataframe(
        molecules,
        round_id=round_id,
        column_mapping=column_mapping,
        extra_columns=extra_columns,
    )
    df.to_excel(path, index=False)
    return str(path.resolve())


def resolve_evaluated_path(
    round_id: int,
    evaluated_file: Optional[str],
    molecules: Optional[list[dict[str, Any]]] = None,
    *,
    column_mapping: Optional[dict[str, str]] = None,
    extra_columns: Optional[list[str]] = None,
) -> str:
    """统一的 evaluated.xlsx 路径解析。"""
    from app.core.errors import AppError
    from app.services.rl_round_service import round_dir

    if evaluated_file and Path(evaluated_file).is_file():
        return evaluated_file
    if molecules:
        out = round_dir(round_id) / f"round_{round_id}_evaluated.xlsx"
        return write_evaluated_xlsx(
            molecules,
            out,
            round_id=round_id,
            column_mapping=column_mapping,
            extra_columns=extra_columns,
        )
    default = round_dir(round_id) / f"round_{round_id}_evaluated.xlsx"
    if default.is_file():
        return str(default)
    raise AppError(
        message="evaluated_file or pipeline_molecules required",
        code="GLARE_NO_INPUT",
        status_code=400,
    )
