#!/usr/bin/env python3
"""Import the canonical, grouped E-Drug Lab skills into Hermes.

The source tree uses ``skills/<master>/<child>/SKILL.md``.  The master directory
also contains its own ``SKILL.md`` and is the default routing entrypoint.  Legacy
flat paths under ``skills/<child>`` are repository symlinks only; they are resolved
by the project compatibility helpers but are not published a second time to Hermes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT_SKILLS = ROOT / "skills"

# Retain these names for existing callers and manifests.  Canonical routing is
# defined by MASTER_CATEGORIES below.
FUNNEL_FLOWCHART = [
    "funnel-orchestrator",
    "funnel-campaign-memory",
    "funnel-diffdynamic-denovo",
    "funnel-diffdynamic-prudent",
    "funnel-glide-sp",
    "funnel-featurehit",
    "funnel-shape-screen",
    "funnel-drugflow-hepg2",
    "funnel-glide-xp",
    "funnel-mmgbsa",
    "funnel-desmond-short-md",
    "funnel-desmond-long-md",
    "funnel-comprehensive-analysis",
    "e-drug-lab-scientist",
]

DDFAST = [
    "ddfast-06-qikprop-admet",
    "ddfast-07-glide-sp",
    "dd-md-desmond",
    "dd-md-desmond-sea-qc",
]

DRUG_DESIGN = [
    "rdkit",
    "pose-library-screening",
    "desmond-membrane-md-ops",
]

CAMPAIGN = [
    "desmond-md-campaign",
    "time-scheduler",
    "reporting",
    "scientist-in-e-drug-lab",
    "edrug-capability-check",
]

EVIDENCE = [
    "scope-molecular-nomination",
    "research-target-biology",
    "search-biomedical-evidence",
    "assess-target-pharmacology",
    "rank-protein-structures",
    "assess-computational-pharmacology",
    "prepare-native-protein-ligand",
    "qualify-binding-pocket",
    "enrich-compound-evidence",
    "triage-compound-toxicity",
    "nominate-lipid-modulators",
    "write-mechanism-validation-report",
]

LEGACY_CATEGORIES: dict[str, list[str]] = {
    "funnel": FUNNEL_FLOWCHART,
    "ddfast": DDFAST,
    "drug-design": DRUG_DESIGN,
    "campaign": CAMPAIGN,
    "evidence": EVIDENCE,
}

MASTER_CATEGORIES: dict[str, list[str]] = {
    "drug-discovery-orchestrator": [
        "e-drug-lab-scientist",
        "funnel-orchestrator",
        "scientist-in-e-drug-lab",
        "funnel-campaign-memory",
        "time-scheduler",
        "reporting",
        "edrug-capability-check",
    ],
    "target-discovery": [
        "scope-molecular-nomination",
        "research-target-biology",
        "search-biomedical-evidence",
        "assess-target-pharmacology",
        "rank-protein-structures",
        "assess-computational-pharmacology",
        "prepare-native-protein-ligand",
        "qualify-binding-pocket",
    ],
    "dd-generation": [
        "funnel-diffdynamic-denovo",
        "funnel-diffdynamic-prudent",
    ],
    "virtual-docking": [
        "funnel-glide-sp",
        "ddfast-07-glide-sp",
        "funnel-glide-xp",
        "funnel-mmgbsa",
    ],
    "featurehit-finding": [
        "funnel-featurehit",
        "funnel-shape-screen",
        "pose-library-screening",
        "rdkit",
    ],
    "admet": [
        "funnel-drugflow-hepg2",
        "ddfast-06-qikprop-admet",
        "enrich-compound-evidence",
        "triage-compound-toxicity",
    ],
    "molecular-dynamics": [
        "funnel-desmond-short-md",
        "funnel-desmond-long-md",
        "dd-md-desmond",
        "dd-md-desmond-sea-qc",
        "desmond-md-campaign",
        "desmond-membrane-md-ops",
    ],
    "all-analysis": [
        "funnel-comprehensive-analysis",
        "nominate-lipid-modulators",
        "write-mechanism-validation-report",
    ],
}

# Existing tests and downstream scripts import CATEGORIES.  Keep it as the
# legacy view while all installation code uses the canonical map above.
CATEGORIES: list[tuple[list[str], str]] = [
    (names, category) for category, names in LEGACY_CATEGORIES.items()
]

SEARCH_ROOTS = [PROJECT_SKILLS]
EXCLUDED_ASSET_DIRS = {"__pycache__", "hsd17b13_reference"}
EXCLUDED_ASSET_FILES = {"WORKFLOW.md", "WORKFLOW_8G9V_T001.md"}


def _canonical_skill_dirs() -> list[tuple[str, str, Path]]:
    entries: list[tuple[str, str, Path]] = []
    for master, children in MASTER_CATEGORIES.items():
        master_path = PROJECT_SKILLS / master
        entries.append((master, master, master_path))
        for child in children:
            entries.append((master, child, master_path / child))
    return entries


CANONICAL_SKILLS = _canonical_skill_dirs()


def _direct_skill_names() -> list[str]:
    """Return legacy flat names, excluding canonical master directories."""
    return sorted(
        child.name
        for child in PROJECT_SKILLS.iterdir()
        if child.is_symlink() and (child / "SKILL.md").is_file()
    ) if PROJECT_SKILLS.is_dir() else []


def _find_skill(name: str) -> Path | None:
    """Resolve a master, canonical child, or legacy flat skill name."""
    direct = PROJECT_SKILLS / name
    if (direct / "SKILL.md").is_file():
        return direct.resolve()
    lower = name.lower()
    for _master, child_name, path in CANONICAL_SKILLS:
        if child_name.lower() == lower and (path / "SKILL.md").is_file():
            return path.resolve()
    return None


def _rel_source(src: Path) -> str:
    try:
        return str(src.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(src.resolve())


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _link_skill(src: Path, dest: Path, *, mode: str) -> str:
    """Link/copy one skill while excluding nested child skill directories."""
    source = src.resolve()
    if source == dest.absolute():
        raise ValueError(f"refusing self-referential skill link: {dest}")
    standard_assets = {
        "SKILL.md",
        "agents",
        "assets",
        "references",
        "scripts",
        "LICENSE",
        "LICENSE.md",
        "NOTICE",
    }
    nested_children = {
        item.relative_to(source).parts[0]
        for item in source.rglob("SKILL.md")
        if item.parent != source
    }
    publishable = standard_assets - nested_children
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        _remove_path(dest)
    if mode == "copy":
        def ignore_assets(current: str, names: list[str]) -> set[str]:
            ignored = {
                name
                for name in names
                if name in EXCLUDED_ASSET_DIRS
                or name in EXCLUDED_ASSET_FILES
                or name.endswith(".pyc")
            }
            if Path(current).resolve() == source:
                ignored.update(set(names) - publishable)
            return ignored

        shutil.copytree(
            source,
            dest,
            symlinks=True,
            ignore=ignore_assets,
        )
        return "copied-filtered" if nested_children else "copied"
    if nested_children:
        dest.mkdir()
        for child in source.iterdir():
            if (
                child.name not in publishable
                or child.name in EXCLUDED_ASSET_DIRS
                or child.name in EXCLUDED_ASSET_FILES
            ):
                continue
            (dest / child.name).symlink_to(child.resolve(), target_is_directory=child.is_dir())
        return "symlinked-filtered"
    dest.symlink_to(source, target_is_directory=True)
    return "symlinked"


def _validate_installed(installed: list[dict]) -> list[str]:
    errors: list[str] = []
    for item in installed:
        destination = Path(item["dest"])
        try:
            resolved = destination.resolve(strict=True)
        except (FileNotFoundError, RuntimeError) as exc:
            errors.append(f"{item['name']}: broken or cyclic link: {exc}")
            continue
        if not (resolved / "SKILL.md").is_file():
            errors.append(f"{item['name']}: SKILL.md missing at {resolved}")
    return errors


def _prune_managed_category(root: Path, allowed: set[str]) -> list[str]:
    removed: list[str] = []
    if not root.is_dir() or root.is_symlink():
        return removed
    for child in root.iterdir():
        if child.name in allowed:
            continue
        _remove_path(child)
        removed.append(child.name)
    return removed


def _install_canonical_group(
    master: str,
    children: list[str],
    skills_root: Path,
    *,
    mode: str,
) -> tuple[list[dict], list[str]]:
    source_root = PROJECT_SKILLS / master
    destination_root = skills_root / master
    allowed = {"SKILL.md", *children}
    removed = _prune_managed_category(destination_root, allowed)
    if destination_root.exists() or destination_root.is_symlink():
        _remove_path(destination_root)

    installed: list[dict] = []
    missing: list[str] = []
    if not (source_root / "SKILL.md").is_file():
        return installed, [master]

    action = _link_skill(source_root, destination_root, mode=mode)
    installed.append(
        {
            "name": master,
            "category": master,
            "kind": "master",
            "source": _rel_source(source_root),
            "dest": str(destination_root),
            "action": action,
        }
    )
    for child in children:
        source = source_root / child
        if not (source / "SKILL.md").is_file():
            missing.append(child)
            continue
        dest = destination_root / child
        action = _link_skill(source, dest, mode=mode)
        installed.append(
            {
                "name": child,
                "category": master,
                "kind": "child",
                "source": _rel_source(source),
                "dest": str(dest),
                "action": action,
            }
        )
    return installed, missing + [f"removed:{name}" for name in removed]


def _patch_hermes_config(hermes_home: Path, external_dirs: list[Path]) -> None:
    cfg_path = hermes_home / "config.yaml"
    data: dict = {}
    if cfg_path.is_file():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    skills = data.setdefault("skills", {})
    if not isinstance(skills, dict):
        skills = {}
        data["skills"] = skills
    dirs = skills.setdefault("external_dirs", [])
    if not isinstance(dirs, list):
        dirs = []
        skills["external_dirs"] = dirs
    for path in external_dirs:
        value = str(path)
        if value not in dirs:
            dirs.append(value)
    eval_mode = os.environ.get("MASLD_COMPETITION_EVAL_MODE", "true").lower() == "true"
    skills["creation_enabled"] = not eval_mode
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_pack_docs(pack: Path, installed: list[dict], missing: list[str]) -> None:
    aliases = {
        child: f"{master}/{child}"
        for master, children in MASTER_CATEGORIES.items()
        for child in children
    }
    published: dict[tuple[str, str], dict] = {}
    for item in installed:
        key = (str(item["category"]), str(item["name"]))
        published.setdefault(
            key,
            {
                "name": item["name"],
                "category": item["category"],
                "kind": item["kind"],
                "source": item["source"],
                "destination": f"{item['category']}/{item['name']}",
                "action": item["action"],
            },
        )
    manifest = {
        "master_categories": MASTER_CATEGORIES,
        "legacy_categories": LEGACY_CATEGORIES,
        "compatibility_aliases": aliases,
        "installed": sorted(published.values(), key=lambda item: (item["category"], item["name"])),
        "published_count": len(published),
        "missing": missing,
    }
    (pack / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    category_lines = [
        f"- **{master}**: {len(children)} child skills"
        for master, children in MASTER_CATEGORIES.items()
    ]
    (pack / "README.md").write_text(
        "\n".join(
            [
                "# Skills pack (Scientist_In_E-Drug-Lab)",
                "",
                "Imported into Hermes `$HERMES_HOME/skills/<master>/<child>/`.",
                "Canonical skill bodies live under `../skills/<master>/<child>/`;",
                "the old flat names remain repository compatibility symlinks only.",
                "",
                *category_lines,
                "",
                "Only canonical master and child skills are published to Hermes to avoid duplicate names.",
                "Re-run: `python scripts/import_drug_skills.py`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hermes-home",
        type=Path,
        default=Path(os.environ.get("HERMES_HOME", ROOT / ".hermes")),
    )
    parser.add_argument(
        "--mode",
        choices=("symlink", "copy"),
        default="symlink",
        help="symlink keeps live sync with local skill sources",
    )
    parser.add_argument("--check", action="store_true", help="validate resolved skills after installation")
    args = parser.parse_args()

    hermes_home = args.hermes_home
    skills_root = hermes_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    pack = ROOT / "skills_pack"
    pack.mkdir(parents=True, exist_ok=True)

    installed: list[dict] = []
    missing: list[str] = []
    removed: list[str] = []
    for master, children in MASTER_CATEGORIES.items():
        for root in (skills_root / master, pack / master):
            removed.extend(_prune_managed_category(root, {"SKILL.md", *children}))
    for retired in (*LEGACY_CATEGORIES, "project", "writing", "masld-ai4s"):
        for root in (skills_root / retired, pack / retired):
            if root.exists() or root.is_symlink():
                _remove_path(root)
                removed.append(retired)

    for master, children in MASTER_CATEGORIES.items():
        for destination_root in (skills_root, pack):
            group, group_missing = _install_canonical_group(
                master,
                children,
                destination_root,
                mode=args.mode,
            )
            installed.extend(
                {**item, "destination_root": str(destination_root)} for item in group
            )
            missing.extend(item for item in group_missing if not item.startswith("removed:"))
            removed.extend(item[8:] for item in group_missing if item.startswith("removed:"))

    _write_pack_docs(pack, installed, missing)
    _patch_hermes_config(hermes_home, [pack, skills_root])
    validation_errors = _validate_installed(
        [item for item in installed if Path(item["destination_root"]).resolve() == skills_root.resolve()]
    ) if args.check else []

    print(f"Installed {len(installed)} canonical skill entries under {skills_root}")
    if removed:
        print(f"Pruned stale entries: {', '.join(sorted(set(removed)))}")
    for master, children in MASTER_CATEGORIES.items():
        print(f"  {master}: {len(children)} children + master")
    if missing:
        print("MISSING:")
        for item in sorted(set(missing)):
            print(f"  - {item}")
    if validation_errors:
        print("INVALID SKILLS:")
        for error in validation_errors:
            print(f"  - {error}")
    if missing or validation_errors:
        return 1
    print(f"MANIFEST: {pack / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
