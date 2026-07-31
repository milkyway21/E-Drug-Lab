#!/usr/bin/env python3
"""Select the Phase F top10 and build a self-contained light analysis package."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BATCH = "phaseF_medoid_pose_2_200_top16_20260728"
ANALYSIS = ROOT / "05_analysis" / BATCH
ASSESSMENT = ANALYSIS / "full20_200ns_assessment"
TRAJECTORIES = ROOT / "04_trajectories" / BATCH
LOGS = ROOT / "logs" / BATCH
DEFAULT_OUTPUT = Path.home() / "Desktop/HSD17B13_PhaseF_full20_200ns_light_package_20260731"
MAX_FILE_BYTES = 50 * 1024 * 1024

ANALYSIS_PARTS = {
    "primary16": ANALYSIS / "final_200ns",
    "supplemental2": ANALYSIS / "extra2_200ns_analysis",
    "supplemental34": ANALYSIS / "extra34_200ns_analysis",
}
SCRIPTS = [
    "12_analyze_md200.py",
    "25_phaseF_200ns_4gpu.py",
    "26_phaseF_sea.py",
    "35_phaseF_extra34_gpu25_queue.py",
    "36_phaseF_extra34_watchdog.py",
    "37_plot_phaseF_md200_5x4.py",
    "41_phaseF_full20_post_analysis.py",
    "42_export_phaseF_full20_tables_only.py",
    "43_phaseF_full20_analysis_watchdog.py",
    "44_package_phaseF_full20_delivery.py",
    "phaseF_common.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selection_basis(row: pd.Series) -> str:
    return (
        "A_pose_retained; ligand in pocket; final-50-ns plateau; pocket stable; "
        f"late direct contact={row['direct_contact_occupancy_late']:.3f}; "
        f"late dominant cluster={row['dominant_cluster_fraction']:.3f}; "
        "ordered by unified md_score"
    )


def build_top10() -> tuple[pd.DataFrame, list[str]]:
    decision_path = ASSESSMENT / "md200_decision_table.csv"
    decisions = pd.read_csv(decision_path).sort_values("rank", kind="stable")
    if len(decisions) != 20 or decisions["molecule_id"].nunique() != 20:
        raise RuntimeError("Full20 decision table does not contain 20 unique molecules")

    eligible = decisions.loc[
        decisions["md_class"].eq("A_pose_retained")
        & decisions["ligand_in_pocket"].eq(True)
        & decisions["late_plateau"].eq(True)
        & decisions["pocket_stable"].eq(True)
        & decisions["direct_contact_occupancy_late"].ge(0.90)
    ].copy()
    eligible = eligible.sort_values("md_score", ascending=False, kind="stable")
    if len(eligible) < 10:
        raise RuntimeError(f"Only {len(eligible)} molecules pass strict top10 stability gates")
    top10 = eligible.head(10).copy()
    top10.insert(0, "stable_binding_rank", range(1, 11))
    top10.insert(2, "selection_status", "selected_top10")
    top10.insert(3, "selection_basis", top10.apply(selection_basis, axis=1))

    preferred = [
        "stable_binding_rank",
        "molecule_id",
        "selection_status",
        "selection_basis",
        "rank",
        "md_class",
        "md_score",
        "wetlab_recommendation",
        "ligand_rmsd_late_median",
        "ligand_rmsd_late_p95",
        "ligand_rmsd_late_slope",
        "ligand_internal_rmsd_late_median",
        "ligand_pocket_com_initial",
        "ligand_pocket_com_late",
        "ligand_pocket_com_delta",
        "min_pocket_distance_late",
        "pocket_ca_late_median",
        "pocket_ca_late_p95",
        "pocket_ca_late_slope",
        "direct_contact_occupancy_full",
        "direct_contact_occupancy_late",
        "contact_residue_count_late_median",
        "key_contact_retention",
        "hydrogen_bond_occupancy",
        "hydrophobic_contact_occupancy",
        "water_bridge_occupancy",
        "dominant_cluster_fraction",
        "late_cluster_count",
        "late_plateau",
        "ligand_in_pocket",
        "pose_retained",
        "contact_retained",
        "pocket_stable",
        "number_of_transitions",
        "last_transition_ns",
        "manual_review_required",
        "rejection_or_selection_reason",
        "glide_xp",
        "mmgbsa",
        "smiles",
    ]
    columns = [column for column in preferred if column in top10.columns]
    columns.extend(column for column in top10.columns if column not in columns)
    top10 = top10[columns]

    csv_path = ASSESSMENT / "top10_stable_binding_candidates.csv"
    xlsx_path = ASSESSMENT / "top10_stable_binding_candidates.xlsx"
    top10.to_csv(csv_path, index=False)
    top10.to_excel(xlsx_path, index=False)

    ids = top10["molecule_id"].astype(str).tolist()
    summary = [
        "# HSD17B13 Phase F top10 stable-binding candidates",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "Eligibility: A_pose_retained, ligand_in_pocket, late_plateau, pocket_stable, "
        "and final-50-ns direct-contact occupancy >= 0.90.",
        "",
        "Ranking: unified md_score descending within the eligible set.",
        "",
    ]
    for row in top10.itertuples(index=False):
        summary.append(
            f"{row.stable_binding_rank}. {row.molecule_id}: score={row.md_score:.1f}, "
            f"late ligand RMSD={row.ligand_rmsd_late_median:.2f} A, "
            f"late direct contact={row.direct_contact_occupancy_late:.1%}, "
            f"dominant cluster={row.dominant_cluster_fraction:.1%}"
        )
    (ASSESSMENT / "top10_stable_binding_summary.md").write_text("\n".join(summary) + "\n")
    return top10, ids


class Packager:
    def __init__(self, output: Path):
        self.output = output
        self.files: list[dict[str, object]] = []
        self.excluded: list[dict[str, object]] = []

    def exclude(self, source: Path, reason: str) -> None:
        size = source.stat().st_size if source.is_file() else ""
        self.excluded.append({"source": str(source), "bytes": size, "reason": reason})

    def copy_file(self, source: Path, relative: Path) -> None:
        actual = source.resolve() if source.is_symlink() else source
        if not actual.is_file():
            raise FileNotFoundError(actual)
        if actual.stat().st_size > MAX_FILE_BYTES:
            self.exclude(actual, f"single file exceeds {MAX_FILE_BYTES} bytes")
            return
        destination = self.output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(actual, destination)
        self.files.append(
            {
                "file": str(relative),
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination),
                "source": str(source),
            }
        )

    def copy_tree(
        self,
        source: Path,
        relative: Path,
        excluded_directory_names: set[str] | None = None,
    ) -> None:
        excluded_directory_names = excluded_directory_names or set()
        for path in sorted(source.rglob("*")):
            if not path.is_file() and not path.is_symlink():
                continue
            subpath = path.relative_to(source)
            excluded_part = next(
                (part for part in subpath.parts if part in excluded_directory_names), None
            )
            if excluded_part:
                self.exclude(path, f"excluded directory category: {excluded_part}")
                continue
            self.copy_file(path, relative / subpath)

    def validate(self) -> None:
        for record in self.files:
            path = self.output / str(record["file"])
            if not path.is_file() or path.stat().st_size != record["bytes"]:
                raise RuntimeError(f"Package file validation failed: {path}")
            if sha256(path) != record["sha256"]:
                raise RuntimeError(f"Package checksum validation failed: {path}")


def find_validation(molecule_id: str) -> Path:
    for attempt in sorted((TRAJECTORIES / molecule_id).glob("attempt_*"), reverse=True):
        validation = attempt / "attempt_validation.json"
        if validation.is_file() and json.loads(validation.read_text()).get("valid"):
            return validation
    raise FileNotFoundError(f"{molecule_id}: no valid trajectory validation JSON")


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if not (ANALYSIS / "ANALYSIS_FULL20_DONE.flag").is_file():
        raise RuntimeError("Full20 analysis completion flag is absent")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing package: {output}")

    top10, top10_ids = build_top10()
    output.mkdir(parents=True)
    packager = Packager(output)

    for name in (
        "top10_stable_binding_candidates.csv",
        "top10_stable_binding_candidates.xlsx",
        "top10_stable_binding_summary.md",
    ):
        packager.copy_file(ASSESSMENT / name, Path("00_top10_selection") / name)

    packager.copy_tree(ASSESSMENT, Path("01_full20_analysis"))
    for label, source in ANALYSIS_PARTS.items():
        packager.copy_tree(
            source,
            Path("02_per_molecule_analysis") / label,
            excluded_directory_names={"representative_structures"},
        )
    packager.copy_tree(
        ANALYSIS / "sea",
        Path("03_sea"),
        excluded_directory_names={".schrodinger_tmp"},
    )
    packager.copy_tree(ANALYSIS / "schrodinger_reports", Path("04_schrodinger_reports"))

    for path in sorted(ANALYSIS.iterdir()):
        if path.is_file() and not path.name.startswith("."):
            packager.copy_file(path, Path("05_provenance/analysis_root") / path.name)
    packager.copy_tree(LOGS, Path("05_provenance/logs"))

    decision = pd.read_csv(ASSESSMENT / "md200_decision_table.csv")
    molecule_ids = decision.sort_values("rank", kind="stable")["molecule_id"].astype(str)
    for molecule_id in molecule_ids:
        packager.copy_file(
            find_validation(molecule_id),
            Path("05_provenance/trajectory_validation")
            / molecule_id
            / "attempt_validation.json",
        )
    for name in SCRIPTS:
        packager.copy_file(ROOT / "scripts" / name, Path("06_reproduction_scripts") / name)

    notes = output / "00_PACKAGE_NOTES.md"
    notes.write_text(
        "# HSD17B13 Phase F full20 light package\n\n"
        f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"Top10: {', '.join(top10_ids)}\n\n"
        "Included: final full20 tables and figures, source per-molecule analysis reports, "
        "SEA EAF/data/plots/reports, Schrodinger reports, trajectory validation JSON, logs, "
        "manifests, and reproduction scripts.\n\n"
        "Excluded: raw DTR trajectories, CMS/system files, per-molecule representative "
        "structure directories, SEA scratch directories, and individual files larger than "
        f"{MAX_FILE_BYTES / 1024 / 1024:.0f} MiB. The large-file exclusion mainly removes "
        "20 P-SSE_Timeline.svg files of about 109 MB each.\n"
    )
    packager.files.append(
        {
            "file": notes.name,
            "bytes": notes.stat().st_size,
            "sha256": sha256(notes),
            "source": "generated",
        }
    )
    packager.validate()

    pd.DataFrame(packager.files).sort_values("file").to_csv(
        output / "00_PACKAGE_MANIFEST.csv", index=False
    )
    pd.DataFrame(packager.excluded).sort_values(["reason", "source"]).to_csv(
        output / "00_EXCLUDED_FILES.csv", index=False
    )
    total_bytes = sum(int(record["bytes"]) for record in packager.files)
    print(f"Top10: {', '.join(top10_ids)}")
    print(f"Package files: {len(packager.files)}")
    print(f"Package bytes: {total_bytes}")
    print(f"Excluded entries: {len(packager.excluded)}")
    print(output)


if __name__ == "__main__":
    main()
