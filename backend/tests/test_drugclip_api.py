"""DrugCLIP HTTP route smoke tests (no Docker required)."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("database__url", "sqlite:///./test_drugclip_api.db")

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_drugclip_status(client):
    resp = client.get("/api/v1/drugclip/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "package_path" in data
    assert "service_url" in data
    assert data.get("package_exists") is True


def test_drugclip_service_health(client):
    resp = client.get("/api/v1/drugclip/service/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data
    assert "url" in data
