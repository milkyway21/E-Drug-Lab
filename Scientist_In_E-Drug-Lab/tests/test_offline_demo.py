import json
from pathlib import Path

import jsonschema

from masld_agent.config import PKG_ROOT
from masld_agent.supervisor import run_offline_demo


def test_offline_hsd17b13_demo(tmp_path: Path):
    fixture = PKG_ROOT / "tests" / "fixtures" / "hsd17b13"
    out = run_offline_demo(fixture, tmp_path)
    required = [
        "manifest.json",
        "config_snapshot.yaml",
        "events.jsonl",
        "evidence.json",
        "targets_ranked.csv",
        "structures.json",
        "ligands.csv",
        "proposal.md",
        "method.md",
        "machine_readable_report.json",
        "warnings.md",
    ]
    for name in required:
        assert (out / name).exists(), name

    report = json.loads((out / "machine_readable_report.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (PKG_ROOT / "schemas" / "machine_readable_report.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(report, schema)
    assert "competition_scope_warning" in report["competition_scope_warning"]

    # Unverified evidence must not appear
    evidence = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    titles = [e.get("title") for e in evidence.get("HSD17B13", [])]
    assert not any(t and "Unverified placeholder" in t for t in titles)

    # Reload manifest
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["offline"] is True
    assert manifest["hermes_eval_mode"] is True
