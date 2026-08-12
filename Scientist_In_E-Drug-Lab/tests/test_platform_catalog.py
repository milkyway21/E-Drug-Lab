"""Catalog completeness for DiffDynamic / e-drug-lab / Schrödinger."""
from __future__ import annotations

from masld_agent.platform.catalog import (
    REQUIRED_IDS,
    get_entry,
    list_entries,
    load_catalog,
    resolve_entry,
    summarize_systems,
)


def test_catalog_loads():
    cat = load_catalog()
    assert cat.get("entries")
    assert len(cat["entries"]) >= len(REQUIRED_IDS)


def test_required_ids_present():
    missing = [i for i in REQUIRED_IDS if get_entry(i) is None]
    assert missing == [], f"missing catalog ids: {missing}"


def test_three_systems():
    summary = summarize_systems()
    assert summary["by_system"].get("dd", 0) >= 10
    assert summary["by_system"].get("ed", 0) >= 8
    assert summary["by_system"].get("sz", 0) >= 10
    assert summary["missing_required_ids"] == []


def test_filter_by_system():
    dd = list_entries(system="dd")
    ed = list_entries(system="ed")
    sz = list_entries(system="sz")
    assert all(e["system"] == "dd" for e in dd)
    assert all(e["system"] == "ed" for e in ed)
    assert all(e["system"] == "sz" for e in sz)
    assert get_entry("ed.integrations.stub")["risks"]


def test_resolve_entry_uses_runtime_environment(monkeypatch):
    monkeypatch.setenv("SCHRODINGER", "/runtime/schrodinger")
    monkeypatch.setenv("MASLD_DIFFDYNAMIC_ROOT", "/runtime/diffdynamic")

    assert resolve_entry("sz.bin.glide") == "/runtime/schrodinger/glide"
    assert resolve_entry("dd.script.sample") == (
        "/runtime/diffdynamic/scripts/sample_diffusion.py"
    )


def test_resolve_entry_uses_registered_defaults(monkeypatch):
    monkeypatch.delenv("SCHRODINGER", raising=False)
    monkeypatch.delenv("MASLD_SCHRODINGER", raising=False)
    monkeypatch.delenv("MASLD_DIFFDYNAMIC_ROOT", raising=False)
    monkeypatch.delenv("MASLD_DIFFDYNAMIC_CONDA", raising=False)
    monkeypatch.delenv("MASLD_DIFFDYNAMIC_CONDA_NAME", raising=False)

    assert resolve_entry("sz.bin.glide") == "/opt/schrodinger2023-3/glide"
    assert resolve_entry("dd.script.sample") == "/data/ye/DiffDynamic/scripts/sample_diffusion.py"
