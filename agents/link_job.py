"""Run the link suggester over a release's unlinked PRs (ADR-0011).

* Open PRs first (they are today's reviewer load), then newest first.
* A PR whose shortlist is empty costs nothing: no call is made.
* A PR already processed with the same input and prompt is skipped.
* Non-essential: when the budget blocks a call, the run stops and reports why. The next
  run continues where it stopped.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from opentelemetry import trace

from agents.gateway import AIError, BudgetExceededError, Gateway
from agents.link_store import LinkSuggestion, LinkSuggestionStore, SuggestionStatus
from agents.link_suggester import PullRequestText, input_sha, suggest_link, suggester_inputs
from agents.prompts import Prompt, load_prompt
from engine.links import candidate_index, link_release, unlinked_pull_requests
from engine.projection import World
from linker.candidates import shortlist
from pipeline.store.tenancy import carry

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass
class RunReport:
    """What one run did."""

    release_key: str
    unlinked: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    cost_usd: float = 0.0
    stopped: str | None = None

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly."""
        return {
            "release": self.release_key,
            "unlinked_prs": self.unlinked,
            **dict(sorted(self.counts.items())),
            "cost_usd": round(self.cost_usd, 6),
            "stopped": self.stopped,
        }


def suggest_for_release(
    gateway: Gateway,
    store: LinkSuggestionStore,
    world: World,
    release_key: str,
    *,
    prompt: Prompt | None = None,
    limit: int | None = None,
    workers: int = 4,
) -> RunReport:
    """Process up to ``limit`` unlinked PRs; see the module docstring."""
    prompt = prompt or load_prompt("link_suggester")
    links = link_release(world, release_key)
    unlinked = unlinked_pull_requests(world, release_key, links)
    report = RunReport(release_key, unlinked=len(unlinked))
    index = candidate_index(world, release_key)
    seen = store.seen(release_key)

    def order(key: str) -> tuple[bool, float]:
        pr = world.pull_requests[key]
        return (not pr.is_open, -pr.created_at.timestamp())

    work = []
    for key in sorted(unlinked, key=order):
        pr = world.pull_requests[key]
        text = PullRequestText(pr.key, pr.title, pr.body, pr.labels)
        cands = shortlist(pr.title, pr.body, pr.labels, index)
        if not cands:
            report.counts["no_candidates"] += 1
            continue
        if (key, input_sha(suggester_inputs(text, cands)), prompt.label) in seen:
            report.counts["already_done"] += 1
            continue
        work.append((text, cands))
    if limit is not None:
        report.counts["left_for_later"] += max(len(work) - limit, 0)
        work = work[:limit]

    stop = threading.Event()
    lock = threading.Lock()

    def one(item: tuple[PullRequestText, list]) -> None:  # type: ignore[type-arg]
        text, cands = item
        if stop.is_set():
            with lock:
                report.counts["left_for_later"] += 1
            return
        try:
            result = suggest_link(gateway, prompt, text, cands)
        except BudgetExceededError as exc:
            stop.set()
            with lock:
                report.stopped = f"AI budget: {exc.decision.reason}"
                report.counts["left_for_later"] += 1
            return
        except AIError as exc:
            logger.warning("link suggester failed", extra={"pr": text.key, "error": str(exc)})
            with lock:
                report.counts["errors"] += 1
            return
        store.save(
            LinkSuggestion(
                release_key=release_key,
                pull_request_key=text.key,
                feature_key=result.checked.feature_key,
                status=SuggestionStatus(result.checked.outcome.value),
                evidence=result.evidence(),
                input_sha=result.input_sha,
                prompt_version=prompt.label,
                model=result.model,
                cost_usd=result.cost_usd,
            )
        )
        with lock:
            report.counts[result.checked.outcome.value] += 1
            report.cost_usd += result.cost_usd

    with tracer.start_as_current_span(
        "agents.suggest_links", attributes={"tpm.release": release_key, "tpm.prs": len(work)}
    ):
        if workers <= 1:
            for item in work:
                one(item)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(carry(one), work))  # pool threads keep the tenant
    return report
