"""Go/no-go criteria from the release assessment and confirmed RAID items. Pure, no I/O.

Each criterion is ``pass``, ``fail`` or ``unknown`` with the facts behind it (ADR-0032).
``unknown`` means there is no data to decide; it is never a guess. Only features in the
release now count. No AI anywhere here: a person makes the go/no-go call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from engine.assess import FeatureAssessment, PRSummary, ReleaseAssessment
from engine.freeze import COUNTS, CodeStatus
from engine.rules import Severity
from modules.raid.store import RaidItem

Status = Literal["pass", "fail", "unknown"]
Verdict = Literal["ready", "not_ready", "unknown"]
ALL = ("code_merged", "no_critical_flags", "ci_green", "risks_owned", "docs_merged")
NAMES = {
    "code_merged": "Code merged or excepted",
    "no_critical_flags": "No open critical flags",
    "ci_green": "CI green",
    "risks_owned": "Every open risk has an owner",
    "docs_merged": "Docs merged",
}
MAX_EVIDENCE = 25  # per criterion; ``count`` always has the full number
_PHRASE = {
    CodeStatus.NOT_MERGED: "is not merged",
    CodeStatus.CLOSED_UNMERGED: "was closed without merging",
    CodeStatus.MERGED_AFTER_FREEZE_NO_EXCEPTION: "merged after the freeze, no exception evidence",
    CodeStatus.NO_FREEZE_DATE: "is not merged (the release has no freeze date)",
}
CI_NOTE = "Any failing check counts: the source does not mark required checks."


@dataclass(frozen=True)
class Evidence:
    text: str
    ref: str  # "feature:<key>", "pr:<key>" or "raid:<RAID_ID>"


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    status: Status
    detail: str
    count: int | None
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Readiness:
    release_key: str
    as_of: datetime
    verdict: Verdict
    criteria: tuple[Criterion, ...]


def _c(cid: str, status: Status, detail: str, count: int | None = None,
       evidence: Sequence[Evidence] = ()) -> Criterion:  # fmt: skip
    return Criterion(cid, NAMES[cid], status, detail, count, tuple(evidence[:MAX_EVIDENCE]))


def _main(f: FeatureAssessment) -> PRSummary | None:
    return next((p for p in f.pull_requests if p.is_main), None)


def code_merged(features: Sequence[FeatureAssessment]) -> Criterion:
    """Each feature's main PR merged by the freeze, or after it with exception evidence."""
    missing: list[Evidence] = []
    no_pr = 0
    for f in features:
        main = _main(f)
        if main is None:
            no_pr += 1
            continue
        status = main.freeze.status
        ok = status in COUNTS or (status is CodeStatus.NO_FREEZE_DATE and main.merged_at)
        if not ok:
            missing.append(Evidence(f"Main PR {main.key} {_PHRASE.get(status, status.value)}.",
                                    f"feature:{f.key}"))  # fmt: skip
    gap = (f" {no_pr} {'has' if no_pr == 1 else 'have'} no verified PR, so "
           f"{'it is' if no_pr == 1 else 'they are'} not counted.") if no_pr else ""  # fmt: skip
    if missing:
        n = len(missing)
        return _c("code_merged", "fail", f"{n} of {len(features)} features have a main PR "
                  f"that is not merged and has no exception.{gap}", n, missing)  # fmt: skip
    if not features or no_pr:
        return _c("code_merged", "unknown", f"No main PR fails.{gap}" if features
                  else "No features are in the release.", None)  # fmt: skip
    return _c("code_merged", "pass", f"All {len(features)} main PRs merged or excepted.", 0)


def _open(code: str, f: FeatureAssessment, ref: str | None) -> bool:
    """A critical flag stops being open when its documented resolution holds (ADR-0032)."""
    if code == "removed_at_freeze":
        return not f.in_release  # re-added after the freeze
    if code == "main_pr_not_merged":
        main = _main(f)
        return not (main and main.key == ref and main.freeze.status in COUNTS)
    return True


def no_critical_flags(features: Sequence[FeatureAssessment]) -> Criterion:
    """Critical rule flags on features in the release that are not resolved."""
    open_flags = [
        Evidence(flag.message, f"feature:{f.key}")
        for f in features
        for flag in f.flags
        if flag.severity is Severity.CRITICAL
        and _open(flag.code, f, flag.facts.get("pull_request"))
    ]
    n = len(open_flags)
    if n:
        return _c("no_critical_flags", "fail", f"{n} critical flags are open.", n, open_flags)
    return _c("no_critical_flags", "pass", "No critical flag is open.", 0)


def ci_green(features: Sequence[FeatureAssessment]) -> Criterion:
    """Open linked PRs with a failing check on their latest commit."""
    prs = {p.key: p for f in features for p in f.pull_requests}
    if not prs:
        return _c("ci_green", "unknown", "No linked PRs, so no CI data.", None)
    failing = [Evidence(f"{p.key} has {p.failing_checks} failing check(s).", f"pr:{p.key}")
               for p in prs.values() if p.state == "open" and p.failing_checks]  # fmt: skip
    if failing:
        n = len(failing)
        return _c("ci_green", "fail", f"{n} open PRs have failing checks. {CI_NOTE}", n, failing)
    return _c("ci_green", "pass", f"No open linked PR has a failing check. {CI_NOTE}", 0)


def risks_owned(items: Sequence[RaidItem]) -> Criterion:
    """Open confirmed RAID risks without an owner. Suggested items do not count."""
    risks = [i for i in items if i.type == "risk" and i.merge_into is None]
    confirmed = [i for i in risks if i.review in ("confirmed", "edited")]
    waiting = sum(i.review == "suggested" for i in risks)
    note = f" {waiting} suggested risks wait for review and do not count." if waiting else ""
    if not confirmed:
        return _c("risks_owned", "unknown", f"No confirmed RAID risks yet.{note}", None)
    live = [i for i in confirmed if i.status in ("open", "in_progress") and not i.owner]
    unowned = [Evidence(f"{i.raid_id}: {i.title} has no owner.", f"raid:{i.raid_id}")
               for i in live]  # fmt: skip
    if unowned:
        n = len(unowned)
        return _c("risks_owned", "fail", f"{n} open confirmed risks have no owner.{note}", n,
                  unowned)  # fmt: skip
    return _c("risks_owned", "pass", f"Every open confirmed risk has an owner.{note}", 0)


def docs_merged(features: Sequence[FeatureAssessment], docs_repos: Sequence[str]) -> Criterion:
    """Linked PRs in the team's docs repos are merged."""
    if not docs_repos:
        return _c("docs_merged", "unknown", "No docs repository is configured for this team.")
    docs = {p.key: p for f in features for p in f.pull_requests
            if p.key.split("#")[0] in docs_repos}  # fmt: skip
    if not docs:
        return _c("docs_merged", "unknown", "No docs PRs are linked to features in the release.")
    open_docs = [Evidence(f"Docs PR {p.key} is {p.state}, not merged.", f"pr:{p.key}")
                 for p in docs.values() if p.merged_at is None]  # fmt: skip
    if open_docs:
        n = len(open_docs)
        return _c("docs_merged", "fail", f"{n} of {len(docs)} docs PRs are not merged.", n,
                  open_docs)  # fmt: skip
    return _c("docs_merged", "pass", f"All {len(docs)} docs PRs are merged.", 0)


def verdict(criteria: Sequence[Criterion]) -> Verdict:
    """ready: every criterion passes; not_ready: any fails; else unknown."""
    statuses = {c.status for c in criteria}
    if "fail" in statuses:
        return "not_ready"
    return "unknown" if "unknown" in statuses or not criteria else "ready"


def evaluate(
    assessment: ReleaseAssessment,
    raid_items: Sequence[RaidItem] = (),
    criteria: Sequence[str] = ALL,
    docs_repos: Sequence[str] = (),
) -> Readiness:
    """The configured criteria for one release, as of the assessment's time."""
    features = [f for f in assessment.features if f.in_release]
    rules = {
        "code_merged": lambda: code_merged(features),
        "no_critical_flags": lambda: no_critical_flags(features),
        "ci_green": lambda: ci_green(features),
        "risks_owned": lambda: risks_owned(
            [i for i in raid_items if i.release_key == assessment.release.key]
        ),
        "docs_merged": lambda: docs_merged(features, docs_repos),
    }
    results = tuple(rules[c]() for c in criteria)
    return Readiness(assessment.release.key, assessment.as_of, verdict(results), results)
