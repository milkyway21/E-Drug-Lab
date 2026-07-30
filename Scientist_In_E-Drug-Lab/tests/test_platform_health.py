"""Platform health probes (real host when available)."""
from __future__ import annotations

from masld_agent.platform.health import (
    check_diffdynamic,
    check_edrug,
    check_schrodinger,
    platform_health,
)


def test_platform_health_shape():
    h = platform_health()
    assert h["status"] in {"ok", "degraded"}
    assert set(h["systems"]) == {"dd", "ed", "sz"}
    for sys in ("dd", "ed", "sz"):
        assert "ok" in h["systems"][sys]
        assert "details" in h["systems"][sys]
        assert "catalog_ids" in h["systems"][sys]


def test_diffdynamic_probe_has_paths():
    dd = check_diffdynamic()
    assert "root" in dd["details"]
    assert "conda" in dd["details"]


def test_edrug_probe_mentions_stub():
    ed = check_edrug()
    assert "integrations_stub_note" in ed["details"]


def test_schrodinger_probe_home():
    sz = check_schrodinger()
    assert "SCHRODINGER" in sz["details"]
