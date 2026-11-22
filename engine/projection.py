"""Rebuild the world as it was at a point in time from normalized events. Pure, no I/O.

Backtest rule (CLAUDE.md section 6): only data dated before the prediction point.

* **Time-varying facts** are rebuilt strictly from events with ``occurred_at < as_of``:
  release membership, labels, PR existence and state (open/merged/closed), merge and close
  times, reviews and CI results.
* **Text fields** (issue description = tracking list, PR title/body, kep.yaml feature
  gates) come from the latest snapshot because GitHub keeps no history of them. This is an
  approximation: text edited after ``as_of`` can leak in. Its reach is limited because a PR
  only exists in the projection if it was created before ``as_of`` (see ADR-0005).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from linker.rules import LinkCandidate
from pipeline.events import (
    ChangeAction,
    CheckCompleted,
    NormalizedEvent,
    PullRequestObserved,
    ReleaseObserved,
    ReviewSubmitted,
    WorkItemLabelChanged,
    WorkItemObserved,
    WorkItemReleaseChanged,
    WorkItemSpecObserved,
)

PRState = Literal["open", "merged", "closed"]


@dataclass(frozen=True)
class ReleaseInfo:
    """A release and its key dates."""

    key: str  # "kubernetes:v1.38"
    name: str
    cycle_start_at: datetime | None
    enhancements_freeze_at: datetime | None
    code_freeze_at: datetime | None
    release_at: datetime | None


@dataclass(frozen=True)
class MembershipChange:
    """Added to / removed from a release at a time."""

    at: datetime
    release_key: str
    added: bool


@dataclass(frozen=True)
class LabelChange:
    """Label added / removed at a time."""

    at: datetime
    label: str
    added: bool


@dataclass(frozen=True)
class Feature:
    """A planning work item as of ``World.as_of``."""

    key: str
    number: int
    title: str
    url: str | None
    description: str
    labels: frozenset[str]
    release_keys: frozenset[str]
    membership: tuple[MembershipChange, ...]
    label_history: tuple[LabelChange, ...]
    feature_flags: tuple[str, ...] = ()
    stage: str | None = None
    owning_team: str | None = None
    participating_teams: tuple[str, ...] = ()

    @property
    def tracked(self) -> bool:
        """Release-team tracking label present."""
        return "tracked/yes" in self.labels

    @property
    def owning_sig(self) -> str | None:
        """Owning SIG as a label (``sig/storage``) from kep.yaml, else the only SIG label."""
        if self.owning_team:
            return f"sig/{self.owning_team.removeprefix('sig-')}"
        sigs = sorted(label for label in self.labels if label.startswith("sig/"))
        return sigs[0] if len(sigs) == 1 else None

    @property
    def teams(self) -> frozenset[str]:
        """SIGs from labels plus kep.yaml owners."""
        sigs = {label for label in self.labels if label.startswith("sig/")}
        if self.owning_team:
            sigs.add(f"sig/{self.owning_team.removeprefix('sig-')}")
        return frozenset(sigs)


@dataclass(frozen=True)
class Review:
    """One review record."""

    id: str
    reviewer: str | None
    state: str
    submitted_at: datetime


@dataclass(frozen=True)
class Check:
    """One CI result on the head commit."""

    name: str
    conclusion: str
    at: datetime


@dataclass(frozen=True)
class PullRequest:
    """A PR as of ``World.as_of``."""

    key: str
    repo: str
    number: int
    title: str
    body: str
    author: str | None
    labels: tuple[str, ...]
    created_at: datetime
    state: PRState
    merged_at: datetime | None
    closed_at: datetime | None
    reviews: tuple[Review, ...]
    checks: tuple[Check, ...]

    @property
    def is_open(self) -> bool:
        """Neither merged nor closed as of the projection time."""
        return self.state == "open"


@dataclass(frozen=True)
class World:
    """Everything the engine knows at ``as_of``."""

    as_of: datetime
    releases: Mapping[str, ReleaseInfo]
    features: Mapping[str, Feature]
    pull_requests: Mapping[str, PullRequest]
    # Links from outside the event log: AI suggestions and people's decisions on them
    # (ADR-0011). ``engine.links.link_release`` merges them; only a person's confirmation
    # makes one verified.
    extra_links: tuple[LinkCandidate, ...] = ()

    def features_in(self, release_key: str) -> list[Feature]:
        """Features currently in a release (removed ones excluded), sorted by key."""
        return sorted(
            (f for f in self.features.values() if release_key in f.release_keys),
            key=lambda f: f.key,
        )

    def features_ever_in(self, release_key: str) -> list[Feature]:
        """Features that were in the release at any point up to ``as_of`` (incl. removed)."""
        return sorted(
            (
                f
                for f in self.features.values()
                if any(m.release_key == release_key for m in f.membership)
                or release_key in f.release_keys
            ),
            key=lambda f: f.key,
        )


def _latest[T](current: tuple[datetime, T] | None, at: datetime, value: T) -> tuple[datetime, T]:
    return (at, value) if current is None or at >= current[0] else current


def project(events: Iterable[NormalizedEvent], as_of: datetime) -> World:
    """Fold events into a :class:`World` as of ``as_of`` (see module docstring)."""
    releases: dict[str, ReleaseInfo] = {}
    item_snap: dict[str, tuple[datetime, WorkItemObserved]] = {}
    spec_snap: dict[str, tuple[datetime, WorkItemSpecObserved]] = {}
    membership: dict[str, list[MembershipChange]] = defaultdict(list)
    label_hist: dict[str, list[LabelChange]] = defaultdict(list)
    pr_snap: dict[str, tuple[datetime, PullRequestObserved]] = {}
    reviews: dict[str, dict[str, Review]] = defaultdict(dict)
    checks: dict[str, dict[str, Check]] = defaultdict(dict)

    for e in events:
        key, p, at = e.subject.external_key, e.payload, e.occurred_at
        if isinstance(p, ReleaseObserved):
            releases[key] = ReleaseInfo(
                key,
                p.name,
                p.cycle_start_at,
                p.enhancements_freeze_at,
                p.code_freeze_at,
                p.release_at,
            )
        elif isinstance(p, WorkItemObserved):
            item_snap[key] = _latest(item_snap.get(key), at, p)
        elif isinstance(p, WorkItemSpecObserved):
            spec_snap[key] = _latest(spec_snap.get(key), at, p)
        elif isinstance(p, PullRequestObserved):
            pr_snap[key] = _latest(pr_snap.get(key), at, p)
        elif at >= as_of:
            continue  # every remaining type is a time-varying fact
        elif isinstance(p, WorkItemReleaseChanged):
            membership[key].append(
                MembershipChange(at, p.release_key, p.action is ChangeAction.ADDED)
            )
        elif isinstance(p, WorkItemLabelChanged):
            label_hist[key].append(LabelChange(at, p.label, p.action is ChangeAction.ADDED))
        elif isinstance(p, ReviewSubmitted):
            reviews[key][p.review_id] = Review(
                p.review_id, p.reviewer, p.state.value, p.submitted_at
            )
        elif isinstance(p, CheckCompleted):
            prev = checks[key].get(p.check_name)
            if prev is None or at >= prev.at:
                checks[key][p.check_name] = Check(p.check_name, p.conclusion.value, at)

    features = {
        key: _feature(key, snap, spec_snap.get(key), membership[key], label_hist[key], as_of)
        for key, (_, snap) in item_snap.items()
        if snap.created_at < as_of
    }
    prs = {
        key: _pull_request(key, snap, reviews[key], checks[key], as_of)
        for key, (_, snap) in pr_snap.items()
        if snap.created_at < as_of
    }
    return World(as_of=as_of, releases=releases, features=features, pull_requests=prs)


def _fold(changes: Iterable[tuple[datetime, str, bool]]) -> frozenset[str]:
    state: set[str] = set()
    for _, name, added in sorted(changes, key=lambda c: c[0]):
        (state.add if added else state.discard)(name)
    return frozenset(state)


def _feature(
    key: str,
    snap: WorkItemObserved,
    spec: tuple[datetime, WorkItemSpecObserved] | None,
    membership: list[MembershipChange],
    labels: list[LabelChange],
    as_of: datetime,
) -> Feature:
    membership.sort(key=lambda m: m.at)
    labels.sort(key=lambda c: c.at)
    s = spec[1] if spec else None
    return Feature(
        key=key,
        number=int(key.rsplit("#", 1)[1]),
        title=snap.title,
        url=snap.url,
        description=snap.description,
        labels=_fold((c.at, c.label, c.added) for c in labels),
        release_keys=_fold((m.at, m.release_key, m.added) for m in membership),
        membership=tuple(membership),
        label_history=tuple(labels),
        feature_flags=s.feature_flags if s else (),
        stage=s.stage if s else None,
        owning_team=s.owning_team if s else None,
        participating_teams=s.participating_teams if s else (),
    )


def _pull_request(
    key: str,
    snap: PullRequestObserved,
    reviews: Mapping[str, Review],
    checks: Mapping[str, Check],
    as_of: datetime,
) -> PullRequest:
    merged = snap.merged_at if snap.merged_at and snap.merged_at < as_of else None
    closed = snap.closed_at if snap.closed_at and snap.closed_at < as_of else None
    state: PRState = "merged" if merged else ("closed" if closed else "open")
    # Only the latest commit's checks are known; they only apply while the PR is that commit.
    known_checks = tuple(sorted(checks.values(), key=lambda c: c.name)) if snap.head_sha else ()
    return PullRequest(
        key=key,
        repo=snap.repo,
        number=snap.number,
        title=snap.title,
        body=snap.body,
        author=snap.author,
        labels=snap.labels,
        created_at=snap.created_at,
        state=state,
        merged_at=merged,
        closed_at=closed,
        reviews=tuple(sorted(reviews.values(), key=lambda r: (r.submitted_at, r.id))),
        checks=known_checks,
    )
