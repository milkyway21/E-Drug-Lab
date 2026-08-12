"""Target-independent MD confidence features.

This builder intentionally aggregates over the target's observed residues. It
does not encode VAV1 numbering, chain names, or a fixed residue list, so the
result has the same dimension for every target.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd


MD_FEATURE_NAMES = [
    "occupancy_mean", "occupancy_std", "occupancy_max", "occupancy_observed_fraction",
    "interaction_hbdonor", "interaction_hbaacceptor", "interaction_hydrophobic",
    "interaction_pistacking", "interaction_pication", "interaction_vdwcontact",
    "energy_mean", "energy_std", "energy_observed_fraction",
    "rmsf_mean", "rmsf_std", "window_complete_rate",
]
INTERACTION_NAMES = {
    "HBD": "interaction_hbdonor",
    "HBDonor": "interaction_hbdonor",
    "HBA": "interaction_hbaacceptor",
    "HBAcceptor": "interaction_hbaacceptor",
    "Hydrophobic": "interaction_hydrophobic",
    "PiStacking": "interaction_pistacking",
    "PiCation": "interaction_pication",
    "VdWContact": "interaction_vdwcontact",
}


def _read_optional(root: Path, name: str) -> pd.DataFrame:
    candidates = [root / "COMBINED" / name, root / name]
    for candidate in candidates:
        if candidate.is_file():
            try:
                return pd.read_parquet(candidate)
            except (ImportError, ModuleNotFoundError) as exc:
                csv_path = candidate.with_suffix(".csv")
                if csv_path.is_file():
                    return pd.read_csv(csv_path)
                raise RuntimeError(
                    f"reading MD parquet requires pyarrow or fastparquet: {candidate}"
                ) from exc
        csv_path = candidate.with_suffix(".csv")
        if csv_path.is_file():
            return pd.read_csv(csv_path)
    return pd.DataFrame()


def _target_rows(frame: pd.DataFrame, target_component: Optional[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    if "protein_component" not in frame.columns:
        raise ValueError(
            "MD input must contain protein_component so target isolation can be verified"
        )
    if not target_component:
        raise ValueError(
            "target_component is required for MD feature construction"
        )
    values = frame["protein_component"].astype(str)
    mask = values.str.casefold() == str(target_component).casefold()
    if mask.any():
        return frame.loc[mask].copy()
    unique = values.dropna().unique().tolist()
    raise ValueError(
        f"target component '{target_component}' not found; available={unique[:20]}"
    )


def _safe_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        return np.asarray([], dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna().to_numpy(dtype=float)


def _observed_fraction(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns or frame.empty:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    return float(np.isfinite(values).mean())


def _molecule_rows(frame: pd.DataFrame, molecule_id: str) -> pd.DataFrame:
    """Select a molecule without assuming every optional MD table has IDs."""
    if frame.empty or "molecule_id" not in frame.columns:
        return frame.iloc[0:0].copy()
    values = frame["molecule_id"].astype(str)
    return frame.loc[values == molecule_id].copy()


def build_target_md_features(
    combined_dir: Path | str,
    out_dir: Path | str,
    *,
    target_component: Optional[str] = None,
) -> dict[str, Any]:
    root = Path(combined_dir).expanduser().resolve()
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    occupancy = _target_rows(
        _read_optional(root, "all8_residue_occupancy_canonical.parquet"),
        target_component,
    )
    interactions = _target_rows(
        _read_optional(root, "all8_interaction_occupancy_canonical.parquet"),
        target_component,
    )
    dynamic = _target_rows(
        _read_optional(root, "all8_dynamic_window_residue.parquet"),
        target_component,
    )
    rmsf = _target_rows(_read_optional(root, "all8_rmsf_residue.parquet"), target_component)
    frames = [frame for frame in (occupancy, interactions, dynamic, rmsf) if not frame.empty]
    if not frames:
        raise FileNotFoundError(f"no supported MD parquet files under {root}")
    molecule_ids = sorted({
        str(value)
        for frame in frames
        if "molecule_id" in frame.columns
        for value in frame["molecule_id"].dropna().unique()
    })
    rows: list[dict[str, Any]] = []
    for molecule_id in molecule_ids:
        occ = _molecule_rows(occupancy, molecule_id)
        ix = _molecule_rows(interactions, molecule_id)
        dyn = _molecule_rows(dynamic, molecule_id)
        rms = _molecule_rows(rmsf, molecule_id)
        occ_values = _safe_values(occ, "any_interaction_occupancy")
        energy_values = _safe_values(dyn, "mmgbsa_total_mean")
        rmsf_values = _safe_values(rms, "rmsf_A")
        row = {
            "molecule_id": molecule_id,
            "occupancy_mean": float(np.mean(occ_values)) if len(occ_values) else 0.0,
            "occupancy_std": float(np.std(occ_values)) if len(occ_values) else 0.0,
            "occupancy_max": float(np.max(occ_values)) if len(occ_values) else 0.0,
            "occupancy_observed_fraction": _observed_fraction(
                occ, "any_interaction_occupancy"
            ),
            "energy_mean": float(np.mean(energy_values)) if len(energy_values) else 0.0,
            "energy_std": float(np.std(energy_values)) if len(energy_values) else 0.0,
            "energy_observed_fraction": _observed_fraction(dyn, "mmgbsa_total_mean"),
            "rmsf_mean": float(np.mean(rmsf_values)) if len(rmsf_values) else 0.0,
            "rmsf_std": float(np.std(rmsf_values)) if len(rmsf_values) else 0.0,
            "window_complete_rate": 0.0,
        }
        for name in INTERACTION_NAMES.values():
            row[name] = 0.0
        if not ix.empty and "interaction_type" in ix.columns:
            for interaction_type, group in ix.groupby("interaction_type"):
                name = INTERACTION_NAMES.get(str(interaction_type))
                if name:
                    values = _safe_values(group, "occupancy")
                    row[name] = float(np.mean(values)) if len(values) else 0.0
        if not dyn.empty and "window_id" in dyn.columns:
            windows = dyn["window_id"].dropna().nunique()
            if windows:
                observed = dyn.get("any_interaction_occupancy", pd.Series(dtype=float)).notna().sum()
                residue_count = max(dyn.get("canonical_res_num", pd.Series(dtype=float)).nunique(), 1)
                row["window_complete_rate"] = float(observed / (windows * residue_count))
        row["md_mask"] = int(bool(occ_values.size or energy_values.size or rmsf_values.size))
        row["reward_total"] = float(np.clip(row["occupancy_mean"] - 0.1 * row["rmsf_mean"], -1.0, 1.0))
        rows.append(row)

    frame = pd.DataFrame(rows)
    fit = frame.loc[frame["md_mask"] == 1, MD_FEATURE_NAMES]
    if fit.empty:
        fit = frame[MD_FEATURE_NAMES]
    mean = np.nan_to_num(fit.to_numpy(dtype=float).mean(axis=0))
    std = np.nan_to_num(fit.to_numpy(dtype=float).std(axis=0), nan=1.0)
    std = np.where(std < 1e-8, 1.0, std)
    values = np.nan_to_num((frame[MD_FEATURE_NAMES].to_numpy(dtype=float) - mean) / std)
    for index, name in enumerate(MD_FEATURE_NAMES):
        frame[f"z_{name}"] = np.clip(values[:, index], -10.0, 10.0)
    spec = {
        "version": "md_target_v1",
        "dim": len(MD_FEATURE_NAMES),
        "names": MD_FEATURE_NAMES,
        "target_component": target_component,
    }
    scaler = {"columns": MD_FEATURE_NAMES, "mean": mean.tolist(), "std": std.tolist()}
    id_map = {
        "canonical_to_aliases": {value: [value] for value in molecule_ids},
        "alias_to_canonical": {value: value for value in molecule_ids},
    }
    (out / "MD_FEATURE_SPEC.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (out / "md_scaler.json").write_text(json.dumps(scaler, indent=2), encoding="utf-8")
    (out / "md_id_map.json").write_text(json.dumps(id_map, indent=2), encoding="utf-8")
    frame.to_csv(out / "md8_molecule_features.csv", index=False)
    source_has_parquet = any(
        (root / location / name).is_file()
        for location in (Path("COMBINED"), Path("."))
        for name in (
            "all8_residue_occupancy_canonical.parquet",
            "all8_interaction_occupancy_canonical.parquet",
            "all8_dynamic_window_residue.parquet",
            "all8_rmsf_residue.parquet",
        )
    )
    parquet_written = False
    if source_has_parquet:
        try:
            frame.to_parquet(out / "md8_molecule_features.parquet", index=False)
            parquet_written = True
        except (ImportError, ModuleNotFoundError, ValueError):
            # CSV is the canonical fallback; parquet remains an optional artifact.
            pass
    return {
        "ok": True,
        "n_molecules": len(frame),
        "dim": len(MD_FEATURE_NAMES),
        "target_component": target_component,
        "parquet_written": parquet_written,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build target-independent MD features")
    parser.add_argument("--combined-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--target-component", default=None)
    args = parser.parse_args()
    print(json.dumps(build_target_md_features(**vars(args)), indent=2))


if __name__ == "__main__":
    main()
