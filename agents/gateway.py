"""The one path from the platform to Claude (CLAUDE.md section 8).

Every call goes: fingerprint -> cache -> budget check -> Claude (structured output) ->
cost accounting -> cache write. Each step is recorded in ``ai_usage``, traced with
OpenTelemetry (the Anthropic SDK adds GenAI child spans) and counted in metrics.

Agents get facts only, as a fact sheet; the output is a Pydantic model that the fact
checker verifies before anyone sees it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from opentelemetry import metrics, trace
from opentelemetry.util.types import AttributeValue
from pydantic import BaseModel

from agents.budget import BudgetDecision, BudgetState, budget_state, decide
from agents.fingerprint import fingerprint
from agents.ledger import Ledger, UsageRecord
from agents.pricing import TokenUsage, worst_case_cost
from agents.prompts import Prompt
from agents.settings import AISettings, ModelRole

logger = logging.getLogger("agents.gateway")
_tracer = trace.get_tracer("agents.gateway")
_meter = metrics.get_meter("agents.gateway")
_calls = _meter.create_counter("ai.calls", unit="{call}", description="AI calls by outcome")
_cost = _meter.create_counter("ai.cost", unit="USD", description="AI spend")
_tokens = _meter.create_counter("ai.tokens", unit="{token}", description="Tokens billed")
_budget = _meter.create_gauge(
    "ai.budget.used_fraction", description="Share of today's AI budget spent (alert at 0.8)"
)

# Models that accept server-side refusal fallbacks (Haiku does not).
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class TaskSpec:
    """How one kind of AI work is run."""

    name: str
    role: ModelRole
    effort: str  # low | medium | high
    max_tokens: int
    essential: bool  # True only for work a person asked for (budget section in budget.py)


class AIError(Exception):
    """An AI call did not produce a usable output."""


class BudgetExceededError(AIError):
    """The budget policy blocked the call."""

    def __init__(self, decision: BudgetDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision


class AIRefusedError(AIError):
    """The model (and any fallback) declined."""


class AITruncatedError(AIError):
    """Output hit ``max_tokens`` before the structured answer was complete."""


@dataclass(frozen=True)
class AIResponse[T: BaseModel]:
    """A validated output and what it cost."""

    output: T
    cached: bool
    model: str
    cost_usd: float
    fingerprint: str
    request_id: str | None = None


class MessagesClient(Protocol):
    """The part of ``anthropic.Anthropic().beta.messages`` the gateway uses."""

    def parse(self, **kwargs: Any) -> Any:
        """Structured-output request."""
        ...


def default_client(settings: AISettings) -> MessagesClient:
    """Anthropic SDK client. Credentials come from ``ANTHROPIC_API_KEY``."""
    import anthropic

    from pipeline.env import configured

    if configured("ANTHROPIC_API_KEY") is None:
        raise AIError("ANTHROPIC_API_KEY is not configured on this deployment")

    mode = "content" if settings.trace_content else "metadata_only"
    otel: Any = {"traces": {"content_mode": mode}}
    client = anthropic.Anthropic(
        timeout=settings.timeout_s,
        max_retries=settings.max_retries,  # SDK retries 408/409/429/5xx with backoff
        open_telemetry=otel,
    )
    return cast(MessagesClient, client.beta.messages)


def usages_from(response: Any, requested_model: str) -> list[TokenUsage]:
    """Billed tokens per model; a refusal fallback reports one iteration per model."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return []
    iterations = [
        it
        for it in (getattr(usage, "iterations", None) or [])
        if getattr(it, "type", "") in {"message", "fallback_message"}
    ]
    rows = iterations or [usage]
    served = getattr(response, "model", None) or requested_model
    return [
        TokenUsage(
            model=getattr(it, "model", None) or served,
            input_tokens=getattr(it, "input_tokens", 0) or 0,
            output_tokens=getattr(it, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(it, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(it, "cache_creation_input_tokens", 0) or 0,
        )
        for it in rows
    ]


class Gateway:
    """Budgeted, cached, traced structured calls to Claude."""

    def __init__(
        self,
        settings: AISettings,
        ledger: Ledger,
        client: MessagesClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self._client = client
        self._clock = clock

    @property
    def client(self) -> MessagesClient:
        """Created on first use, so tests and cache hits need no API key."""
        if self._client is None:
            self._client = default_client(self.settings)
        return self._client

    def budget_fraction(self) -> float:
        """Share of today's cap spent."""
        return self.ledger.spent_today(self._clock()) / self.settings.daily_budget_usd

    def run[T: BaseModel](
        self,
        task: TaskSpec,
        prompt: Prompt,
        inputs: Any,
        output_model: type[T],
    ) -> AIResponse[T]:
        """Run ``task`` on ``inputs`` (JSON-serialisable facts) and return a validated output."""
        model = self.settings.model_for(task.role)
        fp = fingerprint(task=task.name, prompt_sha=prompt.sha, model=model, inputs=inputs)
        user_text = json.dumps(inputs, sort_keys=True, default=str, indent=1)
        attrs: dict[str, AttributeValue] = {
            "ai.task": task.name,
            "ai.prompt": prompt.label,
            "ai.model": model,
            "ai.essential": task.essential,
            "ai.fingerprint": fp,
        }
        with _tracer.start_as_current_span(f"ai.{task.name}", attributes=attrs) as span:
            base = UsageRecord(
                task=task.name,
                prompt_version=prompt.label,
                model_requested=model,
                essential=task.essential,
                outcome="ok",
                fingerprint=fp,
            )

            cached = self.ledger.get_result(fp)
            if cached is not None:
                self._finish(span, replace(base, outcome="cache_hit"), task)
                return AIResponse(output_model.model_validate(cached.output), True, model, 0.0, fp)

            now = self._clock()
            spent = self.ledger.spent_today(now)
            decision = decide(
                spent=spent,
                estimate=worst_case_cost(model, len(prompt.text) + len(user_text), task.max_tokens),
                cap=self.settings.daily_budget_usd,
                essential=task.essential,
                now=now,
                last_nonessential_at=self.ledger.last_nonessential_at(now),
                slow_at=self.settings.slow_at,
                slow_interval_s=self.settings.slow_interval_s,
                essential_overage=self.settings.essential_overage,
            )
            span.set_attribute("ai.budget.state", decision.state.value)
            if not decision.allowed:
                self._finish(
                    span, replace(base, outcome="budget_denied", detail=decision.reason), task
                )
                raise BudgetExceededError(decision)

            try:
                request = self._request(task, model, prompt, user_text, output_model)
                response = self.client.parse(**request)
            except Exception as exc:  # SDK errors after its own retries
                self._finish(span, replace(base, outcome="error", detail=type(exc).__name__), task)
                raise AIError(f"{task.name}: {type(exc).__name__}: {exc}") from exc

            usages = tuple(usages_from(response, model))
            served = getattr(response, "model", None) or model
            request_id = getattr(response, "_request_id", None)
            stop = getattr(response, "stop_reason", None)
            paid = replace(base, usages=usages, model_served=served, request_id=request_id)
            if stop == "refusal":
                details = getattr(response, "stop_details", None)
                category = getattr(details, "category", None)
                self._finish(span, replace(paid, outcome="refused", detail=str(category)), task)
                raise AIRefusedError(f"{task.name}: refused ({category})")
            parsed = getattr(response, "parsed_output", None)
            if stop == "max_tokens" or parsed is None:
                self._finish(span, replace(paid, outcome="max_tokens", detail=str(stop)), task)
                raise AITruncatedError(f"{task.name}: no complete output (stop_reason={stop})")

            self._finish(span, paid, task)
            self.ledger.put_result(
                fp,
                task=task.name,
                prompt_version=prompt.label,
                model=served,
                output=parsed.model_dump(mode="json"),
            )
            return AIResponse(parsed, False, served, paid.cost_usd, fp, request_id)

    def _request(
        self,
        task: TaskSpec,
        model: str,
        prompt: Prompt,
        user_text: str,
        output_model: type[BaseModel],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": task.max_tokens,
            # Stable system prompt first, marked for caching; the facts vary per call.
            "system": [
                {"type": "text", "text": prompt.text, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": f"Fact sheet:\n{user_text}"}],
            "output_format": output_model,
            "output_config": {"effort": task.effort},
        }
        if model.startswith(_FALLBACK_MODELS):
            request["betas"] = [_FALLBACK_BETA]
            request["fallbacks"] = "default"
        return request

    def _finish(self, span: Any, rec: UsageRecord, task: TaskSpec) -> None:
        self.ledger.record(rec)
        labels = {"task": task.name, "model": rec.model_served or rec.model_requested}
        _calls.add(1, {**labels, "outcome": rec.outcome})
        span.set_attribute("ai.outcome", rec.outcome)
        if rec.usages:
            span.set_attribute("ai.cost_usd", rec.cost_usd)
            _cost.add(rec.cost_usd, labels)
            for kind in ("input", "output", "cache_read", "cache_write"):
                n = sum(getattr(u, f"{kind}_tokens") for u in rec.usages)
                if n:
                    _tokens.add(n, {**labels, "kind": kind})
        fraction = self.budget_fraction()
        _budget.set(fraction)
        state = budget_state(
            fraction * self.settings.daily_budget_usd,
            self.settings.daily_budget_usd,
            self.settings.slow_at,
        )
        if state is not BudgetState.NORMAL and rec.usages:
            logger.warning("ai budget %s", state.value, extra={"used_fraction": round(fraction, 3)})


def verify_output(response: AIResponse[Any], facts: Any, ledger: Ledger) -> Any:
    """Fact-check a claims output and store the counts next to the cached result."""
    from verify.checker import check_claims

    claims = [c.to_claim() for c in response.output.claims]
    report = check_claims(claims, facts)
    ledger.set_check_counts(response.fingerprint, report.counts)
    return report


__all__: Sequence[str] = (
    "AIError",
    "AIRefusedError",
    "AIResponse",
    "AITruncatedError",
    "BudgetExceededError",
    "Gateway",
    "TaskSpec",
    "verify_output",
)
