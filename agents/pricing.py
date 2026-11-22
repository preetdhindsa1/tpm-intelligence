"""Token prices and call cost. Pure, no I/O.

Prices in USD per million tokens, Anthropic first-party API, as listed on 2026-11-03.
Cache writes use the 5-minute TTL rate (1.25x input). Update this table when prices
change; an unknown model is charged at the most expensive known rate so the budget errs
on the safe side.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
        """5-minute cache write rate."""
        return self.input * 1.25


PRICES: Mapping[str, Price] = {
    "claude-fable-5-2": Price(8.0, 40.0, 0.20),
    "claude-opus-5-5": Price(4.0, 20.0, 0.20),
    "claude-sonnet-5-5": Price(2.0, 10.0, 0.10),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01),  # cache read assumed 10% of input
}
_FALLBACK_PRICE = max(PRICES.values(), key=lambda p: p.output)


def price_for(model: str) -> Price:
    """Known price, else the most expensive one (conservative)."""
    return PRICES.get(model, _FALLBACK_PRICE)


@dataclass(frozen=True)
class TokenUsage:
    """Tokens billed for one model within a call."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        """Cost of these tokens."""
        p = price_for(self.model)
        return (
            self.input_tokens * p.input
            + self.output_tokens * p.output
            + self.cache_read_tokens * p.cache_read
            + self.cache_write_tokens * p.cache_write
        ) / 1_000_000


def total_cost(usages: Iterable[TokenUsage]) -> float:
    """Sum over models (a refusal fallback bills two models in one call)."""
    return sum(u.cost_usd for u in usages)


def worst_case_cost(model: str, prompt_chars: int, max_tokens: int) -> float:
    """Upper-bound estimate before a call: ~3 characters per token, full ``max_tokens``."""
    p = price_for(model)
    return (prompt_chars / 3 * p.input + max_tokens * p.output) / 1_000_000
