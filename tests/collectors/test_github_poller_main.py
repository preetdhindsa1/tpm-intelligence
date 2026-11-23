"""The poller entrypoint: one or several (team, release) polls per run."""

from __future__ import annotations

import pytest

from collectors.github_poller import __main__ as entry


def test_single_team_style_defaults_to_kubernetes() -> None:
    assert entry.parse_polls(None, None, "v1.38") == [("kubernetes", "v1.38")]
    assert entry.parse_polls(None, "kafka", "4.4.0") == [("kafka", "4.4.0")]


def test_repeated_poll_pairs_keep_order_and_spaces_in_release() -> None:
    pairs = entry.parse_polls(["kubernetes=v1.38", "tpm-intelligence=Phase 3"], None, None)
    assert pairs == [("kubernetes", "v1.38"), ("tpm-intelligence", "Phase 3")]


@pytest.mark.parametrize("bad", ["kubernetes", "=v1.38", "kubernetes=", "kubernetes= "])
def test_malformed_poll_pair_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="TEAM=RELEASE"):
        entry.parse_polls([bad], None, None)


def test_mixing_styles_or_missing_release_is_rejected() -> None:
    with pytest.raises(ValueError, match="not both"):
        entry.parse_polls(["kubernetes=v1.38"], None, "v1.38")
    with pytest.raises(ValueError, match="required"):
        entry.parse_polls(None, "kubernetes", None)


def test_bad_arguments_exit_with_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        entry.main(["--poll", "kubernetes"])
    assert exc.value.code == 2


@pytest.fixture
def polled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Replace the real poll with a recorder whose result depends on the team."""
    calls: list[tuple[str, str]] = []
    results = {"ok": 0, "stream-failed": 1, "misconfigured": 2}

    def fake_poll(team_id: str, release: str, *, token: str, backfill: bool) -> int:
        calls.append((team_id, release))
        if team_id == "crashes":
            raise RuntimeError("boom")
        return results[team_id]

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setattr(entry, "_poll_team", fake_poll)
    return calls


def test_every_team_is_polled_even_after_a_failure(polled: list[tuple[str, str]]) -> None:
    code = entry.main(["--poll", "crashes=r1", "--poll", "stream-failed=r2", "--poll", "ok=r3"])
    assert polled == [("crashes", "r1"), ("stream-failed", "r2"), ("ok", "r3")]
    assert code == 1


def test_worst_exit_code_wins(polled: list[tuple[str, str]]) -> None:
    assert entry.main(["--poll", "ok=r1", "--poll", "ok=r2"]) == 0
    assert entry.main(["--poll", "misconfigured=r1", "--poll", "stream-failed=r2"]) == 2


def test_missing_token_stops_before_polling(
    polled: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN")
    assert entry.main(["--poll", "ok=r1"]) == 2
    assert polled == []
