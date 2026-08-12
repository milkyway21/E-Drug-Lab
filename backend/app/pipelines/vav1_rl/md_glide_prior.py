"""Target-aware MD/Glide confidence prior.

Residue names are data, not model code.  The legacy VAV1 constants remain
available only for old checkpoints; new profiles pass their own IFP columns
and optional MD weights.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path("/data/ye/e-drug-lab/backend")
LEGACY_CONSENSUS_CSV = (
    PROJECT_ROOT / "outputs/vav1_rl_project/binding_RL/patent_screening/results/"
    "md_vav1_consensus_weights.csv"
)

# Legacy VAV1 feature contract.  New target profiles must not use these values.
UNION_RESIDUES = [
    791, 792, 793, 794, 795, 796, 797, 798, 799, 800, 801, 804, 805,
    813, 814, 815, 816, 817, 818, 819, 820, 821, 822, 831, 832, 833, 835,
    836,
]
MD_KEY_RESIDUES = [796, 797, 798, 799, 800, 815, 816, 817, 818, 820, 831]
GLIDE_IFP_COLS = [
    "ifp_C.ARG.796", "ifp_C.ASN.835", "ifp_C.ASP.797",
    "ifp_C.GLN.817", "ifp_C.GLN.818", "ifp_C.GLU.800",
    "ifp_C.PHE.793", "ifp_C.PRO.833", "ifp_C.SER.799",
    "ifp_C.TRP.820", "ifp_C.TYR.836",
]
_AA = {
    791: "TYR", 792: "ASP", 793: "PHE", 794: "CYS", 795: "ALA",
    796: "ARG", 797: "ASP", 798: "ARG", 799: "SER", 800: "GLU",
    801: "LEU", 804: "LYS", 805: "GLU", 813: "ASN", 814: "LYS",
    815: "LYS", 816: "GLY", 817: "GLN", 818: "GLN", 819: "GLY",
    820: "TRP", 821: "TRP", 822: "ARG", 831: "TRP", 832: "PHE",
    833: "PRO", 835: "ASN", 836: "TYR",
}
UNION_IFP_COLS = [f"ifp_C.{_AA[r]}.{r}" for r in UNION_RESIDUES]


def _residue_number(value: str) -> Optional[int]:
    match = re.search(r"(?:^|[.:])([0-9]+)[^0-9]*$", str(value))
    return int(match.group(1)) if match else None


def _normalise_weight_key(value: Any) -> str:
    text = str(value).strip()
    if text.lower().startswith("ifp_"):
        text = text[4:]
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return text


def load_consensus_weights(
    path: Path | str | None = LEGACY_CONSENSUS_CSV,
    residues: Optional[Iterable[int | str]] = None,
) -> dict[int | str, float]:
    """Load and normalize MD weights; missing/absent MD means no prior."""
    requested = list(residues or UNION_RESIDUES)
    if path is None or not Path(path).is_file():
        return {residue: 0.0 for residue in requested}
    frame = pd.read_csv(path)
    if frame.shape[1] < 2:
        raise ValueError(f"MD weights must have at least two columns: {path}")
    residue_col = next(
        (
            column
            for column in ("ifp_column", "ifp", "residue", "residue_label", "canonical_res_num")
            if column in frame
        ),
        frame.columns[0],
    )
    weight_col = "weight" if "weight" in frame else frame.columns[1]
    raw: dict[str, float] = {}
    for _, row in frame.iterrows():
        try:
            key = _normalise_weight_key(row[residue_col])
            value = float(row[weight_col])
            if np.isfinite(value):
                raw[key] = value
        except (TypeError, ValueError):
            continue
    result = {}
    for residue in requested:
        key = _normalise_weight_key(residue)
        value = raw.get(key)
        residue_number = _residue_number(str(residue))
        if value is None and residue_number is not None:
            value = raw.get(str(residue_number), 0.0)
        result[residue] = max(value or 0.0, 0.0)
    total = sum(result.values())
    if total > 0:
        return {residue: value / total for residue, value in result.items()}
    return {residue: 0.0 for residue in requested}


def extract_ifp(row: Mapping[str, Any], ifp_columns: Iterable[str]) -> np.ndarray:
    values: list[float] = []
    for column in ifp_columns:
        try:
            value = float(row.get(column, 0.0))
        except (TypeError, ValueError):
            value = 0.0
        values.append(0.0 if not np.isfinite(value) else value)
    return np.asarray(values, dtype=np.float64)


def extract_ifp_15(row: Mapping[str, Any]) -> np.ndarray:
    """Legacy VAV1 name retained for old callers."""
    return extract_ifp(row, UNION_IFP_COLS)


def compute_consistency(
    contacts: np.ndarray,
    weights: Mapping[int, float],
    residues: Iterable[int] = UNION_RESIDUES,
) -> float:
    residues = list(residues)
    if contacts.shape[-1] != len(residues):
        raise ValueError(
            f"contact dimension {contacts.shape[-1]} != residue dimension {len(residues)}"
        )
    vector = np.asarray([weights.get(residue, 0.0) for residue in residues])
    return float(np.dot(vector, contacts))


class MDGlidePrior:
    """Frozen target-specific confidence prior, or an explicit no-op prior."""

    def __init__(
        self,
        weights: Mapping[int, float] | None = None,
        ifp_columns: Iterable[str] = UNION_IFP_COLS,
    ) -> None:
        self.ifp_columns = tuple(ifp_columns)
        self.residues = tuple(
            _residue_number(column) for column in self.ifp_columns
        )
        if any(residue is None for residue in self.residues):
            self.residues = tuple(range(len(self.ifp_columns)))
        self.weights = dict(weights or {})
        self.w_vector = np.asarray(
            [
                self.weights.get(column, self.weights.get(residue, 0.0))
                for column, residue in zip(self.ifp_columns, self.residues)
            ],
            dtype=np.float64,
        )
        self.available = bool(np.any(self.w_vector > 0))

    @classmethod
    def from_csv(
        cls,
        path: Path | str | None = LEGACY_CONSENSUS_CSV,
        ifp_columns: Iterable[str] = UNION_IFP_COLS,
    ) -> "MDGlidePrior":
        columns = tuple(ifp_columns)
        residues = [
            residue for residue in (_residue_number(column) for column in columns)
            if residue is not None
        ]
        return cls(load_consensus_weights(path, residues), columns)

    @classmethod
    def from_profile(cls, profile: Any) -> Optional["MDGlidePrior"]:
        columns = tuple(getattr(profile, "ifp_columns", ()) or ())
        weights_path = getattr(profile, "md_weights", None)
        if not columns or weights_path is None or not Path(weights_path).is_file():
            return None
        return cls(load_consensus_weights(weights_path, columns), columns)

    def compute_q(self, contacts: np.ndarray) -> float:
        contacts = np.asarray(contacts, dtype=np.float64)
        if contacts.ndim != 1 or contacts.shape[0] != self.w_vector.shape[0]:
            raise ValueError(
                f"prior input shape {contacts.shape} does not match "
                f"{self.w_vector.shape[0]} IFP columns"
            )
        return float(np.dot(self.w_vector, contacts)) if self.available else 0.0

    def compute_q_batch(self, contacts: np.ndarray) -> np.ndarray | float:
        contacts = np.asarray(contacts, dtype=np.float64)
        if contacts.ndim == 1:
            return self.compute_q(contacts)
        if contacts.shape[-1] != self.w_vector.shape[0]:
            raise ValueError("batch prior input does not match IFP dimension")
        return contacts @ self.w_vector if self.available else np.zeros(contacts.shape[0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "ifp_columns": list(self.ifp_columns),
            "weights": {str(key): float(value) for key, value in self.weights.items()},
        }
