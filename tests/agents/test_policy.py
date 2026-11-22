"""Budget policy, pricing, cache fingerprint, re-run thresholds, prompt loading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agents.budget import BudgetState, budget_state, decide
from agents.fingerprint import fingerprint
from agents.pricing import TokenUsage, price_for, total_cost, worst_case_cost
from agents.prompts import load_prompt
from agents.rerun import changed_meaningfully
from verify.facts import Fact, FactKind

NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)


def d(**kw: object) -> object:
    base: dict[str, object] = {
        "spent": 0.0,
        "estimate": 0.01,
        "cap": 2.0,
        "essential": False,
        "now": NOW,
        "last_nonessential_at": None,
    }
    base.update(kw)
    return decide(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------- budget


def test_states() -> None:
    assert budget_state(1.59, 2.0, 0.8) is BudgetState.NORMAL
    assert budget_state(1.60, 2.0, 0.8) is BudgetState.SLOW
    assert budget_state(2.00, 2.0, 0.8) is BudgetState.PAUSED


def test_normal_allows() -> None:
    assert d().allowed  # type: ignore[attr-defined]


def test_slow_spaces_out_nonessential_calls() -> None:
    recent = d(spent=1.7, last_nonessential_at=NOW - timedelta(seconds=20))
    assert not recent.allowed  # type: ignore[attr-defined]
    assert recent.retry_after_s == pytest.approx(40)  # type: ignore[attr-defined]
    assert d(spent=1.7, last_nonessential_at=NOW - timedelta(seconds=61)).allowed  # type: ignore[attr-defined]


def test_paused_blocks_nonessential_but_essential_may_finish_under_cap() -> None:
    assert not d(spent=2.0).allowed  # type: ignore[attr-defined]
    assert d(spent=1.9, essential=True, estimate=0.05).allowed  # type: ignore[attr-defined]
    assert not d(spent=1.98, essential=True, estimate=0.05).allowed  # type: ignore[attr-defined]


def test_worst_case_estimate_prevents_overshoot() -> None:
    """A call that would cross the cap is refused before it runs."""
    assert not d(spent=1.95, estimate=0.10).allowed  # type: ignore[attr-defined]


def test_essential_overage_is_opt_in() -> None:
    assert d(spent=2.0, essential=True, essential_overage=0.25).allowed  # type: ignore[attr-defined]


# ---------------------------------------------------------------- pricing


def test_cost_per_model_and_fallback_sum() -> None:
    opus = TokenUsage("claude-opus-5-5", input_tokens=1_000_000, output_tokens=100_000)
    assert opus.cost_usd == pytest.approx(4.0 + 2.0)
    cached = TokenUsage(
        "claude-opus-5-5", cache_read_tokens=1_000_000, cache_write_tokens=1_000_000
    )
    assert cached.cost_usd == pytest.approx(0.20 + 5.0)
    haiku = TokenUsage("claude-haiku-5-5", output_tokens=1_000_000)
    assert total_cost([opus, haiku]) == pytest.approx(6.5)


def test_unknown_model_is_charged_conservatively() -> None:
    assert price_for("claude-unknown").output == 40.0


def test_worst_case_counts_full_max_tokens() -> None:
    expected = (1000 * 0.1 + 4000 * 0.5) / 1e6
    assert worst_case_cost("claude-haiku-5-5", 3000, 4000) == pytest.approx(expected)


# ---------------------------------------------------------------- fingerprint and re-run


def test_fingerprint_is_order_independent_and_sensitive_to_prompt() -> None:
    a = fingerprint(task="t", prompt_sha="p1", model="m", inputs={"b": 1, "a": [1, 2]})
    b = fingerprint(task="t", prompt_sha="p1", model="m", inputs={"a": [1, 2], "b": 1})
    c = fingerprint(task="t", prompt_sha="p2", model="m", inputs={"a": [1, 2], "b": 1})
    assert a == b
    assert a != c


K = "feature:kubernetes/enhancements#6395::"


def facts(p: float, **extra: object) -> dict[str, Fact]:
    rows = {K + "odds.probability": Fact(K + "odds.probability", FactKind.PROBABILITY, p)}
    for name, value in extra.items():
        rows[K + name] = Fact(K + name, FactKind.BOOLEAN, value)  # type: ignore[arg-type]
    return rows


def test_rerun_thresholds() -> None:
    assert changed_meaningfully(None, facts(0.4))[0]
    assert not changed_meaningfully(facts(0.40), facts(0.48))[0]  # 8 points: jitter
    assert changed_meaningfully(facts(0.40), facts(0.51))[0]  # 11 points
    assert changed_meaningfully(facts(0.4, in_release=True), facts(0.4, in_release=False))[0]
    assert changed_meaningfully(facts(0.4), facts(0.4, **{"flag.ci_failing": True}))[0]


# ---------------------------------------------------------------- prompts


def test_prompt_versions(tmp_path: Path) -> None:
    (tmp_path / "x.v1.md").write_text("one")
    (tmp_path / "x.v2.md").write_text("two")
    assert load_prompt("x", directory=tmp_path).version == 2
    assert load_prompt("x", 1, directory=tmp_path).text == "one"
    assert load_prompt("x", 1, directory=tmp_path).sha != load_prompt("x", directory=tmp_path).sha
    with pytest.raises(FileNotFoundError):
        load_prompt("x", 3, directory=tmp_path)


def test_repo_smoke_prompt_exists() -> None:
    assert load_prompt("smoke").label == "smoke.v1"
