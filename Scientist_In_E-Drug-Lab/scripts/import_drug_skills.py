#!/usr/bin/env python3
"""Import curated project skills into Hermes.

Installs into $HERMES_HOME/skills/<category>/<name>/ as symlinks (live update)
and records skills.external_dirs + a MANIFEST under the project.

Keep set (GitHub bootstrap):
  funnel/      — full Track-H flowchart (14)
  ddfast/      — used DiffDynamic-Fast / MD helpers
  drug-design/ — generic chemistry helpers used in runs
  campaign/    — campaign memory helpers + scientist aliases

Sources are project-local only (`skills/`), so a fresh clone can import without
host-specific paths (~/.claude, nature-skills, /data/ye, …).
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

# ── Selections (locked for public bootstrap) ──────────────────────────────


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
    "scientist-in-e-drug-lab",
    "edrug-capability-check",
]

CATEGORIES: list[tuple[list[str], str]] = [
    (FUNNEL_FLOWCHART, "funnel"),
    (DDFAST, "ddfast"),
    (DRUG_DESIGN, "drug-design"),
    (CAMPAIGN, "campaign"),
]

SEARCH_ROOTS = [
    PROJECT_SKILLS,
]


def _find_skill(name: str) -> Path | None:
    nested_roots = [
        PROJECT_SKILLS,
        PROJECT_SKILLS / "scientist-in-e-drug-lab",
    ]
    search = nested_roots + [r for r in SEARCH_ROOTS if r not in nested_roots]
    for root in search:
        cand = root / name
        if (cand / "SKILL.md").is_file():
            return cand.resolve()
    # case-insensitive fallback
    lower = name.lower()
    for root in search:
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and child.name.lower() == lower and (child / "SKILL.md").is_file():
                return child.resolve()
    return None


def _rel_source(src: Path) -> str:
    """Prefer repo-relative paths in MANIFEST (portable for clones)."""
    try:
        return str(src.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(src.resolve())


def _link_skill(src: Path, dest: Path, *, mode: str) -> str:
    source = src.resolve()
    if source == dest.absolute():
        raise ValueError(f"refusing self-referential skill link: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    if mode == "copy":
        shutil.copytree(source, dest, symlinks=True)
        return "copied"
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


def _prune_managed_category(root: Path, allowed: list[str]) -> list[str]:
    """Remove stale entries from a managed category directory."""
    removed: list[str] = []
    if not root.is_dir():
        return removed
    allowed_names = set(allowed)
    for child in root.iterdir():
        if child.name in allowed_names:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)
        removed.append(child.name)
    return removed


def _install_group(
    names: list[str],
    category: str,
    skills_root: Path,
    *,
    mode: str,
) -> tuple[list[dict], list[str]]:
    ok: list[dict] = []
    missing: list[str] = []
    for name in names:
        src = _find_skill(name)
        if src is None:
            missing.append(name)
            continue
        dest = skills_root / category / name
        action = _link_skill(src, dest, mode=mode)
        ok.append(
            {
                "name": name,
                "category": category,
                "source": _rel_source(src),
                "dest": str(dest),
                "action": action,
            }
        )
    return ok, missing


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
    for p in external_dirs:
        s = str(p)
        if s not in dirs:
            dirs.append(s)
    eval_mode = os.environ.get("MASLD_COMPETITION_EVAL_MODE", "true").lower() == "true"
    skills["creation_enabled"] = not eval_mode
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_pack_docs(pack: Path, installed: list[dict], missing_all: list[str]) -> None:
    manifest = {
        "funnel_flowchart": FUNNEL_FLOWCHART,
        "ddfast": DDFAST,
        "drug_design": DRUG_DESIGN,
        "campaign": CAMPAIGN,
        "installed": [
            {
                "name": i["name"],
                "category": i["category"],
                "source": i["source"],
                "action": i["action"],
            }
            for i in installed
        ],
        "missing": missing_all,
    }
    (pack / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (pack / "README.md").write_text(
        "\n".join(
            [
                "# Skills pack (Scientist_In_E-Drug-Lab)",
                "",
                "Imported into Hermes `$HERMES_HOME/skills/<category>/`.",
                "Skill bodies live under `../skills/` (tracked); this pack holds symlinks + MANIFEST.",
                "",
                f"- **funnel**: {len(FUNNEL_FLOWCHART)} (整体流程图)",
                f"- **ddfast**: {len(DDFAST)} (QikProp / Glide SP / Desmond MD helpers)",
                f"- **drug-design**: {len(DRUG_DESIGN)} (rdkit / pose / membrane MD ops)",
                f"- **campaign**: {len(CAMPAIGN)} (campaign + scientist aliases)",
                "",
                "Removed from public bootstrap: MASLD s00–s08, hsv-*, writing/nature, unused ddfast 00–05/08–10.",
                "",
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
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate resolved skills after installation",
    )
    args = parser.parse_args()
    hermes_home: Path = args.hermes_home
    skills_root = hermes_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    installed: list[dict] = []
    missing_all: list[str] = []
    removed_stale: list[str] = []

    pack = ROOT / "skills_pack"
    for names, category in CATEGORIES:
        removed_stale.extend(_prune_managed_category(skills_root / category, names))
        removed_stale.extend(_prune_managed_category(pack / category, names))

    # Drop retired categories from pack / hermes mirrors
    for retired in ("writing", "masld-ai4s"):
        for root in (skills_root / retired, pack / retired):
            if root.exists() or root.is_symlink():
                if root.is_symlink() or root.is_file():
                    root.unlink()
                else:
                    shutil.rmtree(root)
                removed_stale.append(retired)

    for names, category in CATEGORIES:
        ok, missing = _install_group(names, category, skills_root, mode=args.mode)
        installed.extend(ok)
        missing_all.extend(missing)

    for cat in ("funnel", "ddfast", "drug-design", "campaign"):
        (pack / cat).mkdir(parents=True, exist_ok=True)
    for item in installed:
        src = PROJECT_SKILLS / item["name"]
        if not (src / "SKILL.md").is_file():
            # resolve via find again for nested names
            found = _find_skill(item["name"])
            if found is None:
                continue
            src = found
        dest = pack / item["category"] / item["name"]
        _link_skill(src, dest, mode=args.mode)

    _write_pack_docs(pack, installed, missing_all)
    _patch_hermes_config(hermes_home, [pack, skills_root])

    validation_errors = _validate_installed(installed) if args.check else []

    print(f"Installed {len(installed)} skill links under {skills_root}")
    if removed_stale:
        print(f"Pruned stale skills/categories: {', '.join(sorted(set(removed_stale)))}")
    for cat in ("funnel", "ddfast", "drug-design", "campaign"):
        n = sum(1 for i in installed if i["category"] == cat)
        print(f"  {cat}: {n}")
    if missing_all:
        print("MISSING:")
        for m in missing_all:
            print(f"  - {m}")
    if validation_errors:
        print("INVALID SKILLS:")
        for error in validation_errors:
            print(f"  - {error}")
    if missing_all or validation_errors:
        return 1
    print(f"MANIFEST: {pack / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
