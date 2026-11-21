"""API health endpoint responds and is traced."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def test_healthz_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
