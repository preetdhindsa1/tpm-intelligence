"""Deterministic PR -> work item linking (ADR-0004). Pure functions, no I/O.

Every candidate carries a method, a confidence, a status and the evidence that produced it.
Only ``verified`` links count as facts downstream; ``suggested`` links are shown for a
person (or a later rule) to confirm.

=======================  =========================================  =========  ====
Method                   When                                       Status     Conf
=======================  =========================================  =========  ====
``explicit_key``         strong KEP reference (see ``linker.refs``)  verified   0.95
``tracking_issue_link``  PR URL listed in the KEP issue description  verified   0.90
``feature_gate``         gate of exactly one KEP named in the PR     verified   0.75
``explicit_key``         passing mention only (#143644)              suggested  0.50
``feature_gate``         gate shared by several KEPs                 suggested  0.40
=======================  =========================================  =========  ====

``labels`` (SIG overlap) never creates a link on its own: every SIG has dozens of KEPs.
It is recorded as evidence (``sig_overlap``) on candidates that exist for other reasons.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from linker.methods import LinkMethod, LinkStatus
from linker.refs import find_kep_refs, tracked_pull_requests

CONFIDENCE: Mapping[tuple[LinkMethod, LinkStatus], Decimal] = {
    (LinkMethod.EXPLICIT_KEY, LinkStatus.VERIFIED): Decimal("0.95"),
    (LinkMethod.TRACKING_ISSUE_LINK, LinkStatus.VERIFIED): Decimal("0.90"),
    (LinkMethod.FEATURE_GATE, LinkStatus.VERIFIED): Decimal("0.75"),
    (LinkMethod.EXPLICIT_KEY, LinkStatus.SUGGESTED): Decimal("0.50"),
    (LinkMethod.FEATURE_GATE, LinkStatus.SUGGESTED): Decimal("0.40"),
}


def _sigs(labels: Iterable[str]) -> set[str]:
    return {label for label in labels if label.startswith("sig/")}


@dataclass(frozen=True)
class WorkItemInfo:
    """What the linker needs about a KEP issue."""

    key: str  # "kubernetes/enhancements#6395"
    number: int  # 6395
    description: str = ""
    feature_flags: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class PullRequestInfo:
    """What the linker needs about a PR (text only)."""

    key: str  # "kubernetes/kubernetes#143709"
    repo: str
    number: int
    title: str
    body: str = ""
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkCandidate:
    """One proposed link with its provenance."""

    pull_request_key: str
    work_item_key: str
    method: LinkMethod
    status: LinkStatus
    confidence: Decimal
    evidence: Mapping[str, Any] = field(default_factory=dict)


def _candidate(
    pr: PullRequestInfo,
    item: WorkItemInfo,
    method: LinkMethod,
    status: LinkStatus,
    evidence: dict[str, Any],
) -> LinkCandidate:
    sigs = sorted(_sigs(pr.labels) & _sigs(item.labels))
    if sigs:
        evidence = {**evidence, "sig_overlap": sigs}
    return LinkCandidate(
        pull_request_key=pr.key,
        work_item_key=item.key,
        method=method,
        status=status,
        confidence=CONFIDENCE[(method, status)],
        evidence=evidence,
    )


@dataclass(frozen=True)
class LinkIndex:
    """Lookups built once per release from its work items."""

    by_number: Mapping[int, WorkItemInfo]
    tracked_by: Mapping[tuple[str, int], tuple[WorkItemInfo, ...]]
    gates: Mapping[str, tuple[WorkItemInfo, ...]]
    gate_pattern: re.Pattern[str] | None = None  # all gate names, one pass per PR

    def gates_in(self, text: str) -> list[str]:
        """Gate names mentioned as whole words in ``text`` (sorted, unique)."""
        if self.gate_pattern is None:
            return []
        return sorted(set(self.gate_pattern.findall(text)))

    @classmethod
    def build(cls, items: Iterable[WorkItemInfo]) -> LinkIndex:
        """Index work items by KEP number, tracked PR and feature gate."""
        by_number: dict[int, WorkItemInfo] = {}
        tracked: dict[tuple[str, int], list[WorkItemInfo]] = defaultdict(list)
        gates: dict[str, list[WorkItemInfo]] = defaultdict(list)
        for item in items:
            by_number[item.number] = item
            for pr in tracked_pull_requests(item.description):
                tracked[pr].append(item)
            for gate in item.feature_flags:
                gates[gate].append(item)
        # Longest first so a gate that prefixes another cannot shadow it.
        names = sorted(gates, key=lambda g: (-len(g), g))
        pattern = (
            re.compile(r"(?<!\w)(" + "|".join(map(re.escape, names)) + r")(?!\w)")
            if names
            else None
        )
        return cls(
            by_number=by_number,
            tracked_by={k: tuple(v) for k, v in tracked.items()},
            gates={k: tuple(v) for k, v in gates.items()},
            gate_pattern=pattern,
        )


def link_pull_request(pr: PullRequestInfo, index: LinkIndex) -> list[LinkCandidate]:
    """All link candidates for one PR (possibly several methods per work item)."""
    out: list[LinkCandidate] = []

    for ref in find_kep_refs(pr.title, pr.body):
        item = index.by_number.get(ref.number)
        if item is None:  # references a KEP outside this release
            continue
        status = LinkStatus.VERIFIED if ref.strong else LinkStatus.SUGGESTED
        out.append(
            _candidate(
                pr,
                item,
                LinkMethod.EXPLICIT_KEY,
                status,
                {"where": ref.where.value, "snippet": ref.snippet},
            )
        )

    for item in index.tracked_by.get((pr.repo, pr.number), ()):
        out.append(
            _candidate(
                pr,
                item,
                LinkMethod.TRACKING_ISSUE_LINK,
                LinkStatus.VERIFIED,
                {"listed_in": f"{item.key} description"},
            )
        )

    text = f"{pr.title}\n{pr.body}"
    for gate in index.gates_in(text):
        owners = index.gates[gate]
        status = LinkStatus.VERIFIED if len(owners) == 1 else LinkStatus.SUGGESTED
        for item in owners:
            out.append(
                _candidate(
                    pr,
                    item,
                    LinkMethod.FEATURE_GATE,
                    status,
                    {"feature_gate": gate, "gate_owners": len(owners)},
                )
            )
    return out


def best_links(candidates: Sequence[LinkCandidate]) -> dict[tuple[str, str], LinkCandidate]:
    """Strongest candidate per (PR, work item): verified beats suggested, then method rank."""
    best: dict[tuple[str, str], LinkCandidate] = {}
    for c in candidates:
        key = (c.pull_request_key, c.work_item_key)
        current = best.get(key)
        if current is None or _strength(c) < _strength(current):
            best[key] = c
    return best


def _strength(c: LinkCandidate) -> tuple[int, int]:
    return (0 if c.status is LinkStatus.VERIFIED else 1, c.method.rank)
