"""Draft -> verify -> (one) redraft, as a LangGraph state machine (ADR-0010).

1. ``draft``: the gateway asks Claude for claims about the fact sheet.
2. ``verify``: the fact checker keeps verified claims and records why others were removed.
3. If more than ``retry_above`` of the claims were removed and no retry happened yet, draft
   again with the removal reasons as feedback (a new input, so a new cache key).
4. The attempt with the most verified claims wins. Only verified claims leave this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agents.gateway import Gateway, TaskSpec, verify_output
from agents.prompts import Prompt
from agents.schemas import ClaimsOut
from verify.checker import CheckReport, Verdict
from verify.claims import Claim
from verify.facts import FactSheet

RETRY_ABOVE = 0.30
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class Attempt:
    """One draft and its fact-check report."""

    report: CheckReport
    output: BaseModel  # the parsed answer, e.g. ClaimsOut or ExecUpdateOut
    model: str
    cost_usd: float
    cached: bool
    fingerprint: str


@dataclass(frozen=True)
class LoopResult:
    """Verified claims of the best attempt, plus every attempt for the record."""

    claims: tuple[Claim, ...]
    best: Attempt
    attempts: tuple[Attempt, ...]

    @property
    def cost_usd(self) -> float:
        """Total across attempts."""
        return sum(a.cost_usd for a in self.attempts)


class _State(TypedDict):
    attempts: list[Attempt]


def _feedback(report: CheckReport) -> list[dict[str, Any]]:
    return [
        {
            "claim": c.claim.text,
            "removed_because": c.reason.value if c.reason else "",
            "detail": c.detail,
        }
        for c in report.checked
        if c.verdict is Verdict.REMOVED
    ]


def run_loop(
    gateway: Gateway,
    task: TaskSpec,
    prompt: Prompt,
    facts: FactSheet,
    *,
    retry_above: float = RETRY_ABOVE,
    max_attempts: int = MAX_ATTEMPTS,
    extra_inputs: dict[str, Any] | None = None,
    output_model: type[BaseModel] = ClaimsOut,
) -> LoopResult:
    """Run the graph and return the best attempt's verified claims."""

    def draft_and_verify(state: _State) -> dict[str, list[Attempt]]:
        inputs: dict[str, Any] = {"facts": facts.as_prompt_rows(), **(extra_inputs or {})}
        if state["attempts"]:
            inputs["previous_attempt_removed"] = _feedback(state["attempts"][-1].report)
        response = gateway.run(task, prompt, inputs, output_model)
        report = verify_output(response, facts, gateway.ledger)
        attempt = Attempt(
            report,
            response.output,
            response.model,
            response.cost_usd,
            response.cached,
            response.fingerprint,
        )
        return {"attempts": [*state["attempts"], attempt]}

    def route(state: _State) -> str:
        last = state["attempts"][-1].report
        rate = last.removal_rate
        if len(state["attempts"]) < max_attempts and (rate is None or rate > retry_above):
            return "draft"
        return END

    graph = StateGraph(_State)
    graph.add_node("draft", draft_and_verify)
    graph.add_edge(START, "draft")
    graph.add_conditional_edges("draft", route)
    final: _State = graph.compile().invoke({"attempts": []})  # type: ignore[assignment]

    attempts = tuple(final["attempts"])
    best = max(attempts, key=lambda a: len(a.report.verified))
    return LoopResult(best.report.verified, best, attempts)
