"""Team configs and secrets per tenant (ADR-0035, #233)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from connectors.load import load_teams, set_team_source
from connectors.schema import TeamConfig
from connectors.secrets import env_name, resolve, secret_name
from pipeline.store.tenancy import current_tenant, use_tenant
from tests.api.test_connectors_api import WEB


@pytest.fixture
def acme_teams() -> Iterator[None]:
    config = TeamConfig.model_validate(WEB)
    set_team_source(lambda t: {config.id: config} if t == "acme" else {})
    yield
    set_team_source(None)


def test_the_demo_reads_yaml_and_a_tenant_reads_its_own(acme_teams: None) -> None:
    assert {"kubernetes", "kafka"} <= set(load_teams())  # tests run for the demo
    with use_tenant("acme"):
        assert set(load_teams()) == {"acme-web"}
    with use_tenant("globex"):
        assert load_teams() == {}


def test_no_tenant_refuses_rather_than_guess() -> None:
    token = current_tenant.set(None)
    try:
        with pytest.raises(RuntimeError, match="no tenant"):
            load_teams()
    finally:
        current_tenant.reset(token)


def test_secret_names_and_env_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    assert secret_name("acme", "github-token") == "tenant-acme-github-token"
    assert env_name("acme", "github-token") == "TENANT_ACME_GITHUB_TOKEN"
    monkeypatch.delenv("TENANT_ACME_GITHUB_TOKEN", raising=False)
    assert resolve("acme", "github-token") is None
    monkeypatch.setenv("TENANT_ACME_GITHUB_TOKEN", "t0k")
    assert resolve("acme", "github-token") == "t0k"
    assert resolve("globex", "github-token") is None  # never another tenant's
    with pytest.raises(ValueError, match="not a secret reference"):
        secret_name("acme", "Bad Ref")
    with pytest.raises(ValueError, match="demo"):
        resolve("demo", "github-token")


def test_the_gcp_backend_uses_the_tenant_secret_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "gcp")
    asked: list[str] = []
    assert resolve("acme", "jira-token", gcp=lambda n: asked.append(n) or "v") == "v"
    assert asked == ["tenant-acme-jira-token"]


def test_a_secret_value_cannot_be_stored_as_a_ref() -> None:
    with pytest.raises(ValueError, match="not a secret name"):
        TeamConfig.model_validate({**WEB, "secret_refs": {"github": "ghp_" + "a" * 36}})


def test_team_secret_is_the_demo_env_or_the_tenants_ref(
    acme_teams: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from connectors.secrets import team_secret

    monkeypatch.setenv("GITHUB_TOKEN", "demo-token")
    monkeypatch.setenv("TENANT_ACME_GITHUB_TOKEN", "acme-token")
    k8s = load_teams()["kubernetes"]
    assert team_secret(k8s, "github", "GITHUB_TOKEN") == "demo-token"
    with use_tenant("acme"):
        web = load_teams()["acme-web"]
        assert team_secret(web, "github", "GITHUB_TOKEN") == "acme-token"
        assert team_secret(web, "jira", "JIRA_TOKEN") is None  # no ref: no demo fallback


INLINE = {"releases": [{"name": "2027.1", "cycle_start": "2027-01-04T00:00:00Z",
                        "enhancements_freeze": "2027-01-18T12:00:00Z",
                        "code_freeze": "2027-02-15T12:00:00Z",
                        "release": "2027-02-22T00:00:00Z"}]}  # fmt: skip


def test_a_tenant_writes_its_release_dates_in_the_config() -> None:
    from connectors.load import release_plan, team_calendar

    team = TeamConfig.model_validate({**WEB, "calendar": INLINE})
    calendar = team_calendar(team)
    assert calendar is not None
    assert calendar.project == "acme-web"
    assert calendar.get("2027.1").code_freeze.isoformat() == "2027-02-15T12:00:00+00:00"
    assert set(release_plan(team)) == {"2027.1"}


@pytest.mark.parametrize(
    "calendar",
    [
        {},  # neither
        {"path": "x.yaml", **INLINE},  # both
        {"releases": [{**INLINE["releases"][0], "code_freeze": "2026-01-01T00:00:00Z"}]},
    ],
)
def test_a_calendar_needs_one_source_and_ordered_dates(calendar: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"calendar needs exactly one|out of order"):
        TeamConfig.model_validate({**WEB, "calendar": calendar})


def test_the_demo_calendars_are_still_files() -> None:
    from connectors.load import team_calendar

    k8s = team_calendar(load_teams()["kubernetes"])
    assert k8s is not None
    assert "v1.38" in {r.name for r in k8s.releases}
