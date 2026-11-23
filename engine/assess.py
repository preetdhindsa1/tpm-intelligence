"""Release and feature assessment: the facts the API serves. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from engine.freeze import FreezeCheck, check_pr
from engine.graph import build_graph, critical_path
from engine.links import ReleaseLinks, link_release
from engine.projection import Feature, ReleaseInfo, World
from engine.review_rounds import review_rounds
from engine.rules import (
    DEFAULT_RULES,
    Flag,
    RuleConfig,
    evaluate_feature,
    main_pr,
    unlinked_open_load,
)

_TIMELINE_LABELS = {
    "lead-opted-in": "opted_in",
    "tracked/yes": "tracked",
    "tracked/no": "untracked",
}


@dataclass(frozen=True)
class TimelineEntry:
    """One dated fact on a feature's timeline."""

    at: datetime
    kind: str  # opted_in, added_to_release, tracked, pr_opened, code_freeze, ...
    ref: str | None = None


@dataclass(frozen=True)
class PRSummary:
    """Per-PR facts for a feature."""

    key: str
    title: str
    state: str
    created_at: datetime
    merged_at: datetime | None
    review_rounds: int
    review_records: int
    failing_checks: int
    freeze: FreezeCheck
    is_main: bool


@dataclass(frozen=True)
class FeatureAssessment:
    """Everything computed for one feature."""

    key: str
    title: str
    in_release: bool
    tracked: bool
    stage: str | None
    teams: tuple[str, ...]
    pull_requests: tuple[PRSummary, ...]
    suggested_pull_requests: tuple[str, ...]
    flags: tuple[Flag, ...]
    critical_path: tuple[str, ...]
    timeline: tuple[TimelineEntry, ...]


@dataclass(frozen=True)
class ReleaseAssessment:
    """All features of a release as of ``as_of``."""

    release: ReleaseInfo
    as_of: datetime
    features: tuple[FeatureAssessment, ...]
    unlinked_open_prs_by_sig: tuple[tuple[str, int], ...]


def feature_timeline(
    feature: Feature, release: ReleaseInfo, world: World, pr_keys: Iterable[str]
) -> list[TimelineEntry]:
    """Release dates, membership and tracking changes, and linked PR events, by time."""
    entries: list[TimelineEntry] = []
    for kind, at in (
        ("enhancements_freeze", release.enhancements_freeze_at),
        ("code_freeze", release.code_freeze_at),
        ("release", release.release_at),
    ):
        if at is not None:
            entries.append(TimelineEntry(at, kind))
    for m in feature.membership:
        if m.release_key == release.key:
            entries.append(
                TimelineEntry(m.at, "added_to_release" if m.added else "removed_from_release")
            )
    for c in feature.label_history:
        if c.added and c.label in _TIMELINE_LABELS:
            entries.append(TimelineEntry(c.at, _TIMELINE_LABELS[c.label]))
    for key in pr_keys:
        pr = world.pull_requests.get(key)
        if pr is None:
            continue
        entries.append(TimelineEntry(pr.created_at, "pr_opened", key))
        if pr.merged_at:
            entries.append(TimelineEntry(pr.merged_at, "pr_merged", key))
        elif pr.closed_at:
            entries.append(TimelineEntry(pr.closed_at, "pr_closed", key))
    return sorted(entries, key=lambda e: (e.at, e.kind, e.ref or ""))


def assess_release(
    world: World,
    release_key: str,
    config: RuleConfig = DEFAULT_RULES,
    links: ReleaseLinks | None = None,
) -> ReleaseAssessment:
    """Assess every feature that is or was in the release.

    ``links`` is the release's linking if the caller already has it (P3-M4: link once
    per recompute); it must be ``link_release(world, release_key)``.
    """
    release = world.releases[release_key]
    links = links if links is not None else link_release(world, release_key)
    sig_load = unlinked_open_load(world, links)
    features = world.features_ever_in(release_key)
    graph = build_graph(release_key, features, world.pull_requests, links.by_feature())
    assessed = tuple(_assess(f, release, world, links, graph, config) for f in features)
    return ReleaseAssessment(
        release=release,
        as_of=world.as_of,
        features=assessed,
        unlinked_open_prs_by_sig=tuple(sorted(sig_load.items(), key=lambda kv: (-kv[1], kv[0]))),
    )


def _assess(
    f: Feature,
    release: ReleaseInfo,
    world: World,
    links: ReleaseLinks,
    graph: nx.DiGraph[str],
    config: RuleConfig,
) -> FeatureAssessment:
    pr_keys = [k for k in links.verified_prs(f.key) if k in world.pull_requests]
    main = main_pr(pr_keys, world, links, f.key)
    summaries: list[PRSummary] = []
    for key in pr_keys:
        pr = world.pull_requests[key]
        rounds = review_rounds(pr, config.review_round_window)
        summaries.append(
            PRSummary(
                key=pr.key,
                title=pr.title,
                state=pr.state,
                created_at=pr.created_at,
                merged_at=pr.merged_at,
                review_rounds=len(rounds),
                review_records=len(pr.reviews),
                failing_checks=sum(1 for c in pr.checks if c.conclusion == "failure"),
                freeze=check_pr(pr, f, release),
                is_main=main is not None and pr.key == main.key,
            )
        )
    return FeatureAssessment(
        key=f.key,
        title=f.title,
        in_release=release.key in f.release_keys,
        tracked=f.tracked,
        stage=f.stage,
        teams=tuple(sorted(f.teams)),
        pull_requests=tuple(summaries),
        suggested_pull_requests=tuple(links.suggested_prs(f.key)),
        flags=tuple(evaluate_feature(f, release, world, links, config)),
        critical_path=tuple(critical_path(graph, f.key, world.pull_requests)),
        timeline=tuple(feature_timeline(f, release, world, pr_keys)),
    )
