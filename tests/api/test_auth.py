"""Sign-in and permissions (api/auth.py, ADR-0016).

Actions need a request signed by the web app for an allowlisted GitHub login. Reading
stays public. Anonymous visitors never trigger paid AI.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.auth import AuthConfig, signature
from api.main import create_app
from api.service import InMemoryEventSource, ReleaseService
from api.validation import Validation
from engine.forecast import ForecastConfig
from tests.engine.conftest import fixture_events, utc

SECRET = b"test-secret"
REQUIRED = AuthConfig("required", SECRET, frozenset({"preetdhindsa1"}))
FAST = ForecastConfig(replications=5, sims=100)

# Every endpoint that changes data or spends money (ADR-0016), with a minimal body.
ACTIONS: list[tuple[str, str, Any]] = [
    ("POST", "/releases/v1.38/updates", None),
    ("PATCH", "/releases/v1.38/updates/1", {"sections": {}}),
    ("POST", "/releases/v1.38/updates/1/approve", {}),
    ("POST", "/releases/v1.38/updates/1/reject", {}),
    ("POST", "/releases/v1.38/link-suggestions/1/confirm", {}),
    ("POST", "/releases/v1.38/link-suggestions/1/reject", {}),
    ("POST", "/releases/v1.38/scenarios", {"name": "x", "pools": {}}),
    ("POST", "/raid/4/confirm", {}),
    ("POST", "/raid/4/edit", {"owner": "SIG Node"}),
    ("POST", "/raid/4/reject", {"reason": "not a risk"}),
]


def service(now: Any = None) -> ReleaseService:
    return ReleaseService(
        InMemoryEventSource(list(fixture_events())),
        forecast=FAST,
        now=lambda: now or utc(2026, 11, 21, 3),
        validation=lambda: Validation(False, "test"),
        date_validation=lambda: Validation(False, "test"),
    )


def signed(
    user: str, method: str, path: str, body: bytes = b"", *, age: int = 0, secret: bytes = SECRET
) -> dict[str, str]:
    ts = str(int(time.time()) - age)
    return {
        "x-tpm-user": user,
        "x-tpm-time": ts,
        "x-tpm-signature": signature(secret, user, ts, method, path, body),
        "content-type": "application/json",
    }


@pytest.fixture(scope="module")
def api() -> TestClient:
    from agents.link_store import MemoryLinkSuggestionStore
    from api.sim_store import MemorySimStore

    # In-memory stores: a request that passes auth must never reach the real database.
    return TestClient(
        create_app(
            service=service(),
            auth=REQUIRED,
            link_store=MemoryLinkSuggestionStore(),
            sim_store=MemorySimStore(),
        )
    )


def _send(api: TestClient, method: str, path: str, body: Any, headers: dict[str, str]) -> int:
    import json

    raw = b"" if body is None else json.dumps(body).encode()
    return api.request(method, path, content=raw, headers=headers).status_code


@pytest.mark.parametrize(("method", "path", "body"), ACTIONS)
def test_every_action_refuses_anonymous_requests(
    api: TestClient, method: str, path: str, body: Any
) -> None:
    assert _send(api, method, path, body, {"content-type": "application/json"}) == 401


@pytest.mark.parametrize(("method", "path", "body"), ACTIONS)
def test_every_action_refuses_a_signed_in_non_approver(
    api: TestClient, method: str, path: str, body: Any
) -> None:
    import json

    raw = b"" if body is None else json.dumps(body).encode()
    assert _send(api, method, path, body, signed("someone-else", method, path, raw)) == 403


def test_bad_expired_or_replayed_signatures_are_refused(api: TestClient) -> None:
    path = "/releases/v1.38/link-suggestions/1/confirm"
    body = b"{}"
    ok = signed("preetdhindsa1", "POST", path, body)
    wrong_secret = signed("preetdhindsa1", "POST", path, body, secret=b"other")
    expired = signed("preetdhindsa1", "POST", path, body, age=301)
    other_path = signed("preetdhindsa1", "POST", "/releases/v1.38/link-suggestions/2/confirm", body)
    for headers in (wrong_secret, expired, other_path):
        assert api.post(path, content=body, headers=headers).status_code == 401
    # Same signature, different body: refused (the body is signed too).
    assert api.post(path, content=b'{"note": "x"}', headers=ok).status_code == 401
    # The real one gets past auth (404: no such suggestion in this test).
    assert api.post(path, content=body, headers=ok).status_code == 404


def test_reading_stays_public(api: TestClient) -> None:
    assert api.get("/releases").status_code == 200
    assert api.get("/releases/v1.38/features").status_code == 200
    assert api.post("/releases/v1.38/simulate", json={"pools": {}}).status_code != 401


def test_no_secret_configured_fails_closed() -> None:
    client = TestClient(
        create_app(service=service(), auth=AuthConfig("required", None, frozenset({"a"})))
    )
    assert client.post("/releases/v1.38/updates").status_code == 401
    headers = signed("a", "POST", "/releases/v1.38/updates")
    assert client.post("/releases/v1.38/updates", headers=headers).status_code == 401


def test_me_says_who_is_acting(api: TestClient) -> None:
    assert api.get("/me").json() == {
        "login": None,
        "signed_in": False,
        "approver": False,
        "mode": "required",
    }
    me = api.get("/me", headers=signed("PreetDhindsa1", "GET", "/me")).json()
    assert me == {"login": "preetdhindsa1", "signed_in": True, "approver": True, "mode": "required"}


def test_approval_records_the_signed_in_login() -> None:
    import json

    from agents.gateway import Gateway
    from agents.ledger import MemoryLedger
    from agents.notes import MemoryNoteStore
    from agents.settings import AISettings
    from agents.updates import MemoryUpdateStore
    from api.ai import AIServices
    from tests.agents.test_gateway import FakeClient, Response
    from tests.agents.test_vp_summary import OUTPUT

    ai = AIServices(
        gateway=Gateway(
            AISettings(),
            MemoryLedger(),
            FakeClient(Response(parsed_output=OUTPUT, model="claude-opus-5-5")),
        ),
        notes=MemoryNoteStore(),
        updates=MemoryUpdateStore(),
    )
    client = TestClient(create_app(service=service(), ai=ai, auth=REQUIRED))
    path = "/releases/v1.38/updates"
    created = client.post(path, headers=signed("preetdhindsa1", "POST", path))
    assert created.status_code == 201
    uid = created.json()["id"]
    approve = f"/releases/v1.38/updates/{uid}/approve"
    body = json.dumps({"acknowledge_warnings": True, "acknowledge_stale": True}).encode()
    done = client.post(
        approve, content=body, headers=signed("preetdhindsa1", "POST", approve, body)
    )
    assert done.status_code == 200
    assert done.json()["decided_by"] == "user:preetdhindsa1"


def test_anonymous_visitors_never_trigger_paid_ai() -> None:
    from agents.gateway import Gateway
    from agents.ledger import MemoryLedger
    from agents.notes import MemoryNoteStore
    from agents.settings import AISettings
    from api.ai import AIServices
    from tests.agents.test_risk_analyst import BAD, Sequenced

    calls = Sequenced(BAD, BAD)
    ai = AIServices(gateway=Gateway(AISettings(), MemoryLedger(), calls), notes=MemoryNoteStore())
    client = TestClient(create_app(service=service(utc(2026, 11, 10)), ai=ai, auth=REQUIRED))
    path = "/releases/v1.38/features/6395/risk-note"
    body = client.get(path).json()
    assert body["status"] == "sign_in_required"
    assert calls.calls == []
    fresh = client.get(path, headers=signed("preetdhindsa1", "GET", path)).json()
    assert fresh["status"] == "fresh"
    assert client.get(path).json()["status"] == "reused"  # the stored note is public
