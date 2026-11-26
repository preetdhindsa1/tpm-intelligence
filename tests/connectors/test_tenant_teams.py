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
