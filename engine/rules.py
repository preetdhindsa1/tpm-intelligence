"""Rule flags per feature (CLAUDE.md section 3: rule flags). Pure, no I/O.

Each flag is a deterministic fact with the evidence that produced it. Messages are
templates filled with computed values: no AI anywhere here.

=========================  ========  ==================================================
Code                       Severity  Fires when
=========================  ========  ==================================================
late_main_pr               warning   main PR opened within ``late_main_pr_days`` of freeze
main_pr_not_merged         critical  Code Freeze has passed and the main PR is unmerged
review_waiting             warning   open linked PR, no approval, waiting > N days
ci_failing                 warning   open linked PR with failing checks on its head commit
removed_at_freeze          critical  removed from the release within a window after freeze
readded_after_freeze       info      added back after freeze (exception evidence)
merged_after_freeze        warning   linked PR merged after freeze (shows exception status)
no_linked_prs              warning   tracked feature with no verified PR
=========================  ========  ==================================================

Unlinked PR load (reviewer and CI load from PRs not linked to any feature) is reported per
SIG at release level (``unlinked_open_load``), not as a per-feature flag: on real v1.38 data
a per-feature version fired on 80 of 106 features because most KEPs are owned by the
largest SIGs, so it carried no signal (decision 2026-11-21).

The "main PR" is the linked PR the author marked as the implementation (KEP number in the
title or an "implements ... KEP-N" phrase), else the most recently opened verified PR.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from engine.freeze import CodeStatus, check_pr
from engine.links import ReleaseLinks
from engine.projection import Feature, PullRequest, ReleaseInfo, World
from engine.review_rounds import DEFAULT_WINDOW, review_rounds


class Severity(StrEnum):
    """How much attention a flag needs."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RuleConfig:
    """Thresholds. Defaults are starting points, not measured optima."""

    review_round_window: timedelta = DEFAULT_WINDOW
    late_main_pr_days: int = 21
    review_wait_days: float = 7.0
    freeze_removal_window: timedelta = timedelta(days=3)


DEFAULT_RULES = RuleConfig()


@dataclass(frozen=True)
class Flag:
    """One rule result."""

    code: str
    severity: Severity
    message: str
    facts: Mapping[str, Any] = field(default_factory=dict)


def main_pr(
    pr_keys: Sequence[str], world: World, links: ReleaseLinks, feature_key: str
) -> PullRequest | None:
    """The implementation PR for a feature (see module docstring)."""
    prs = [world.pull_requests[k] for k in pr_keys if k in world.pull_requests]
    if not prs:
        return None
    declared = [
        pr
        for pr in prs
        if links.best[(pr.key, feature_key)].evidence.get("where") in ("title", "implements")
    ]
    pool = declared or prs
    return max(pool, key=lambda pr: (pr.created_at, pr.key))


def unlinked_open_load(world: World, links: ReleaseLinks) -> Counter[str]:
    """Open PRs without a verified link, counted per SIG label. Not per person."""
    linked = links.linked_pr_keys()
    load: Counter[str] = Counter()
    for pr in world.pull_requests.values():
        if pr.is_open and pr.key not in linked:
            for label in pr.labels:
                if label.startswith("sig/"):
                    load[label] += 1
    return load


def unlinked_open_prs(world: World, links: ReleaseLinks) -> int:
    """Distinct open PRs without a verified link, with or without a SIG label.

    The per-SIG counts above count a PR once per SIG label, so their sum is not a PR count.
    """
    linked = links.linked_pr_keys()
    return sum(1 for pr in world.pull_requests.values() if pr.is_open and pr.key not in linked)


def _days(delta: timedelta) -> float:
    return round(delta.total_seconds() / 86400, 1)


def evaluate_feature(
    feature: Feature,
    release: ReleaseInfo,
    world: World,
    links: ReleaseLinks,
    config: RuleConfig = DEFAULT_RULES,
) -> list[Flag]:
    """All flags for one feature as of ``world.as_of``."""
    flags: list[Flag] = []
    now, freeze = world.as_of, release.code_freeze_at
    pr_keys = [k for k in links.verified_prs(feature.key) if k in world.pull_requests]
    main = main_pr(pr_keys, world, links, feature.key)

    if feature.tracked and not pr_keys:
        flags.append(
            Flag(
                "no_linked_prs", Severity.WARNING, "Tracked feature has no verified linked PR.", {}
            )
        )

    if main is not None and freeze is not None:
        lead = freeze - main.created_at
        if timedelta(0) <= lead <= timedelta(days=config.late_main_pr_days):
            flags.append(
                Flag(
                    "late_main_pr",
                    Severity.WARNING,
                    f"Main PR {main.key} opened {_days(lead)} days before Code Freeze.",
                    {
                        "pull_request": main.key,
                        "opened_at": main.created_at.isoformat(),
                        "days_before_freeze": _days(lead),
                    },
                )
            )
        merged_by_freeze = main.merged_at is not None and main.merged_at <= freeze
        if now > freeze and not merged_by_freeze:
            flags.append(
                Flag(
                    "main_pr_not_merged",
                    Severity.CRITICAL,
                    f"Main PR {main.key} was not merged by Code Freeze.",
                    {
                        "pull_request": main.key,
                        "merged_at": main.merged_at.isoformat() if main.merged_at else None,
                    },
                )
            )

    for key in pr_keys:
        pr = world.pull_requests[key]
        if pr.is_open:
            flags.extend(_open_pr_flags(pr, now, config))
        if freeze is not None and pr.merged_at is not None and pr.merged_at > freeze:
            check = check_pr(pr, feature, release)
            exception = check.status is CodeStatus.MERGED_AFTER_FREEZE_WITH_EXCEPTION
            flags.append(
                Flag(
                    "merged_after_freeze",
                    Severity.WARNING,
                    f"{pr.key} merged {_days(pr.merged_at - freeze)} days after Code Freeze; "
                    + (
                        "exception evidence: re-added after freeze."
                        if exception
                        else "no exception evidence."
                    ),
                    {
                        "pull_request": pr.key,
                        "merged_at": pr.merged_at.isoformat(),
                        "status": check.status.value,
                        "exception_evidence_at": check.exception_evidence_at.isoformat()
                        if check.exception_evidence_at
                        else None,
                    },
                )
            )

    if freeze is not None:
        for m in feature.membership:
            if m.release_key != release.key:
                continue
            if not m.added and freeze <= m.at <= freeze + config.freeze_removal_window:
                flags.append(
                    Flag(
                        "removed_at_freeze",
                        Severity.CRITICAL,
                        f"Removed from {release.name} at Code Freeze ({m.at.isoformat()}).",
                        {"removed_at": m.at.isoformat()},
                    )
                )
            if m.added and m.at > freeze:
                flags.append(
                    Flag(
                        "readded_after_freeze",
                        Severity.INFO,
                        f"Added back to {release.name} after Code Freeze ({m.at.isoformat()}).",
                        {"readded_at": m.at.isoformat()},
                    )
                )

    return flags


def _open_pr_flags(pr: PullRequest, now: datetime, config: RuleConfig) -> list[Flag]:
    flags: list[Flag] = []
    rounds = review_rounds(pr, config.review_round_window)
    approved = any(r.outcome == "approved" for r in rounds)
    since = rounds[-1].ended_at if rounds else pr.created_at
    waiting = now - since
    if not approved and waiting > timedelta(days=config.review_wait_days):
        flags.append(
            Flag(
                "review_waiting",
                Severity.WARNING,
                f"{pr.key} has waited {_days(waiting)} days since its last review round "
                "without approval.",
                {
                    "pull_request": pr.key,
                    "waiting_days": _days(waiting),
                    "review_rounds": len(rounds),
                },
            )
        )
    failing = sorted(c.name for c in pr.checks if c.conclusion == "failure")
    if failing:
        flags.append(
            Flag(
                "ci_failing",
                Severity.WARNING,
                f"{pr.key} has {len(failing)} failing check(s) on its latest commit.",
                {"pull_request": pr.key, "failing_checks": failing},
            )
        )
    return flags
