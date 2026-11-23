"""API health endpoint responds and is traced."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def test_healthz_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_alias_for_cloud_run() -> None:
    """Cloud Run answers a public /healthz itself with 404 (paths ending in z are reserved)."""
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
