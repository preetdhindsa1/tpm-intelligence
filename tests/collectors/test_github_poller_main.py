"""The poller entrypoint: one or several (team, release) polls per run."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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


seen_since: list[datetime | None] = []


@pytest.fixture
def polled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Replace the real poll with a recorder whose result depends on the team."""
    calls: list[tuple[str, str]] = []
    seen_since.clear()
    results = {"ok": 0, "stream-failed": 1, "misconfigured": 2}

    def fake_poll(
        team_id: str, release: str, *, token: str, backfill: bool, since: datetime | None = None
    ) -> int:
        calls.append((team_id, release))
        seen_since.append(since)
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


def test_only_the_kep_link_pack_reads_kep_specs() -> None:
    """Issue #11: Kubernetes plans with kep.yaml; this project and others do not."""
    from connectors import load_team

    assert load_team("kubernetes").link_pack == "kep"
    assert load_team("tpm-intelligence").link_pack != "kep"


def test_since_reads_history_before_the_cycle_start(polled: list[tuple[str, str]]) -> None:
    """2026-11-25: this repo's PRs predate Phase 3, so a plain backfill re-read none."""
    assert entry.main(["--poll", "ok=r1", "--backfill", "--since", "2026-11-20"]) == 0
    assert seen_since == [datetime(2026, 11, 20, tzinfo=UTC)]


@pytest.mark.parametrize("argv", [["--since", "2026-11-20"], ["--backfill", "--since", "20 Nov"]])
def test_since_needs_backfill_and_a_date(polled: list[tuple[str, str]], argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        entry.main(["--poll", "ok=r1", *argv])
    assert exc.value.code == 2
    assert polled == []


def test_current_release_is_the_running_cycle() -> None:
    from collectors.github_poller.calendar import Calendar, ReleaseDates

    def rel(name: str, start: int, ship: int) -> ReleaseDates:
        return ReleaseDates(name=name, cycle_start=datetime(2027, start, 1, tzinfo=UTC),
                            enhancements_freeze=datetime(2027, start, 10, tzinfo=UTC),
                            code_freeze=datetime(2027, start, 20, tzinfo=UTC),
                            release=datetime(2027, ship, 1, tzinfo=UTC), source_url="")  # fmt: skip

    cal = Calendar(project="acme", releases=(rel("1", 1, 3), rel("2", 3, 5)))
    assert entry.current_release(cal, datetime(2027, 2, 1, tzinfo=UTC)) == "1"
    assert entry.current_release(cal, datetime(2027, 3, 5, tzinfo=UTC)) == "2"  # newest wins
    assert entry.current_release(cal, datetime(2026, 6, 1, tzinfo=UTC)) is None


def test_all_tenants_takes_no_explicit_polls() -> None:
    with pytest.raises(SystemExit) as exc:
        entry.main(["--all-tenants", "--poll", "kubernetes=v1.38"])
    assert exc.value.code == 2


def test_all_tenants_polls_each_team_under_its_own_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from connectors.load import set_team_source
    from connectors.schema import TeamConfig
    from pipeline.store.tenancy import current_tenant
    from tests.api.test_connectors_api import WEB
    from tests.connectors.test_tenant_teams import INLINE

    team = TeamConfig.model_validate({**WEB, "calendar": INLINE})
    set_team_source(lambda t: {team.id: team} if t in ("acme", "globex") else {})
    monkeypatch.setattr(entry, "private_tenants", lambda: ["acme", "globex"])
    monkeypatch.setenv("TENANT_ACME_GITHUB_TOKEN", "a-token")  # globex has none: skipped
    seen: list[tuple[str | None, str, str]] = []

    def fake(team_id: str, release: str, *, token: str, backfill: bool, **_: Any) -> int:
        seen.append((current_tenant.get(), release, token))
        return 0

    monkeypatch.setattr(entry, "_poll_team", fake)
    try:
        code = entry._poll_all_tenants(backfill=False, now=datetime(2027, 2, 1, tzinfo=UTC))
    finally:
        set_team_source(None)
    assert code == 0
    assert seen == [("acme", "2027.1", "a-token")]
