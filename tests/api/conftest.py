"""API tests act as the local developer unless a test sets up sign-in itself (ADR-0016)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def local_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "local")
