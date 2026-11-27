"""Portfolio rules (ADR-0025): stage, bottleneck and next decision per program. Pure, no I/O.

Every text field is a template filled with computed numbers. No AI anywhere here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

# "verify" runs from the team's code-freeze date to the release (ADR-0025 addendum: it was
# called "freeze"; AI-native teams verify rather than freeze, and each team names the date).
STAGES = ("plan", "build", "verify", "launch", "learn")
LAUNCH_WINDOW = timedelta(days=7)
REVIEW_GAP_MIN_MERGED = 5  # pod rule R22: no rate from fewer than 5 merged PRs
_FLAG_DETAIL = {
    "main_pr_not_merged": "{n} features past {label} with the main PR not merged",
    "removed_at_freeze": "{n} features removed at {label}",
}


@dataclass(frozen=True)
class LabFacts:
    """Lab counts for a team with agent lanes (ADR-0023)."""

    merged: int
    approved_merged: int
    median_hours_to_merge: float | None
    unassigned: int
    # Pod facts (ADR-0023 addendum 2): merged people PRs (bots excluded) and how many had a
    # human review or comment before merge. None when the team has no pod facts.
    human_reviewed: int | None = None
    reviewed_of: int | None = None
    # PRs the human approved by merging them (ADR-0023 addendum 3), of ``reviewed_of``.
    human_approved: int | None = None


@dataclass(frozen=True)
class ProgramFacts:
    """Stored facts for one program's current release."""

    key: str
    project: str
    display_name: str
    release: str
    planning_tool: str
    code_tools: tuple[str, ...]
    as_of: datetime
    dates: dict[str, datetime | None]  # cycle_start_at, enhancements_freeze_at, ...
    features_in_release: int
    features_ever: int
    critical_codes: tuple[tuple[str, ...], ...]  # per in-release feature with a critical flag
    linked_features: int
    readded_after_freeze: int
    unlinked_open_prs: int
    draft_update_id: int | None = None
    suggested_links: int = 0
    lab: LabFacts | None = None
    code_freeze_label: str = "Code Freeze"  # the team's own name for its code_freeze date
    raid_suggested: int = 0  # RAID items waiting for a person (#225)
    has_retro: bool = False  # a retro replay is stored for this release (#252)


def stage(dates: dict[str, datetime | None], now: datetime) -> dict[str, Any]:
    """Calendar stage (ADR-0025 rule 2). ``current`` is None when a needed date is missing."""
    start, freeze, release = (
        dates.get(k) for k in ("cycle_start_at", "code_freeze_at", "release_at")
    )
    milestones = [
        (name, at)
        for name, at in (
            ("cycle_start", start),
            ("enhancements_freeze", dates.get("enhancements_freeze_at")),
            ("code_freeze", freeze),
            ("release", release),
            ("launch_end", release + LAUNCH_WINDOW if release else None),
        )
        if at is not None
    ]
    past = [m for m in milestones if m[1] <= now]
    ahead = [m for m in milestones if m[1] > now]
    current: str | None = None
    if start and freeze and release:
        bounds = (start, freeze, release, release + LAUNCH_WINDOW)
        current = STAGES[sum(1 for b in bounds if b <= now)]
    at = STAGES.index(current) if current else len(STAGES)
    nxt = ahead[0] if ahead else None
    return {
        "current": current,
        "stages": [
            {"name": s, "status": "done" if i < at else "current" if i == at else "upcoming"}
            for i, s in enumerate(STAGES)
        ]
        if current
        else [{"name": s, "status": "upcoming"} for s in STAGES],
        "last_milestone": {"name": past[-1][0], "at": past[-1][1]} if past else None,
        "next_milestone": {"name": nxt[0], "at": nxt[1]} if nxt else None,
        "days_to_next_milestone": (nxt[1].date() - now.date()).days if nxt else None,
    }


def _reviewed(lab: LabFacts) -> tuple[int, int, str]:
    """(reviewed, of, what) for the review gap.

    Human reviews from the pod facts when the team has them (ADR-0025 addendum 2): GitHub
    approvals cannot exist where every PR and review is posted from one account. Approvals
    otherwise.
    """
    if lab.human_reviewed is not None and lab.reviewed_of is not None:
        what = "a human review" if lab.human_approved is None else "a written human review"
        return lab.human_reviewed, lab.reviewed_of, what
    return lab.approved_merged, lab.merged, "an approving review"


def _approved(lab: LabFacts) -> str:
    """'88 approved by the human at merge, ' when the pod facts count it, else ''."""
    return (
        ""
        if lab.human_approved is None
        else f"{lab.human_approved} approved by the human at merge, "
    )


def _review_gap(lab: LabFacts | None) -> bool:
    if lab is None:
        return False
    n, of, _ = _reviewed(lab)
    return of >= REVIEW_GAP_MIN_MERGED and n * 2 < of


def _minutes(lab: LabFacts) -> int | None:
    hours = lab.median_hours_to_merge
    return None if hours is None else round(hours * 60)


def _row(
    kind: str, severity: str, headline: str, detail: str | None, **facts: Any
) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "headline": headline,
        "detail": detail,
        "facts": facts,
    }


def bottleneck(p: ProgramFacts, current_stage: str | None) -> dict[str, Any]:
    """The first rule that fires (ADR-0025 rule 4)."""
    if p.critical_codes:
        counts = Counter(code for codes in p.critical_codes for code in set(codes))
        top, n = min(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        k = len(p.critical_codes)
        template = _FLAG_DETAIL.get(top, "{n} features flagged " + top)
        detail = template.format(n=n, label=p.code_freeze_label)
        headline = f"{k} critical flag{'s' if k != 1 else ''}"
        return _row(
            "critical_flags",
            "critical",
            headline,
            detail,
            critical_features=k,
            top_flag=top,
            top_flag_features=n,
        )
    if p.lab is not None and _review_gap(p.lab):
        n, of, what = _reviewed(p.lab)
        detail = f"{of} pull requests merged, {_approved(p.lab)}{n} with {what}"
        return _row("review_gap", "warning", "Review gap", detail, **_gap_facts(p.lab))
    n, linked = p.features_in_release, p.linked_features
    if current_stage in STAGES[1:] and n > linked:
        return _row(
            "linking_gap",
            "warning",
            f"{n - linked} of {n} features have no linked code",
            f"{linked} of {n} features in the release are linked to a pull request",
            features_in_release=n,
            linked_features=linked,
            unlinked_features=n - linked,
        )
    if p.unlinked_open_prs > 0:
        return _row(
            "unlinked_load",
            "info",
            f"{p.unlinked_open_prs:,} open pull requests not linked to a feature",
            "They still use the same reviewers and CI",
            unlinked_open_prs=p.unlinked_open_prs,
        )
    return _row("none", "info", "No bottleneck flagged", None)


def _gap_facts(lab: LabFacts) -> dict[str, Any]:
    return {
        "merged": lab.merged,
        "approved_merged": lab.approved_merged,
        "median_minutes_to_merge": _minutes(lab),
        "human_reviewed": lab.human_reviewed,
        "reviewed_of": lab.reviewed_of,
        "human_approved": lab.human_approved,
    }


_DECISION_LABEL = {
    "approve_exec_update": "Approve exec update",
    "review_link_suggestions": "Review AI link suggestions",
    "review_raid": "Review RAID items",
    "classify_prs": "Classify pull requests with no lane",
}


def waiting(p: ProgramFacts) -> list[dict[str, Any]]:
    """Approvals this program waits on, in ADR-0025 rule 5 order."""
    items: list[tuple[str, str, int, dict[str, int] | None]] = []
    if p.draft_update_id is not None:
        label = f"{p.display_name} {p.release} exec update · draft"
        items.append(("approve_exec_update", label, 1, {"update_id": p.draft_update_id}))
    if p.suggested_links > 0:
        label = f"{p.suggested_links} AI link suggestions · {p.release}"
        items.append(("review_link_suggestions", label, p.suggested_links, None))
    if p.raid_suggested > 0:
        n = p.raid_suggested
        label = f"{n} RAID item{'s' if n != 1 else ''} waiting for review · {p.release}"
        items.append(("review_raid", label, n, None))
    if p.lab is not None and p.lab.unassigned > 0:
        n = p.lab.unassigned
        label = f"{n} pull request{'s' if n != 1 else ''} with no lane · {p.display_name}"
        items.append(("classify_prs", label, n, None))
    return [
        {"kind": k, "program_key": p.key, "label": label, "count": c, "ref": ref}
        for k, label, c, ref in items
    ]


def program(p: ProgramFacts) -> dict[str, Any]:
    """One Portfolio row from its facts (contract field order)."""
    st = stage(p.dates, p.as_of)
    first = next(iter(waiting(p)), None)
    decision = None
    if first is not None:
        decision = {
            "kind": first["kind"],
            "label": _DECISION_LABEL[first["kind"]],
            "count": first["count"],
            "ref": first["ref"],
        }
    return {
        "key": p.key,
        "project": p.project,
        "display_name": p.display_name,
        "release": p.release,
        "planning_tool": p.planning_tool,
        "code_tools": list(p.code_tools),
        "has_lab": p.lab is not None,
        "has_retro": p.has_retro,
        "code_freeze_label": p.code_freeze_label,
        "as_of": p.as_of,
        "dates": p.dates,
        "stage": st,
        "scope": {"features_in_release": p.features_in_release, "features_ever": p.features_ever},
        "bottleneck": bottleneck(p, st["current"]),
        "next_decision": decision,
    }


def _pattern(kind: str, title: str, text: str, p: ProgramFacts, **facts: Any) -> dict[str, Any]:
    return {"kind": kind, "title": title, "text": text, "program_key": p.key, "facts": facts}


def across(facts: list[ProgramFacts]) -> list[dict[str, Any]]:
    """Templated patterns, each only when its fact is above zero (ADR-0025 rule 7)."""
    out = [
        _pattern(
            "late_code",
            "Code lands late, not never",
            f"{p.display_name} {p.release}: {p.readded_after_freeze} features were removed "
            "at the freeze and later re-added.",
            p,
            readded_after_freeze=p.readded_after_freeze,
        )
        for p in facts
        if p.readded_after_freeze > 0
    ]
    for p in facts:
        if p.lab is not None and _review_gap(p.lab):
            m = _minutes(p.lab)
            speed = f"merge in a median of {m} minutes, and " if m is not None else ""
            n, of, what = _reviewed(p.lab)
            a = p.lab.human_approved
            gap = (
                f"{n} of {of} had {what}."
                if a is None
                else f"{a} of {of} were approved by the human at merge and {n} had {what}."
            )
            text = f"{p.display_name}: pull requests {speed}{gap}"
            out.append(
                _pattern("review_gap", "Review is the new bottleneck", text, p, **_gap_facts(p.lab))
            )
    out += [
        _pattern(
            "unlinked_load",
            "Unlinked work is real load",
            f"{p.unlinked_open_prs:,} open {p.display_name} pull requests are not linked to "
            "any feature but still use the same reviewers.",
            p,
            unlinked_open_prs=p.unlinked_open_prs,
        )
        for p in facts
        if p.unlinked_open_prs > 0
    ]
    return out


COMING_NEXT = (
    {"module": "raid", "name": "RAID tracker", "status": "planned"},
    {"module": "readiness", "name": "Release readiness", "status": "planned"},
    {"module": "retro", "name": "Retro insights", "status": "planned"},
)


def _sort_key(p: ProgramFacts) -> tuple[datetime, str]:
    """Release date, then key (ADR-0025 rule 1). Undated releases go last."""
    return (p.dates.get("release_at") or datetime.max.replace(tzinfo=p.as_of.tzinfo), p.key)


def coming_next(
    live: frozenset[str] = frozenset(), validated: dict[str, bool] | None = None
) -> list[dict[str, Any]]:
    """The Wave 4/5 modules; ``live`` names those with real data (#225), else ``planned``.

    ``validated`` (#252): True or False for a module with a backtested model (readiness),
    None for one with no model to validate (RAID items, retro facts), so a live but
    unvalidated module can say so (CLAUDE.md principle 5).
    """
    known = validated or {}
    return [{**m, "status": "live" if m["module"] in live else "planned",
             "validated": known.get(m["module"])} for m in COMING_NEXT]  # fmt: skip


def portfolio(
    facts: list[ProgramFacts],
    skipped: list[dict[str, str]],
    now: datetime,
    live: frozenset[str] = frozenset(),
    validated: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """The whole ``GET /portfolio`` body (docs/api/ux-v1-contract.md)."""
    facts = sorted(facts, key=_sort_key)
    order = list(_DECISION_LABEL)
    # Kind order, then program order (sorted() is stable).
    items = sorted((i for p in facts for i in waiting(p)), key=lambda i: order.index(i["kind"]))
    return {
        "as_of": min((p.as_of for p in facts), default=now),
        "totals": {
            "programs": len(facts),
            "planning_tools": sorted({p.planning_tool for p in facts}),
            "waiting_on_you": len(items),
        },
        "programs": [program(p) for p in facts],
        "waiting_on_you": items,
        "across_programs": across(facts),
        "coming_next": coming_next(live, validated),
        "skipped": skipped,
    }
