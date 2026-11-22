"""AI link suggester: which feature is this unlinked PR work for? (ADR-0011)

1. Code builds a shortlist of the release's features (``linker.candidates``).
2. Claude (simple model) picks one or answers ``null``, quoting both sides.
3. Code checks the answer (``linker.suggestions``). Only checked answers are stored as
   ``suggested``; a person confirms or rejects them in the review queue.

Non-essential: when the daily budget pauses it, the run stops and resumes another day.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agents.gateway import Gateway, TaskSpec
from agents.prompts import Prompt
from agents.settings import ModelRole
from linker.candidates import Candidate, pr_text
from linker.suggestions import CheckedSuggestion, check_suggestion

TASK = TaskSpec("link_suggester", ModelRole.SIMPLE, effort="low", max_tokens=1500, essential=False)
MAX_PR_CHARS = 3000
_LABEL_PREFIXES = ("sig/", "area/", "kind/")


class LinkPickOut(BaseModel):
    """The model's answer."""

    model_config = ConfigDict(extra="forbid")

    feature_key: str | None = Field(
        description="Key of the chosen candidate, exactly as given, or null."
    )
    pr_quote: str = Field(description="Exact phrase from the pull request; empty if null.")
    feature_quote: str = Field(
        description="Exact phrase from the chosen feature's title, summary or gate; empty if null."
    )


@dataclass(frozen=True)
class PullRequestText:
    """The parts of a PR the suggester sees."""

    key: str
    title: str
    body: str
    labels: tuple[str, ...]


def shown_text(pr: PullRequestText) -> str:
    """PR text as shown to the model (the quote is checked against exactly this)."""
    return pr_text(pr.title, pr.body)[:MAX_PR_CHARS]


def suggester_inputs(pr: PullRequestText, candidates: Sequence[Candidate]) -> dict[str, Any]:
    """The whole input of one call: the PR and the shortlist, nothing else."""
    return {
        "pull_request": {
            "key": pr.key,
            "title": pr.title,
            "labels": sorted(lb for lb in pr.labels if lb.startswith(_LABEL_PREFIXES)),
            "text": shown_text(pr),
        },
        "candidates": [
            {
                "key": c.feature.key,
                "title": c.feature.title,
                "summary": c.feature.summary,
                "feature_gates": list(c.feature.feature_gates),
                "sigs": list(c.feature.sigs),
                "stage": c.feature.stage,
            }
            for c in candidates
        ],
    }


def input_sha(inputs: dict[str, Any]) -> str:
    """Stable hash of a call's input, to skip PRs already processed with the same input."""
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class SuggestionResult:
    """One PR's answer, its verdict and its cost."""

    pull_request_key: str
    checked: CheckedSuggestion
    answer: LinkPickOut
    candidates: tuple[Candidate, ...]
    input_sha: str
    model: str
    cost_usd: float
    cached: bool

    def evidence(self) -> dict[str, Any]:
        """What the review queue shows next to the suggestion."""
        chosen = next(
            (c for c in self.candidates if c.feature.key == self.checked.feature_key), None
        )
        return {
            "pr_quote": self.answer.pr_quote,
            "feature_quote": self.answer.feature_quote,
            "shortlist_rank": self.checked.rank,
            "shortlist_size": len(self.candidates),
            "shared_words": list(chosen.shared_words) if chosen else [],
            "drop_reason": self.checked.reason.value if self.checked.reason else None,
        }


def suggest_link(
    gateway: Gateway, prompt: Prompt, pr: PullRequestText, candidates: Sequence[Candidate]
) -> SuggestionResult:
    """One call plus the deterministic check. Raises ``AIError`` (incl. budget) unchanged."""
    inputs = suggester_inputs(pr, candidates)
    response = gateway.run(TASK, prompt, inputs, LinkPickOut)
    out = response.output
    checked = check_suggestion(
        out.feature_key, out.pr_quote, out.feature_quote, shown_text(pr), candidates
    )
    return SuggestionResult(
        pull_request_key=pr.key,
        checked=checked,
        answer=out,
        candidates=tuple(candidates),
        input_sha=input_sha(inputs),
        model=response.model,
        cost_usd=response.cost_usd,
        cached=response.cached,
    )
