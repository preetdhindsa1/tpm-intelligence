"""Fixture loading for collector tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "github"


def load_json(name: str) -> Any:
    """Load a JSON fixture from tests/fixtures/github/."""
    return json.loads((FIXTURES / name).read_text())


def load_text(name: str) -> str:
    """Load a text fixture from tests/fixtures/github/."""
    return (FIXTURES / name).read_text()
