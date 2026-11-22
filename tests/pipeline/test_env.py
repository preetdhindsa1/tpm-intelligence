"""Deploy placeholders count as unset (pipeline/env.py, ADR-0017)."""

from __future__ import annotations

import pytest

from pipeline.env import configured


@pytest.mark.parametrize("value", ["", "  ", "unconfigured"])
def test_placeholder_and_empty_are_unset(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SOME_SECRET", value)
    assert configured("SOME_SECRET") is None


def test_real_value_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_SECRET", "abc")
    assert configured("SOME_SECRET") == "abc"
    monkeypatch.delenv("SOME_SECRET")
    assert configured("SOME_SECRET") is None


def test_unconfigured_anthropic_key_is_an_ai_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.gateway import AIError, default_client
    from agents.settings import AISettings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "unconfigured")
    with pytest.raises(AIError, match="not configured"):
        default_client(AISettings())
