#!/usr/bin/env python3
"""Import curated local drug-design / writing / self-written skills into Hermes.

Installs into $HERMES_HOME/skills/<category>/<name>/ as symlinks (live update)
and records skills.external_dirs + a MANIFEST under the project.

Categories:
  ddfast/       — DiffDynamic-Fast funnel 00–10 (all)
  drug-design/  — curated 20 specialized chemistry/SBDD skills
  writing/      — curated 10 paper / Nature writing skills
  masld-ai4s/   — self-written MASLD competition + scientist agent skills
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CURSOR_SKILLS = Path.home() / ".cursor" / "skills"
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"
YE_CLAUDE = Path("/data/ye/.claude/skills")
NATURE = Path("/data/ye/e-drug-lab/nature-skills/skills")
EDRUG_SKILLS = Path("/data/ye/e-drug-lab/skills")
PROJECT_SKILLS = ROOT / "skills"

# ── Selections (locked for this agent) ───────────────────────────────────

DDFAST = [
    "ddfast-00-pipeline-brief",
    "ddfast-01-input-gate",
    "ddfast-02-fast-denovo",
    "ddfast-03-fast-scaffold",
    "ddfast-04-extract-novina",
    "ddfast-05-smiles-dedup",
    "ddfast-06-qikprop-admet",
    "ddfast-07-glide-sp",
    "ddfast-08-glide-xp",
    "ddfast-09-mmgbsa-ifd",
    "ddfast-10-rank-manual",
]

DRUG_DESIGN_20 = [
    "diffdynamic-generation",
    "diffdynamic-paper-plots-2",
    "modelbatchsampleandcomparsion-2",
    "molecular-docking-autodock-2",
    "mol-render-2",
    "pocket-comparison",
    "rdkit-2",
    "chemistry-query-2",
    "pubchem-database-2",
    "find-topk-similiar-chemicals-rdkit",
    "find-topk-similiar-chemicals-pubchem-database",
    "active-ligands",
    "drug-team-2",
    "admet-filter",
    "ligand-pipeline",
    "bio-orchestrator-2",
    "Bioinformatics-2",
    "academic-search",
    "nature-academic-search",
    "mfds-drug-safety",
]

WRITING_10 = [
    "nature-writing",
    "nature-polishing",
    "nature-citation",
    "nature-figure",
    "nature-data",
    "nature-reader",
    "nature-response",
    "nature-paper2ppt",
    "nature-academic-search",
    "academic-search",
]

SELF_WRITTEN = [
    "s00-competition-brief",
    "s01-library-ingest-qc",
    "s02-reference-actives",
    "s03-physchem-tox-filter",
    "s04-similarity-pharmacophore",
    "s05-target-evidence-scoring",
    "s06-dual-objective-rank",
    "s07-mechanism-hypothesis",
    "s08-submission-export",
    "scientist-in-e-drug-lab",
    # HSV Pol / four-mutant funnel (nested under skills/scientist-in-e-drug-lab/)
    "hsv-00-pipeline-brief",
    "hsv-01-diffdynamic-generate",
    "hsv-02-receptor-grid",
    "hsv-03-sp-fill-rank",
    "hsv-04-seed-ifd",
    "hsv-05-shape-screen",
    "hsv-06-shape-candidate-sp",
    "hsv-07-shape-top200-ifd",
]

SEARCH_ROOTS = [
    CURSOR_SKILLS,
    CLAUDE_SKILLS,
    YE_CLAUDE,
    NATURE,
    EDRUG_SKILLS,
    PROJECT_SKILLS,
]


def _find_skill(name: str) -> Path | None:
    nested_roots = [
        PROJECT_SKILLS / "scientist-in-e-drug-lab",
        PROJECT_SKILLS,
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


def _link_skill(src: Path, dest: Path, *, mode: str) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    if mode == "copy":
        shutil.copytree(src, dest, symlinks=True)
        return "copied"
    dest.symlink_to(src, target_is_directory=True)
    return "symlinked"


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
                "source": str(src),
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
    # Keep skill creation under HERMES_HOME for skill_manager
    skills.setdefault("creation_enabled", True)
    cfg_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
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
    args = parser.parse_args()
    hermes_home: Path = args.hermes_home
    skills_root = hermes_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    installed: list[dict] = []
    missing_all: list[str] = []

    for names, category in (
        (DDFAST, "ddfast"),
        (DRUG_DESIGN_20, "drug-design"),
        (WRITING_10, "writing"),
        (SELF_WRITTEN, "masld-ai4s"),
    ):
        ok, missing = _install_group(names, category, skills_root, mode=args.mode)
        installed.extend(ok)
        missing_all.extend(missing)

    # Project-side mirror for docs / external_dirs (category layout)
    pack = ROOT / "skills_pack"
    for cat in ("ddfast", "drug-design", "writing", "masld-ai4s"):
        (pack / cat).mkdir(parents=True, exist_ok=True)
    # Refresh pack symlinks to same sources
    for item in installed:
        src = Path(item["source"])
        dest = pack / item["category"] / item["name"]
        _link_skill(src, dest, mode=args.mode)

    manifest = {
        "ddfast": DDFAST,
        "drug_design_20": DRUG_DESIGN_20,
        "writing_10": WRITING_10,
        "self_written": SELF_WRITTEN,
        "installed": installed,
        "missing": missing_all,
        "hermes_skills_root": str(skills_root),
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
                "",
                f"- **ddfast**: {len(DDFAST)} (00–10 full funnel)",
                f"- **drug-design**: {len(DRUG_DESIGN_20)} curated",
                f"- **writing**: {len(WRITING_10)} curated",
                f"- **masld-ai4s**: {len(SELF_WRITTEN)} self-written",
                "",
                "Re-run: `python scripts/import_drug_skills.py`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    _patch_hermes_config(hermes_home, [pack, skills_root])

    print(f"Installed {len(installed)} skill links under {skills_root}")
    for cat in ("ddfast", "drug-design", "writing", "masld-ai4s"):
        n = sum(1 for i in installed if i["category"] == cat)
        print(f"  {cat}: {n}")
    if missing_all:
        print("MISSING:")
        for m in missing_all:
            print(f"  - {m}")
        return 1
    print(f"MANIFEST: {pack / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
