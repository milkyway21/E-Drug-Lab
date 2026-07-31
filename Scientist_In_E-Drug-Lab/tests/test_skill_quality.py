"""Quality gates for the directly imported project skills."""
from __future__ import annotations

import importlib.util
import csv
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
AUDIT_PATH = ROOT / "scripts" / "audit_skills.py"
SPEC = importlib.util.spec_from_file_location("audit_skills", AUDIT_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_top_level_skills_pass_quality_gate():
    assert AUDIT.audit_skills() == []


def test_catalog_sources_are_direct_children():
    for name in AUDIT._catalog_names():
        assert (AUDIT.PROJECT_SKILLS / name / "SKILL.md").is_file()


def test_skill_link_excludes_nested_skill_trees(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("---\nname: source\ndescription: Use source.\n---\n")
    references = source / "references"
    references.mkdir()
    (references / "guide.md").write_text("keep\n")
    (source / "legacy_workflow.md").write_text("exclude\n")
    nested = source / "nested-stage"
    nested.mkdir()
    (nested / "SKILL.md").write_text("---\nname: nested-stage\ndescription: Use nested.\n---\n")

    destination = tmp_path / "installed" / "source"
    action = AUDIT.IMPORTER._link_skill(source, destination, mode="symlink")

    assert action == "symlinked-filtered"
    assert (destination / "SKILL.md").is_file()
    assert (destination / "references" / "guide.md").is_file()
    assert not (destination / "legacy_workflow.md").exists()
    assert not (destination / "nested-stage").exists()


def _run_rdkit_script(script_name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills" / "rdkit" / "scripts" / script_name),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_rdkit_bundled_clis_execute_representative_workflows(tmp_path):
    molecules = tmp_path / "molecules.smi"
    molecules.write_text("CCO zeta\nCCO alpha\nc1ccccc1 benzene\n", encoding="utf-8")

    properties = tmp_path / "properties.csv"
    _run_rdkit_script(
        "molecular_properties.py",
        "--file",
        str(molecules),
        "--output",
        str(properties),
    )
    with properties.open(encoding="utf-8", newline="") as stream:
        property_rows = list(csv.DictReader(stream))
    assert len(property_rows) == 3
    assert all(row["Fraction_Csp3"] for row in property_rows)

    similarity = tmp_path / "similarity.csv"
    _run_rdkit_script(
        "similarity_search.py",
        "CCO",
        str(molecules),
        "--threshold",
        "0",
        "--output",
        str(similarity),
    )
    with similarity.open(encoding="utf-8", newline="") as stream:
        similarity_rows = list(csv.DictReader(stream))
    assert [row["Name"] for row in similarity_rows[:2]] == ["alpha", "zeta"]

    filtered = tmp_path / "filtered.smi"
    report = tmp_path / "filter.csv"
    _run_rdkit_script(
        "substructure_filter.py",
        str(molecules),
        "--pattern",
        "c1ccccc1",
        "--output",
        str(filtered),
        "--report",
        str(report),
    )
    assert filtered.read_text(encoding="utf-8").strip().endswith("benzene")
    with report.open(encoding="utf-8", newline="") as stream:
        report_rows = list(csv.DictReader(stream))
    assert sum(row["Status"] == "included" for row in report_rows) == 1
