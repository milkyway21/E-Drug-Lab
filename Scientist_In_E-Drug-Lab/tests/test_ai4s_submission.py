"""Tests for AI4S submission helpers (identity/SOUL untouched)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from masld_agent.submission import (
    export_top10_template,
    pack_submission,
    validate_submission,
    write_hepg2_plan,
)
from masld_agent.tools.ai4s_brief import format_competition_brief, lint_dual_readout, load_ai4s_config


def test_soul_identity_unchanged():
    soul = Path(__file__).resolve().parents[1] / "config" / "SOUL.md"
    text = soul.read_text(encoding="utf-8")
    assert "across diseases" in text or "not only MASLD" in text
    assert "MASLD target-discovery research assistant" not in text


def test_competition_brief_has_scoring_and_dual_readout():
    text = format_competition_brief(load_ai4s_config())
    assert "60" in text
    assert "20" in text
    assert "脂质" in text or "lipid" in text.lower()
    assert "活力" in text or "viability" in text.lower()
    assert "OriGene" in text or "origene" in text.lower()


def test_dual_readout_lint_missing_viability():
    bad = "该分子可显著降脂并减少脂滴信号。"
    r = lint_dual_readout(bad)
    assert r["ok"] is False
    assert "cell_viability" in r["missing"]


def test_dual_readout_lint_ok():
    good = "降脂同时监测细胞活力；排除细胞毒性导致的脂滴假阳性。"
    r = lint_dual_readout(good)
    assert r["ok"] is True


def test_export_top10_template(tmp_path: Path):
    out = tmp_path / "top10.csv"
    export_top10_template(out)
    text = out.read_text(encoding="utf-8")
    assert "lipid_rationale" in text
    assert "tox_rationale" in text
    assert "PENDING_01" in text


def test_validate_and_pack_marks_pending(tmp_path: Path):
    # Minimal run dir
    run = tmp_path / "run"
    run.mkdir()
    (run / "proposal.md").write_text(
        "机制假说。降脂与细胞活力双读出需同时评估。\n",
        encoding="utf-8",
    )
    (run / "method.md").write_text(
        "可复现方法。HepG2-FFA lipid + viability.\n",
        encoding="utf-8",
    )
    (run / "machine_readable_report.json").write_text("{}", encoding="utf-8")
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    (run / "targets_ranked.csv").write_text(
        "rank,gene_symbol,uniprot_id,novelty_class,score_total,missing_dimensions\n"
        "1,HSD17B13,Q7Z5P4,emerging_target,0.5,\n",
        encoding="utf-8",
    )

    result = validate_submission(run)
    assert "pending_library_nomination" in result["status_flags"]
    assert result["ok"] is False  # top10 not filled

    zpath = tmp_path / "bundle.zip"
    pack_submission(run, zpath)
    assert zpath.is_file()
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
    assert "proposal.md" in names
    assert any(n.endswith("SUBMISSION_CHECKLIST.md") for n in names)
    assert (run / "hepg2_validation_plan.md").is_file()
    assert (run / "submission" / "README_AI4S.md").is_file()


def test_hepg2_plan_mentions_dual_readout(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    path = write_hepg2_plan(run)
    text = path.read_text(encoding="utf-8")
    assert "活力" in text
    assert "脂质" in text or "降脂" in text
