"""The tenant context (pipeline/store/tenancy.py, ADR-0034): pure parts, no database."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from pipeline.store.tenancy import (
    DEMO,
    carry,
    cli_tenant,
    current_tenant,
    in_tenant,
    use_tenant,
    valid,
)


def test_tests_run_for_the_demo() -> None:
    assert current_tenant.get() == DEMO


def test_use_tenant_nests_and_restores() -> None:
    with use_tenant("acme"):
        assert current_tenant.get() == "acme"
        with use_tenant("globex"):
            assert current_tenant.get() == "globex"
        assert current_tenant.get() == "acme"
    assert current_tenant.get() == DEMO


@pytest.mark.parametrize("bad", ["", "A", "acme corp", "-acme", "a" * 33, "acme;drop"])
def test_tenant_ids_are_slugs(bad: str) -> None:
    with pytest.raises(ValueError, match="not a tenant id"):
        valid(bad)


def test_a_plain_thread_loses_the_tenant_and_in_tenant_restores_it() -> None:
    seen: dict[str, str | None] = {}
    with use_tenant("acme"):
        t = threading.Thread(target=lambda: seen.update(plain=current_tenant.get()))
        t.start()
        t.join()
        t = threading.Thread(
            target=in_tenant("acme", lambda: seen.update(wrapped=current_tenant.get()))
        )
        t.start()
        t.join()
    assert seen == {"plain": None, "wrapped": "acme"}


def test_carry_keeps_the_callers_tenant_in_a_pool_and_none_stays_none() -> None:
    with use_tenant("acme"), ThreadPoolExecutor(2) as pool:
        assert set(pool.map(carry(lambda _: current_tenant.get()), range(4))) == {"acme"}
    token = current_tenant.set(None)
    try:
        with ThreadPoolExecutor(1) as pool:
            assert list(pool.map(carry(lambda _: current_tenant.get()), [0])) == [None]
    finally:
        current_tenant.reset(token)


def test_cli_tenant_defaults_to_the_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TPM_TENANT", raising=False)
    assert cli_tenant() == DEMO
    monkeypatch.setenv("TPM_TENANT", "acme")
    assert cli_tenant() == "acme"
    monkeypatch.setenv("TPM_TENANT", "Not valid")
    with pytest.raises(ValueError, match="not a tenant id"):
        cli_tenant()
