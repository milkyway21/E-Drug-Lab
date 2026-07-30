"""Path safety and review-regression tests."""
from pathlib import Path

import pytest

from masld_agent.hermes_plugin import _run_offline
from masld_agent.paths import UnsafePathError, resolve_under
from masld_agent.tools.docking import run_docking
from masld_agent.tools.literature import search_pubmed_esearch


def test_resolve_under_blocks_traversal(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "ok").mkdir()
    with pytest.raises(UnsafePathError):
        resolve_under(root, "../etc/passwd", default=root / "ok")


def test_resolve_under_allows_relative(tmp_path: Path):
    root = tmp_path / "proj"
    (root / "runs").mkdir(parents=True)
    p = resolve_under(root, "runs", default=root / "runs")
    assert p == (root / "runs").resolve()


def test_hermes_offline_rejects_escape():
    raw = _run_offline({"fixture": "/etc", "output": "runs"})
    assert '"status": "error"' in raw or '"status":"error"' in raw.replace(" ", "")


def test_pubmed_esearch_not_verified_without_title(monkeypatch):
    class FakeHttp:
        def get_json(self, url, params=None, headers=None, use_cache=True):
            return {"esearchresult": {"idlist": ["28112690"]}}

    rows = search_pubmed_esearch("HSD17B13", http=FakeHttp())  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0].verified is False
    assert rows[0].title is None
    assert "unverified" in rows[0].warnings[0]


def test_docking_status_when_inputs_partial(monkeypatch):
    monkeypatch.setattr("masld_agent.tools.docking.vina_available", lambda: True)
    d = run_docking(
        receptor_pdbqt="/tmp/r.pdbqt",
        ligand_pdbqt="/tmp/l.pdbqt",
        center=(1.0, 2.0, 3.0),
        crystal_ligand_pdbqt=None,
    )
    assert d.status == "skipped_incomplete_integration"
    assert d.score is None


def test_docking_skip_without_vina():
    d = run_docking()
    assert d.status in {"skipped_missing_dependency", "failed", "skipped_incomplete_integration"}
    assert d.score is None
