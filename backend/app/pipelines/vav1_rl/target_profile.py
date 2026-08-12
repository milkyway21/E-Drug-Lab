"""Target runtime metadata and automatic Glide schema discovery.

The model never needs to know a target's residue numbering.  A profile keeps
the target-specific files and the raw Glide columns at the I/O boundary, then
the feature store converts them to the shared, fixed-width schema.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd


TARGET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
GLIDE_SCORE_NAMES = (
    "docking_score",
    "glide_emodel",
    "glide_evdw",
    "glide_ecoul",
)


def _path(value: Any, base_dir: Optional[Path] = None) -> Optional[Path]:
    if value in (None, ""):
        return None
    result = Path(str(value)).expanduser()
    if base_dir is not None and not result.is_absolute():
        result = base_dir / result
    return result


def _validate_target_id(target_id: str) -> str:
    value = str(target_id).strip()
    if not TARGET_ID_RE.fullmatch(value):
        raise ValueError(
            "target_id must contain 1-64 ASCII letters, numbers, '.', '_' or '-'"
        )
    return value


@dataclass(frozen=True)
class TargetProfile:
    """All target-dependent runtime inputs needed by the pipeline."""

    target_id: str
    receptor_pdb: Optional[Path] = None
    prepared_receptor: Optional[Path] = None
    grid_file: Optional[Path] = None
    receptor_chain: Optional[str] = None
    glide_table: Optional[Path] = None
    md_dir: Optional[Path] = None
    md_weights: Optional[Path] = None
    activity_table: Optional[Path] = None
    generation_source: Optional[Path] = None
    reference_library: Optional[Path] = None
    target_component: Optional[str] = None
    activity_metric: Optional[str] = None
    activity_direction: str = "greater_is_active"
    generation_command: tuple[str, ...] = ()
    generation_env: dict[str, str] = field(default_factory=dict)
    generation_timeout_seconds: int = 7200
    active_threshold: Optional[float] = None
    weak_threshold: Optional[float] = None
    strong_threshold: Optional[float] = None
    score_columns: dict[str, str] = field(default_factory=dict)
    ifp_columns: tuple[str, ...] = ()
    contact_count_column: Optional[str] = None
    interaction_count_column: Optional[str] = "residue_counts"
    schema_version: str = "glide_target_v2"
    source: str = "explicit"

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", _validate_target_id(self.target_id))
        for name in (
            "receptor_pdb",
            "prepared_receptor",
            "grid_file",
            "glide_table",
            "md_dir",
            "md_weights",
            "activity_table",
            "generation_source",
            "reference_library",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value).expanduser())
        if self.receptor_chain is not None:
            chain = str(self.receptor_chain).strip()
            if not chain or len(chain) > 8:
                raise ValueError("receptor_chain must be a short non-empty identifier")
            object.__setattr__(self, "receptor_chain", chain)
        if self.target_component is not None:
            component = str(self.target_component).strip()
            if not component:
                raise ValueError("target_component must be non-empty when provided")
            object.__setattr__(self, "target_component", component)
        if self.md_dir is not None and self.target_component is None:
            raise ValueError("target_component is required when md_dir is configured")
        direction = str(self.activity_direction or "").strip().lower()
        if direction not in {"greater_is_active", "less_is_active"}:
            raise ValueError(
                "activity_direction must be 'greater_is_active' or 'less_is_active'"
            )
        object.__setattr__(self, "activity_direction", direction)
        if self.activity_metric is not None:
            metric = str(self.activity_metric).strip()
            if not metric:
                raise ValueError("activity_metric must be non-empty when provided")
            object.__setattr__(self, "activity_metric", metric)
        command = tuple(str(item) for item in (self.generation_command or ()))
        if any(not item for item in command):
            raise ValueError("generation_command entries must be non-empty")
        object.__setattr__(self, "generation_command", command)
        env = {
            str(key): str(value)
            for key, value in (self.generation_env or {}).items()
        }
        object.__setattr__(self, "generation_env", env)
        timeout = int(self.generation_timeout_seconds)
        if timeout <= 0:
            raise ValueError("generation_timeout_seconds must be positive")
        object.__setattr__(self, "generation_timeout_seconds", timeout)
        object.__setattr__(self, "ifp_columns", tuple(self.ifp_columns))

    @classmethod
    def from_dict(
        cls,
        values: Mapping[str, Any],
        *,
        base_dir: Optional[Path] = None,
    ) -> "TargetProfile":
        raw = dict(values)
        target_id = raw.pop("target_id", raw.pop("target", None))
        if not target_id:
            raise ValueError("target profile requires target_id")
        raw["target_id"] = target_id
        for name in (
            "receptor_pdb",
            "prepared_receptor",
            "grid_file",
            "glide_table",
            "md_dir",
            "md_weights",
            "activity_table",
            "generation_source",
            "reference_library",
        ):
            raw[name] = _path(raw.get(name), base_dir)
        raw["score_columns"] = {
            str(k): str(v) for k, v in (raw.get("score_columns") or {}).items()
        }
        raw["ifp_columns"] = tuple(raw.get("ifp_columns") or ())
        generation_command = raw.get("generation_command") or ()
        if isinstance(generation_command, str):
            raise ValueError("generation_command must be a JSON list of argv tokens")
        raw["generation_command"] = tuple(generation_command)
        raw["generation_env"] = {
            str(key): str(value)
            for key, value in (raw.get("generation_env") or {}).items()
        }
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in raw.items() if key in allowed})

    @classmethod
    def load(cls, path: Path | str) -> "TargetProfile":
        profile_path = Path(path).expanduser().resolve()
        if not profile_path.is_file():
            raise FileNotFoundError(f"target profile not found: {profile_path}")
        try:
            values = json.loads(profile_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid target profile JSON: {profile_path}") from exc
        if not isinstance(values, dict):
            raise ValueError("target profile must be a JSON object")
        return cls.from_dict(values, base_dir=profile_path.parent)

    def to_dict(self) -> dict[str, Any]:
        values = asdict(self)
        for key, value in values.items():
            if isinstance(value, Path):
                values[key] = str(value)
            elif isinstance(value, tuple):
                values[key] = list(value)
        return values

    def save(self, path: Path | str) -> Path:
        profile_path = Path(path).expanduser()
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        values = self.to_dict()
        for name in (
            "receptor_pdb",
            "prepared_receptor",
            "grid_file",
            "glide_table",
            "md_dir",
            "md_weights",
            "activity_table",
            "generation_source",
            "reference_library",
        ):
            value = values.get(name)
            if value and not Path(value).is_absolute():
                values[name] = str(Path(value).expanduser().resolve())
        profile_path.write_text(
            json.dumps(values, indent=2, sort_keys=True), encoding="utf-8"
        )
        return profile_path

    def validate_files(self, *, require_glide: bool = False) -> None:
        for label, value in (
            ("receptor_pdb", self.receptor_pdb),
            ("prepared_receptor", self.prepared_receptor),
            ("grid_file", self.grid_file),
            ("glide_table", self.glide_table),
            ("md_dir", self.md_dir),
            ("md_weights", self.md_weights),
            ("activity_table", self.activity_table),
            ("generation_source", self.generation_source),
            ("reference_library", self.reference_library),
        ):
            if value is None:
                continue
            expected = value.is_dir() if label == "md_dir" else value.is_file()
            if not expected:
                raise FileNotFoundError(f"{label} not found: {value}")
        if require_glide and self.glide_table is None:
            raise ValueError("target profile requires glide_table for Glide features")


def _find_contact_count_column(columns: list[str], target_id: str) -> Optional[str]:
    lower = {str(column).lower(): str(column) for column in columns}
    candidates = [
        f"n_{target_id.lower()}_residues",
        "n_contact_residues",
        "n_residues",
    ]
    if target_id.lower() == "vav1":
        candidates.insert(2, "n_vav1_residues")
    for candidate in candidates:
        if candidate in lower:
            return lower[candidate]
    return None


def _find_interaction_count_column(columns: list[str]) -> Optional[str]:
    lower = {str(column).lower(): str(column) for column in columns}
    for candidate in (
        "residue_counts",
        "interaction_counts",
        "interaction_count",
        "contact_interactions",
    ):
        if candidate in lower:
            return lower[candidate]
    return None


def infer_glide_profile(
    target_id: str,
    glide_table: Path | str,
    *,
    receptor_pdb: Path | str | None = None,
    prepared_receptor: Path | str | None = None,
    grid_file: Path | str | None = None,
    receptor_chain: str | None = None,
    md_dir: Path | str | None = None,
    md_weights: Path | str | None = None,
    activity_table: Path | str | None = None,
    generation_source: Path | str | None = None,
    reference_library: Path | str | None = None,
    active_threshold: float | None = None,
    weak_threshold: float | None = None,
    strong_threshold: float | None = None,
    target_component: str | None = None,
    activity_metric: str | None = None,
    activity_direction: str = "greater_is_active",
    generation_command: tuple[str, ...] | list[str] = (),
    generation_env: Mapping[str, str] | None = None,
    generation_timeout_seconds: int = 7200,
) -> TargetProfile:
    """Infer target-specific raw columns from a Glide result table."""
    table_path = Path(glide_table).expanduser().resolve()
    if not table_path.is_file():
        raise FileNotFoundError(f"Glide table not found: {table_path}")
    frame = pd.read_csv(table_path, nrows=0)
    columns = [str(column) for column in frame.columns]
    lower = {column.lower(): column for column in columns}
    score_columns = {
        name: lower[name]
        for name in GLIDE_SCORE_NAMES
        if name in lower
    }
    missing_scores = [name for name in GLIDE_SCORE_NAMES if name not in score_columns]
    if missing_scores:
        raise ValueError(
            f"Glide table is missing required score columns: {missing_scores}"
        )
    ifp_columns = tuple(sorted(column for column in columns if column.lower().startswith("ifp_")))
    contact_column = _find_contact_count_column(columns, target_id)
    if not ifp_columns and contact_column is None:
        raise ValueError("Glide table has neither ifp_* nor contact-count columns")
    return TargetProfile(
        target_id=target_id,
        receptor_pdb=_path(receptor_pdb),
        prepared_receptor=_path(prepared_receptor),
        grid_file=_path(grid_file),
        receptor_chain=receptor_chain,
        glide_table=table_path,
        md_dir=_path(md_dir),
        md_weights=_path(md_weights),
        activity_table=_path(activity_table),
        generation_source=_path(generation_source),
        reference_library=_path(reference_library),
        target_component=target_component,
        activity_metric=activity_metric,
        activity_direction=activity_direction,
        generation_command=tuple(generation_command),
        generation_env=dict(generation_env or {}),
        generation_timeout_seconds=generation_timeout_seconds,
        active_threshold=active_threshold,
        weak_threshold=weak_threshold,
        strong_threshold=strong_threshold,
        score_columns=score_columns,
        ifp_columns=ifp_columns,
        contact_count_column=contact_column,
        interaction_count_column=_find_interaction_count_column(columns),
        source="glide_inferred",
    )


def load_or_infer_profile(
    profile: Path | str | Mapping[str, Any] | TargetProfile | None,
    *,
    target_id: str | None = None,
    glide_table: Path | str | None = None,
) -> Optional[TargetProfile]:
    if profile is not None:
        if isinstance(profile, TargetProfile) or (
            hasattr(profile, "target_id") and hasattr(profile, "glide_table")
        ):
            return profile
        if isinstance(profile, Mapping):
            return TargetProfile.from_dict(profile)
        return TargetProfile.load(profile)
    if target_id and glide_table:
        return infer_glide_profile(target_id, glide_table)
    if target_id and str(target_id).lower() != "vav1":
        raise ValueError(
            "target_profile or glide_table is required for every non-VAV1 target"
        )
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Infer a target profile from Glide SP CSV")
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--glide-table", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receptor-pdb")
    parser.add_argument("--prepared-receptor")
    parser.add_argument("--grid-file")
    parser.add_argument("--receptor-chain")
    parser.add_argument("--md-dir")
    parser.add_argument("--md-weights")
    parser.add_argument("--activity-table")
    parser.add_argument("--generation-source")
    parser.add_argument("--reference-library")
    parser.add_argument("--target-component")
    parser.add_argument("--activity-metric")
    parser.add_argument(
        "--activity-direction",
        choices=("greater_is_active", "less_is_active"),
        default="greater_is_active",
    )
    parser.add_argument("--generation-command", nargs="+", default=())
    parser.add_argument("--generation-timeout-seconds", type=int, default=7200)
    parser.add_argument("--active-threshold", type=float)
    parser.add_argument("--weak-threshold", type=float)
    parser.add_argument("--strong-threshold", type=float)
    args = parser.parse_args()
    profile = infer_glide_profile(
        args.target_id,
        args.glide_table,
        receptor_pdb=args.receptor_pdb,
        prepared_receptor=args.prepared_receptor,
        grid_file=args.grid_file,
        receptor_chain=args.receptor_chain,
        md_dir=args.md_dir,
        md_weights=args.md_weights,
        activity_table=args.activity_table,
        generation_source=args.generation_source,
        reference_library=args.reference_library,
        target_component=args.target_component,
        activity_metric=args.activity_metric,
        activity_direction=args.activity_direction,
        generation_command=args.generation_command,
        generation_timeout_seconds=args.generation_timeout_seconds,
        active_threshold=args.active_threshold,
        weak_threshold=args.weak_threshold,
        strong_threshold=args.strong_threshold,
    )
    profile.save(args.output)
    print(json.dumps(profile.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
