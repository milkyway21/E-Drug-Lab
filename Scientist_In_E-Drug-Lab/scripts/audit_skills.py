#!/usr/bin/env python3
"""Audit canonical grouped project skills and their compatibility aliases."""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
from collections import Counter
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
IMPORTER_PATH = SCRIPT_DIR / "import_drug_skills.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("skill_import_catalog", IMPORTER_PATH)
assert IMPORTER_SPEC is not None and IMPORTER_SPEC.loader is not None
IMPORTER = importlib.util.module_from_spec(IMPORTER_SPEC)
IMPORTER_SPEC.loader.exec_module(IMPORTER)
CATEGORIES = IMPORTER.CATEGORIES
MASTER_CATEGORIES = IMPORTER.MASTER_CATEGORIES
CANONICAL_SKILLS = IMPORTER.CANONICAL_SKILLS
LEGACY_CATEGORIES = IMPORTER.LEGACY_CATEGORIES
PROJECT_SKILLS = IMPORTER.PROJECT_SKILLS


ROOT = PROJECT_SKILLS.parent
FRONTMATTER_KEYS = {"name", "description"}
LINK_PATTERN = re.compile(r"\[[^]]*\]\(([^)]+)\)")
HOST_PATH_PATTERN = re.compile(r"/(?:data|home)/[^\s`'\"<>]+")
URL_PATTERN = re.compile(r"https?://[^\s`'\"<>]+")


def _frontmatter(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc
    data = yaml.safe_load("\n".join(lines[1:end]))
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data


def _active_skill_dirs() -> list[Path]:
    return [path for _master, _name, path in CANONICAL_SKILLS if (path / "SKILL.md").is_file()]


def _catalog_names() -> list[str]:
    return [master for master in MASTER_CATEGORIES] + [
        name for names in MASTER_CATEGORIES.values() for name in names
    ]


def _compatibility_aliases() -> dict[str, Path]:
    aliases: dict[str, Path] = {}
    for master, children in MASTER_CATEGORIES.items():
        for child in children:
            aliases[child] = PROJECT_SKILLS / master / child
    return aliases


def _portable_text_assets(skill_dir: Path) -> list[Path]:
    standard_skill_assets = {
        "SKILL.md",
        "agents",
        "assets",
        "references",
        "scripts",
        "LICENSE",
        "LICENSE.md",
        "NOTICE",
    }
    nested_skill_children = {
        path.relative_to(skill_dir).parts[0]
        for path in skill_dir.rglob("SKILL.md")
        if path.parent != skill_dir
    }
    assets: list[Path] = []
    for path in skill_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".sh", ".yaml", ".yml"}:
            continue
        relative = path.relative_to(skill_dir)
        if relative.parts[0] in nested_skill_children:
            continue
        if nested_skill_children and relative.parts[0] not in standard_skill_assets:
            continue
        if relative.parts[:2] == ("scripts", "hsd17b13_reference"):
            continue
        assets.append(path)
    return sorted(assets)


def audit_skills(*, check_scripts: bool = False) -> list[str]:
    errors: list[str] = []
    skill_dirs = _active_skill_dirs()
    active_paths = {path.resolve() for path in skill_dirs}
    catalog_names = _catalog_names()
    counts = Counter(catalog_names)

    for name, count in sorted(counts.items()):
        if count != 1:
            errors.append(f"catalog: {name!r} occurs {count} times")
    catalog_paths = {
        path.resolve()
        for _master, _name, path in CANONICAL_SKILLS
        if (path / "SKILL.md").is_file()
    }
    if catalog_paths != active_paths:
        missing = sorted(str(path) for path in active_paths - catalog_paths)
        extra = sorted(str(path) for path in catalog_paths - active_paths)
        errors.append(f"catalog mismatch: unlisted={missing}, missing_directories={extra}")

    for alias, expected in sorted(_compatibility_aliases().items()):
        alias_path = PROJECT_SKILLS / alias
        if not alias_path.is_symlink():
            errors.append(f"compatibility alias missing symlink: {alias_path.relative_to(ROOT)}")
        elif alias_path.resolve() != expected.resolve():
            errors.append(
                f"compatibility alias target mismatch: {alias_path.relative_to(ROOT)} "
                f"-> {alias_path.resolve().relative_to(ROOT)}; expected {expected.relative_to(ROOT)}"
            )

    for skill_dir in skill_dirs:
        skill_path = skill_dir / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        relative = skill_path.relative_to(ROOT)
        try:
            metadata = _frontmatter(skill_path)
        except (ValueError, yaml.YAMLError) as exc:
            errors.append(f"{relative}: {exc}")
            continue

        keys = set(metadata)
        if keys != FRONTMATTER_KEYS:
            errors.append(
                f"{relative}: frontmatter keys must be {sorted(FRONTMATTER_KEYS)}, got {sorted(keys)}"
            )
        if metadata.get("name") != skill_dir.name:
            errors.append(f"{relative}: name must equal directory {skill_dir.name!r}")
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{relative}: description must be non-empty text")
        elif not re.search(r"\b(?:use|invoke)\b", description, flags=re.IGNORECASE):
            errors.append(f"{relative}: description must state when to use the skill")
        if len(text.splitlines()) > 500:
            errors.append(f"{relative}: SKILL.md exceeds 500 lines")
        for asset_path in _portable_text_assets(skill_dir):
            asset_text = asset_path.read_text(encoding="utf-8")
            portable_path_text = URL_PATTERN.sub("", asset_text)
            asset_relative = asset_path.relative_to(ROOT)
            for match in HOST_PATH_PATTERN.finditer(portable_path_text):
                errors.append(f"{asset_relative}: host-specific path {match.group(0)!r}")
            if "/opt/schrodinger" in asset_text.lower():
                errors.append(f"{asset_relative}: hard-coded Schrödinger installation path")
            if "hsv-" in asset_text.lower():
                errors.append(f"{asset_relative}: excluded nested workflow reference")
            if re.search(r'[=:]\s*["\']res\.ptype UNK["\']', asset_text):
                errors.append(f"{asset_relative}: hard-coded ligand ASL default")

        for target in LINK_PATTERN.findall(text):
            target = target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            resolved = (skill_dir / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                errors.append(f"{relative}: broken local link {target!r}")

        metadata_path = skill_dir / "agents" / "openai.yaml"
        if metadata_path.exists():
            try:
                agent_data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
                interface = agent_data["interface"]
                for key in ("display_name", "short_description", "default_prompt"):
                    if not isinstance(interface.get(key), str) or not interface[key].strip():
                        errors.append(f"{metadata_path.relative_to(ROOT)}: missing {key}")
            except (KeyError, TypeError, yaml.YAMLError) as exc:
                errors.append(f"{metadata_path.relative_to(ROOT)}: invalid metadata ({exc})")

        if check_scripts:
            for python_path in sorted(skill_dir.rglob("*.py")):
                try:
                    compile(
                        python_path.read_text(encoding="utf-8"),
                        str(python_path),
                        "exec",
                    )
                except (OSError, SyntaxError, UnicodeError) as exc:
                    errors.append(f"{python_path.relative_to(ROOT)}: Python compile failed ({exc})")
            for shell_path in sorted(skill_dir.rglob("*.sh")):
                result = subprocess.run(
                    ["bash", "-n", str(shell_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode:
                    errors.append(
                        f"{shell_path.relative_to(ROOT)}: bash -n failed ({result.stderr.strip()})"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-scripts", action="store_true")
    args = parser.parse_args()
    errors = audit_skills(check_scripts=args.check_scripts)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"OK: {len(MASTER_CATEGORIES)} master skills and "
        f"{sum(len(children) for children in MASTER_CATEGORIES.values())} child skills passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
