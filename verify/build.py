"""Turn engine output into a fact sheet. Pure, no I/O.

Only verified links count (CLAUDE.md section 2.2): suggested PRs appear as a count, never as
linked PRs. Odds carry their validation status so a summary cannot present unvalidated odds
as reliable.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime

from engine.assess import FeatureAssessment, ReleaseAssessment
from verify.facts import Fact, FactKind, FactSheet, FactValue, fact_key

# Flag facts that are worth citing, with their kind. Anything else in Flag.facts is ignored.
_FLAG_FACT_KINDS: Mapping[str, FactKind] = {
    "pull_request": FactKind.LABEL,
    "opened_at": FactKind.DATE,
    "merged_at": FactKind.DATE,
    "removed_at": FactKind.DATE,
    "readded_at": FactKind.DATE,
    "exception_evidence_at": FactKind.DATE,
    "status": FactKind.LABEL,
    "days_before_freeze": FactKind.DURATION_DAYS,
    "waiting_days": FactKind.DURATION_DAYS,
    "review_rounds": FactKind.COUNT,
    "failing_checks": FactKind.COUNT,
}


@dataclass(frozen=True)
class OddsFacts:
    """Forecast output for one feature, as served by the API."""

    probability: float | None
    low: float | None
    high: float | None
    base_rate: float | None
    validated: bool


def build_fact_sheet(
    assessment: ReleaseAssessment, odds: Mapping[str, OddsFacts] | None = None
) -> FactSheet:
    """All citable facts for a release: release dates and counts, features, PRs, SIG load."""
    return FactSheet(_release_facts(assessment, odds or {}))


def _release_facts(a: ReleaseAssessment, odds: Mapping[str, OddsFacts]) -> Iterator[Fact]:
    r = a.release

    def rel(field: str, kind: FactKind, value: FactValue) -> Fact:
        return Fact(fact_key("release", field), kind, value)

    yield rel("name", FactKind.LABEL, r.name)
    yield rel("as_of", FactKind.DATE, a.as_of)
    for field, at in (
        ("enhancements_freeze_at", r.enhancements_freeze_at),
        ("code_freeze_at", r.code_freeze_at),
        ("release_at", r.release_at),
    ):
        if at is not None:
            yield rel(field, FactKind.DATE, at)
    current = [f for f in a.features if f.in_release]
    yield rel("features_in_release", FactKind.COUNT, len(current))
    yield rel("features_ever_in_release", FactKind.COUNT, len(a.features))
    yield rel("features_removed", FactKind.COUNT, len(a.features) - len(current))
    yield rel("features_tracked", FactKind.COUNT, sum(f.tracked for f in current))
    flag_counts = Counter(code for f in current for code in {fl.code for fl in f.flags})
    for code, n in sorted(flag_counts.items()):
        yield rel(f"features_with_flag.{code}", FactKind.COUNT, n)
    for sig, n in a.unlinked_open_prs_by_sig:
        yield Fact(fact_key("sig", "unlinked_open_prs", sig), FactKind.COUNT, n)

    seen_prs: set[str] = set()
    for f in a.features:
        yield from _feature_facts(f, odds.get(f.key))
        for p in f.pull_requests:
            if p.key in seen_prs:
                continue
            seen_prs.add(p.key)
            yield from _pr_facts(f, p.key)


def _feature_facts(f: FeatureAssessment, odds: OddsFacts | None) -> Iterator[Fact]:
    def fact(field: str, kind: FactKind, value: FactValue) -> Fact:
        return Fact(fact_key("feature", field, f.key), kind, value)

    yield fact("title", FactKind.LABEL, f.title)
    yield fact("in_release", FactKind.BOOLEAN, f.in_release)
    yield fact("tracked", FactKind.BOOLEAN, f.tracked)
    if f.stage is not None:
        yield fact("stage", FactKind.LABEL, f.stage)
    yield fact("prs.total", FactKind.COUNT, len(f.pull_requests))
    yield fact("prs.merged", FactKind.COUNT, sum(p.merged_at is not None for p in f.pull_requests))
    yield fact("prs.open", FactKind.COUNT, sum(p.state == "open" for p in f.pull_requests))
    yield fact("prs.suggested", FactKind.COUNT, len(f.suggested_pull_requests))
    main = next((p for p in f.pull_requests if p.is_main), None)
    if main is not None:
        yield fact("main_pr", FactKind.LABEL, main.key)
    yield fact("critical_path.length", FactKind.COUNT, len(f.critical_path))

    # Last time each timeline event happened (removal and re-add are what summaries cite).
    last: dict[str, datetime] = {}
    for e in f.timeline:
        if e.ref is None:
            last[e.kind] = e.at
    for kind in ("opted_in", "tracked", "untracked", "added_to_release", "removed_from_release"):
        if kind in last:
            yield fact(f"last_{kind}_at", FactKind.DATE, last[kind])

    emitted: set[str] = set()
    for flag in f.flags:
        key = fact_key("feature", f"flag.{flag.code}", f.key)
        if key not in emitted:
            emitted.add(key)
            yield Fact(key, FactKind.BOOLEAN, True)
            # Severity is a fact too, so a summary never calls a warning "critical".
            yield Fact(key + ".severity", FactKind.LABEL, flag.severity.value)
            # The rule's own sentence, so the meaning is not reinterpreted (e.g. "not
            # merged by Code Freeze" is not "not merged").
            yield Fact(key + ".message", FactKind.LABEL, flag.message)
        for name, value in flag.facts.items():
            fact_kind = _FLAG_FACT_KINDS.get(name)
            key = fact_key("feature", f"flag.{flag.code}.{name}", f.key)
            # Several flags of one code (e.g. two PRs waiting review) keep the first; the
            # PR facts carry the per-PR values.
            if fact_kind is None or value is None or key in emitted:
                continue
            emitted.add(key)
            yield Fact(key, fact_kind, _coerce(fact_kind, value))

    if odds is not None:
        yield fact("odds.validated", FactKind.BOOLEAN, odds.validated)
        for name, value in (
            ("probability", odds.probability),
            ("low", odds.low),
            ("high", odds.high),
            ("base_rate", odds.base_rate),
        ):
            if value is not None:
                yield fact(f"odds.{name}", FactKind.PROBABILITY, value)


def _coerce(kind: FactKind, value: object) -> FactValue:
    """Typed flag fact. A list (e.g. names of failing checks) counts as its length."""
    if kind is FactKind.DATE and isinstance(value, str):
        return datetime.fromisoformat(value)
    if kind is FactKind.COUNT and isinstance(value, list | tuple | set):
        return len(value)
    return value  # type: ignore[return-value]


def _pr_facts(f: FeatureAssessment, pr_key: str) -> Iterator[Fact]:
    p = next(p for p in f.pull_requests if p.key == pr_key)

    def fact(field: str, kind: FactKind, value: FactValue) -> Fact:
        return Fact(fact_key("pr", field, p.key), kind, value)

    yield fact("state", FactKind.LABEL, p.state)
    yield fact("created_at", FactKind.DATE, p.created_at)
    if p.merged_at is not None:
        yield fact("merged_at", FactKind.DATE, p.merged_at)
    yield fact("review_rounds", FactKind.COUNT, p.review_rounds)
    yield fact("failing_checks", FactKind.COUNT, p.failing_checks)
    yield fact("freeze_status", FactKind.LABEL, p.freeze.status.value)
