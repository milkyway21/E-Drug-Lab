"""Glide feature stores with legacy and target-independent contracts.

The legacy VAV1 16-column contract is kept for old checkpoints.  A target
profile uses the same width but replaces residue identity with deterministic
interaction summaries inferred from the target's Glide SP table.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from .md_glide_prior import MDGlidePrior, UNION_IFP_COLS, extract_ifp
from .target_profile import TargetProfile, load_or_infer_profile


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BINDING_RL = Path("/data/ye/e-drug-lab/backend/outputs/vav1_rl_project/binding_RL")
FEATURE_TABLE = BINDING_RL / "patent_screening" / "results" / "feature_table.csv"
PATENT_GLIDE = BINDING_RL / "patent_docking" / "analysis" / "glide_sp_docking_results.csv"
WETLAB_GLIDE = BINDING_RL / "wetlab_docking" / "analysis" / "glide_sp_docking_results.csv"
ALLIN_GLIDE_TABLE = BINDING_RL / "features_v1" / "glide" / "allin_glide_feature_table.csv"

# Legacy VAV1 contract.  Do not use these columns for a new target profile.
GLIDE_SCORE_COLS = [
    "docking_score", "glide_emodel", "glide_evdw", "glide_ecoul",
    "n_vav1_residues",
]
IFP_COLS = [
    "ifp_C.ARG.796", "ifp_C.ASN.835", "ifp_C.ASP.797",
    "ifp_C.GLN.817", "ifp_C.GLN.818", "ifp_C.GLU.800",
    "ifp_C.PHE.793", "ifp_C.PRO.833", "ifp_C.SER.799",
    "ifp_C.TRP.820", "ifp_C.TYR.836",
]
GLIDE_DIM = len(GLIDE_SCORE_COLS) + len(IFP_COLS)

# Target-independent contract: five scores plus eleven interaction summaries.
UNIFIED_SCORE_COLS = [
    "docking_score", "glide_emodel", "glide_evdw", "glide_ecoul",
    "contact_residue_count",
]
UNIFIED_SUMMARY_COLS = [
    "contact_residue_fraction",
    "interaction_hbond",
    "interaction_salt",
    "interaction_pipi",
    "interaction_pication",
    "interaction_hphob",
    "interaction_vdw",
    "interaction_total",
    "interaction_per_residue",
    "interaction_nonzero_types",
    "contact_observed",
]
UNIFIED_FEATURE_COLS = UNIFIED_SCORE_COLS + UNIFIED_SUMMARY_COLS
UNIFIED_GLIDE_DIM = len(UNIFIED_FEATURE_COLS)
COUNT_TYPES = (
    "hbond", "salt", "pipi", "pication", "hphob", "vdw"
)


def _normalize_id(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer() and abs(number) < 10_000_000:
            return f"{int(number):07d}"
    except (TypeError, ValueError):
        pass
    return text


def _parse_residue_counts(value: Any) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return result
    for item in str(value).split(";"):
        label, separator, raw_counts = item.strip().partition(":")
        if not separator:
            continue
        parts = raw_counts.split("/")
        if len(parts) != len(COUNT_TYPES):
            continue
        try:
            numbers = [max(float(part), 0.0) for part in parts]
        except ValueError:
            continue
        result[label] = dict(zip(COUNT_TYPES, numbers))
    return result


def _numeric(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _target_feature_row(row: Mapping[str, Any], profile: TargetProfile) -> dict[str, float]:
    """Convert one raw target table row to the fixed-width feature contract."""
    raw_scores = profile.score_columns
    docking = _numeric(row.get(raw_scores.get("docking_score", "docking_score")), math.nan)
    ifp_values = extract_ifp(row, profile.ifp_columns)
    contact_column = profile.contact_count_column
    if contact_column:
        contact_count = _numeric(row.get(contact_column), float(np.count_nonzero(ifp_values > 0)))
    else:
        contact_count = float(np.count_nonzero(ifp_values > 0))
    contact_count = max(contact_count, 0.0)
    max_contacts = max(len(profile.ifp_columns), 1)
    counts = _parse_residue_counts(row.get(profile.interaction_count_column or ""))
    interaction = {
        kind: sum(values.get(kind, 0.0) for values in counts.values())
        for kind in COUNT_TYPES
    }
    interaction_total = sum(interaction.values())
    summary = {
        "contact_residue_count": contact_count,
        "contact_residue_fraction": min(contact_count / max_contacts, 1.0),
        **{f"interaction_{kind}": value for kind, value in interaction.items()},
        "interaction_total": interaction_total,
        "interaction_per_residue": interaction_total / max(contact_count, 1.0),
        "interaction_nonzero_types": float(sum(value > 0 for value in interaction.values())),
        "contact_observed": float(np.isfinite(docking)),
    }
    return {
        "docking_score": docking,
        "glide_emodel": _numeric(row.get(raw_scores.get("glide_emodel", "glide_emodel")), math.nan),
        "glide_evdw": _numeric(row.get(raw_scores.get("glide_evdw", "glide_evdw")), math.nan),
        "glide_ecoul": _numeric(row.get(raw_scores.get("glide_ecoul", "glide_ecoul")), math.nan),
        **summary,
    }


class GlideFeatureStore:
    def __init__(
        self,
        table: pd.DataFrame,
        mean: np.ndarray,
        std: np.ndarray,
        *,
        profile: Optional[TargetProfile] = None,
        feature_columns: Optional[list[str]] = None,
    ) -> None:
        self.table = table
        self.mean = np.asarray(mean, dtype=np.float64)
        self.std = np.nan_to_num(
            np.where(np.asarray(std, dtype=np.float64) < 1e-8, 1.0, std),
            nan=1.0,
        )
        self.profile = profile
        self.unified = profile is not None
        self.feature_columns = feature_columns or (
            list(UNIFIED_FEATURE_COLS) if self.unified else list(GLIDE_SCORE_COLS + IFP_COLS)
        )
        self.feature_dim = len(self.feature_columns)
        self.by_id = {str(row["molecule_id"]): row for _, row in table.iterrows()}
        if profile is not None:
            self._md_prior = MDGlidePrior.from_profile(profile)
        else:
            self._md_prior = MDGlidePrior.from_csv()

    @classmethod
    def build(
        cls,
        train_ids: Optional[set[str]] = None,
        *,
        feature_table: Path | str | None = None,
        profile: Optional[TargetProfile] = None,
        fit_all: bool = False,
    ) -> "GlideFeatureStore":
        if profile is not None:
            if profile.glide_table is None:
                raise ValueError("target profile requires glide_table")
            source = Path(profile.glide_table)
            if not source.is_file():
                raise FileNotFoundError(f"Glide table not found: {source}")
            raw = pd.read_csv(source)
            if raw.empty:
                raise ValueError(f"Glide table has no rows: {source}")
            if "molecule_id" not in raw.columns:
                id_col = "mol_id" if "mol_id" in raw.columns else None
                if id_col is None:
                    raise ValueError("Glide table requires molecule_id or mol_id")
                raw = raw.rename(columns={id_col: "molecule_id"})
            rows = []
            for _, source_row in raw.iterrows():
                values = _target_feature_row(source_row, profile)
                values["molecule_id"] = _normalize_id(source_row["molecule_id"])
                if "split" in raw.columns:
                    values["split"] = source_row.get("split")
                # Keep raw IFP columns beside the fixed-width model features
                # so an optional target-specific MD prior can compute q.
                for column in profile.ifp_columns:
                    values[column] = source_row.get(column, 0.0)
                rows.append(values)
            table = pd.DataFrame(rows)
            if table.empty:
                raise ValueError(f"Glide table produced no usable rows: {source}")
            columns = list(UNIFIED_FEATURE_COLS)
            if train_ids is not None:
                normalized = {_normalize_id(value) for value in train_ids}
                selected = table[table["molecule_id"].isin(normalized)]
                if selected.empty:
                    raise ValueError(
                        "target profile Glide scaler has no rows for train_ids"
                    )
                fit = selected
            elif "split" in table.columns:
                fit = table[
                    table["split"].astype(str).str.lower().eq("train")
                ]
                if fit.empty:
                    if not fit_all:
                        raise ValueError(
                            "target profile Glide scaler requires split=train rows"
                        )
                    fit = table
            elif fit_all:
                fit = table
            else:
                raise ValueError(
                    "target profile Glide scaler requires train_ids or split=train"
                )
            matrix = fit[columns].to_numpy(dtype=float)
            mean = np.nan_to_num(np.nanmean(matrix, axis=0), nan=0.0)
            std = np.nan_to_num(np.nanstd(matrix, axis=0), nan=1.0)
            return cls(table, mean, std, profile=profile, feature_columns=columns)

        path = Path(feature_table or FEATURE_TABLE)
        ft = pd.read_csv(path)
        for column in IFP_COLS + GLIDE_SCORE_COLS:
            if column not in ft.columns:
                ft[column] = np.nan
        # Legacy VAV1 queries also consume the existing ALLIN library table.
        # Keep the wider IFP union for q_i while retaining the 16D model input.
        for column in UNION_IFP_COLS:
            if column not in ft.columns:
                ft[column] = 0.0
        ft["molecule_id"] = ft["molecule_id"].map(_normalize_id)
        if ALLIN_GLIDE_TABLE.is_file():
            extension = pd.read_csv(ALLIN_GLIDE_TABLE)
            extension["molecule_id"] = extension["molecule_id"].map(_normalize_id)
            all_columns = list(dict.fromkeys([*ft.columns, *extension.columns]))
            ft = ft.reindex(columns=all_columns)
            extension = extension.reindex(columns=all_columns)
            ft = pd.concat([ft, extension], ignore_index=True)
            ft = ft.drop_duplicates(subset=["molecule_id"], keep="last")
        if WETLAB_GLIDE.is_file():
            wetlab = pd.read_csv(WETLAB_GLIDE)
            id_col = "mol_id" if "mol_id" in wetlab.columns else "molecule_id"
            existing = set(ft["molecule_id"])
            extra_rows = []
            for _, row in wetlab.iterrows():
                mid = _normalize_id(row[id_col])
                if mid in existing:
                    continue
                extra = {column: np.nan for column in ft.columns}
                extra["molecule_id"] = mid
                for column in GLIDE_SCORE_COLS:
                    if column in wetlab.columns:
                        extra[column] = row[column]
                extra_rows.append(extra)
            if extra_rows:
                ft = pd.concat([ft, pd.DataFrame(extra_rows)], ignore_index=True)
        fit = ft
        if train_ids is not None:
            selected = ft[ft["molecule_id"].isin({_normalize_id(v) for v in train_ids})]
            if selected.empty:
                raise ValueError("Glide scaler has no rows for train_ids")
            fit = selected
        columns = GLIDE_SCORE_COLS + IFP_COLS
        matrix = fit[columns].to_numpy(dtype=float)
        mean = np.nan_to_num(np.nanmean(matrix, axis=0))
        std = np.nan_to_num(np.nanstd(matrix, axis=0), nan=1.0)
        return cls(ft, mean, std, feature_columns=columns)

    def get(self, molecule_id: str) -> dict[str, Any]:
        mid = _normalize_id(molecule_id)
        row = self.by_id.get(mid)
        if row is None:
            return {
                "molecule_id": mid,
                "glide_vec": [0.0] * self.feature_dim,
                "glide_mask": 0,
                "observed": False,
                "q": 0.0,
            }
        raw = np.asarray([_numeric(row.get(column), math.nan) for column in self.feature_columns])
        observed = bool(np.isfinite(raw[0]))
        z = (raw - self.mean) / self.std
        z = np.clip(np.nan_to_num(z, nan=0.0), -10, 10)
        q = 0.0
        if self.profile is not None and self._md_prior is not None:
            contacts = extract_ifp(row, self.profile.ifp_columns)
            q = self._md_prior.compute_q(contacts)
        elif self.profile is None:
            contacts = extract_ifp(row, IFP_COLS)
            # Legacy prior uses the 28-column union; construct the missing
            # columns as zeros so old checkpoint behavior remains defined.
            legacy_row = {column: row.get(column, 0.0) for column in self._md_prior.ifp_columns}
            q = self._md_prior.compute_q(extract_ifp(legacy_row, self._md_prior.ifp_columns))
        return {
            "molecule_id": mid,
            "glide_vec": z.astype(float).tolist(),
            "glide_mask": int(observed),
            "observed": observed,
            "q": float(q),
        }

    def schema(self) -> dict[str, Any]:
        return {
            "version": "glide_target_v2" if self.unified else "glide_v1",
            "target_id": self.profile.target_id if self.profile else "VAV1",
            "feature_columns": list(self.feature_columns),
            "score_columns": list(UNIFIED_SCORE_COLS if self.unified else GLIDE_SCORE_COLS),
            "ifp_columns": list(self.profile.ifp_columns if self.profile else IFP_COLS),
            "mean": self.mean.tolist(),
            "std": self.std.tolist(),
            "dim": self.feature_dim,
            "md_prior": self._md_prior.to_dict() if self._md_prior else None,
        }

    def save_cache(self, path: Path | str) -> None:
        cache_path = Path(path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(self.schema(), indent=2), encoding="utf-8")
        rows = []
        for molecule_id in self.by_id:
            values = self.get(molecule_id)
            rows.append({
                "molecule_id": molecule_id,
                "glide_mask": values["glide_mask"],
                **{f"g{i}": value for i, value in enumerate(values["glide_vec"])},
            })
        pd.DataFrame(rows).to_csv(cache_path.with_suffix(".csv"), index=False)


def build_default_glide_store(
    profile: Path | str | Mapping[str, Any] | TargetProfile | None = None,
    *,
    target_id: str | None = None,
    glide_table: Path | str | None = None,
    train_ids: Optional[set[str]] = None,
    fit_all: bool = False,
) -> GlideFeatureStore:
    if isinstance(profile, TargetProfile):
        resolved = profile
    else:
        resolved = load_or_infer_profile(profile, target_id=target_id, glide_table=glide_table)
    if resolved is not None:
        return GlideFeatureStore.build(
            profile=resolved,
            train_ids=train_ids,
            fit_all=fit_all,
        )
    legacy_train_ids = train_ids
    if FEATURE_TABLE.is_file():
        frame = pd.read_csv(FEATURE_TABLE)
        if legacy_train_ids is None and "split" in frame.columns:
            legacy_train_ids = set(
                frame.loc[frame["split"] == "train", "molecule_id"].map(_normalize_id)
            )
    return GlideFeatureStore.build(train_ids=legacy_train_ids, fit_all=fit_all)
