"""Gateway with a fake Messages client: caching, budget, refusals, cost, verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from agents.gateway import (
    AIRefusedError,
    AITruncatedError,
    BudgetExceededError,
    Gateway,
    TaskSpec,
    verify_output,
)
from agents.ledger import MemoryLedger, UsageRecord
from agents.pricing import TokenUsage
from agents.prompts import Prompt
from agents.schemas import ClaimOut, ClaimsOut
from agents.settings import AISettings, ModelRole
from verify.facts import Fact, FactKind, FactSheet

NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)
PROMPT = Prompt("smoke", 1, "Return claims.")
SIMPLE = TaskSpec("smoke", ModelRole.SIMPLE, "low", 2000, essential=False)
SUMMARY = TaskSpec("vp_summary", ModelRole.SUMMARY, "medium", 4000, essential=True)
FACTS = FactSheet(
    [Fact("release::code_freeze_at", FactKind.DATE, datetime(2026, 11, 17, 12, tzinfo=UTC))]
)
GOOD = ClaimsOut(
    claims=[
        ClaimOut(
            text="Code Freeze was Nov 17.",
            type=FactKind.DATE,
            refs=["release::code_freeze_at"],
            value="2026-11-17",
        ),
        ClaimOut(text="Odds are 90%.", type=FactKind.PROBABILITY, refs=[], value=0.9),
    ]
)


@dataclass
class Usage:
    input_tokens: int = 1000
    output_tokens: int = 200
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    iterations: list[Any] | None = None


@dataclass
class Response:
    parsed_output: Any = field(default_factory=lambda: GOOD)
    stop_reason: str = "end_turn"
    model: str = "claude-haiku-5-5"
    usage: Usage = field(default_factory=Usage)
    stop_details: Any = None
    _request_id: str = "req_test"


class FakeClient:
    def __init__(self, response: Response | Exception | None = None) -> None:
        self.response = response or Response()
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def gateway(client: FakeClient, ledger: MemoryLedger | None = None) -> Gateway:
    return Gateway(AISettings(), ledger or MemoryLedger(), client, clock=lambda: NOW)


def test_call_records_cost_and_caches() -> None:
    client, ledger = FakeClient(), MemoryLedger()
    gw = gateway(client, ledger)
    first = gw.run(SIMPLE, PROMPT, FACTS.as_prompt_rows(), ClaimsOut)
    second = gw.run(SIMPLE, PROMPT, FACTS.as_prompt_rows(), ClaimsOut)
    assert len(client.calls) == 1  # second answer came from the cache
    assert not first.cached
    assert second.cached
    assert second.output == first.output
    assert first.cost_usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1e6)
    assert [r.outcome for r in ledger.records] == ["ok", "cache_hit"]


def test_request_shape_uses_config_model_caching_and_effort() -> None:
    client = FakeClient()
    gateway(client).run(SIMPLE, PROMPT, {"x": 1}, ClaimsOut)
    req = client.calls[0]
    assert req["model"] == "claude-haiku-5-5"
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"] == {"effort": "low"}
    assert req["output_format"] is ClaimsOut
    assert "fallbacks" not in req  # Haiku has no server-side fallback


def test_summary_role_uses_strong_model_with_refusal_fallback() -> None:
    client = FakeClient(Response(model="claude-opus-5-5"))
    gateway(client).run(SUMMARY, PROMPT, {"x": 1}, ClaimsOut)
    req = client.calls[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default"


def test_fallback_iterations_are_billed_per_model() -> None:
    @dataclass
    class It:
        type: str
        model: str
        input_tokens: int
        output_tokens: int
        cache_read_input_tokens: int = 0
        cache_creation_input_tokens: int = 0

    usage = Usage(
        iterations=[
            It("message", "claude-opus-5-5", 1000, 0),
            It("fallback_message", "claude-opus-4-8", 1000, 500),
        ]
    )
    ledger = MemoryLedger()
    gateway(FakeClient(Response(usage=usage, model="claude-opus-4-8")), ledger).run(
        SUMMARY, PROMPT, {}, ClaimsOut
    )
    rec = ledger.records[-1]
    assert [u.model for u in rec.usages] == ["claude-opus-5-5", "claude-opus-4-8"]
    # Opus 4.8 is not in the price table: charged at the most expensive known rate.
    assert rec.cost_usd == pytest.approx((1000 * 4 + 1000 * 8 + 500 * 40) / 1e6)


def test_budget_denial_is_recorded_and_raised() -> None:
    ledger = MemoryLedger()
    ledger.record(
        UsageRecord(
            "x", "p", "m", False, "ok", "f",
            usages=(TokenUsage("claude-opus-5-5", output_tokens=100_000),),  # $2.00
            at=NOW,
        )
    )  # fmt: skip
    client = FakeClient()
    with pytest.raises(BudgetExceededError):
        gateway(client, ledger).run(SIMPLE, PROMPT, {}, ClaimsOut)
    assert client.calls == []
    assert ledger.records[-1].outcome == "budget_denied"


def test_cache_hit_needs_no_budget() -> None:
    ledger = MemoryLedger()
    gw = gateway(FakeClient(), ledger)
    gw.run(SIMPLE, PROMPT, {}, ClaimsOut)
    ledger.record(
        UsageRecord(
            "x", "p", "m", False, "ok", "f",
            usages=(TokenUsage("claude-opus-5-5", output_tokens=200_000),), at=NOW,
        )
    )  # fmt: skip
    assert gw.run(SIMPLE, PROMPT, {}, ClaimsOut).cached


def test_refusal_and_truncation() -> None:
    with pytest.raises(AIRefusedError):
        gateway(FakeClient(Response(stop_reason="refusal", parsed_output=None))).run(
            SIMPLE, PROMPT, {}, ClaimsOut
        )
    ledger = MemoryLedger()
    with pytest.raises(AITruncatedError):
        gateway(FakeClient(Response(stop_reason="max_tokens", parsed_output=None)), ledger).run(
            SIMPLE, PROMPT, {}, ClaimsOut
        )
    assert ledger.records[-1].outcome == "max_tokens"
    assert ledger.records[-1].cost_usd > 0  # truncated calls still cost money
    assert ledger.results == {}  # and are never cached


def test_verify_output_keeps_only_verified_claims_and_stores_counts() -> None:
    ledger = MemoryLedger()
    response = gateway(FakeClient(), ledger).run(SIMPLE, PROMPT, FACTS.as_prompt_rows(), ClaimsOut)
    report = verify_output(response, FACTS, ledger)
    assert [c.text for c in report.verified] == ["Code Freeze was Nov 17."]
    assert ledger.results[response.fingerprint].check_counts == report.counts
    assert report.counts["removed.no_supporting_data"] == 1


def test_verify_output_logs_one_line_for_the_removal_rate_alert(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#45: CLAUDE.md section 9 alerts on an unusual fact-checker removal rate."""
    ledger = MemoryLedger()
    response = gateway(FakeClient(), ledger).run(SIMPLE, PROMPT, FACTS.as_prompt_rows(), ClaimsOut)
    with caplog.at_level("INFO", logger="agents.gateway"):
        report = verify_output(response, FACTS, ledger)
    [line] = [r for r in caplog.records if r.getMessage() == "claims checked"]
    assert line.removal_rate == report.removal_rate  # type: ignore[attr-defined]
    assert line.counts == report.counts  # type: ignore[attr-defined]
    assert line.claims == len(report.checked)  # type: ignore[attr-defined]
