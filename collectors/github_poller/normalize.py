"""Pure functions: raw GitHub JSON -> normalized events. No I/O.

Mapping notes
-------------
* A KEP enhancement issue is a ``feature`` work item keyed ``kubernetes/enhancements#N``.
* Issue status: ``open`` -> ``in_progress``, ``closed`` -> ``done``. Whether a feature
  actually lands is decided by the engine from PRs, not from this field.
* Milestone events become ``work_item.release_changed``. Label events (``tracked/yes``,
  ``tracked/no``, ``lead-opted-in``, ...) become ``work_item.label_changed``. The engine
  interprets the labels; the collector does not.
* Event IDs derive from GitHub's own IDs (issue event ``id``, review ``databaseId``) or,
  for snapshots, from ``updated_at``, so re-polling yields identical IDs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

import yaml

from collectors.github_poller.calendar import ReleaseDates
from pipeline.events import (
    ChangeAction,
    CheckCompleted,
    CheckConclusion,
    CommentPosted,
    CommitNote,
    MergeabilityObserved,
    NormalizedEvent,
    PullRequestObserved,
    ReleaseObserved,
    ReviewState,
    ReviewSubmitted,
    Source,
    SubjectKind,
    SubjectRef,
    WorkItemLabelChanged,
    WorkItemObserved,
    WorkItemReleaseChanged,
    WorkItemSpecObserved,
    WorkItemStatusChanged,
    WorkItemType,
    new_event,
    release_key,
)

Json = Mapping[str, Any]

_KEP_PATH = re.compile(r"^keps/[^/]+/(\d+)-[^/]+/kep\.yaml$")


class _NoDatesLoader(yaml.SafeLoader):
    """SafeLoader that keeps date-like scalars as strings.

    Real kep.yaml files contain invalid dates (a v1.38 backfill on 2026-11-21 hit
    "month must be in 1..12"); we never need dates from kep.yaml.
    """


_NoDatesLoader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class SpecParseError(ValueError):
    """A spec file (kep.yaml) could not be parsed."""


_PR_STATES: dict[str, Literal["open", "closed", "merged"]] = {
    "OPEN": "open",
    "CLOSED": "closed",
    "MERGED": "merged",
}
_REVIEW_STATES = {
    "APPROVED": ReviewState.APPROVED,
    "CHANGES_REQUESTED": ReviewState.CHANGES_REQUESTED,
    "COMMENTED": ReviewState.COMMENTED,
    "DISMISSED": ReviewState.DISMISSED,
}
_STATUS_CONTEXT_STATES = {
    "SUCCESS": CheckConclusion.SUCCESS,
    "FAILURE": CheckConclusion.FAILURE,
    "ERROR": CheckConclusion.FAILURE,
    "PENDING": CheckConclusion.PENDING,
    "EXPECTED": CheckConclusion.PENDING,
}
_CHECK_RUN_CONCLUSIONS = {
    "SUCCESS": CheckConclusion.SUCCESS,
    "FAILURE": CheckConclusion.FAILURE,
    "TIMED_OUT": CheckConclusion.FAILURE,
    "STARTUP_FAILURE": CheckConclusion.FAILURE,
    "ACTION_REQUIRED": CheckConclusion.FAILURE,
    "CANCELLED": CheckConclusion.CANCELLED,
    "SKIPPED": CheckConclusion.SKIPPED,
    "NEUTRAL": CheckConclusion.NEUTRAL,
    "STALE": CheckConclusion.NEUTRAL,
}


def parse_ts(value: str) -> datetime:
    """Parse GitHub's ISO-8601 ``...Z`` timestamps into aware datetimes."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def work_item_ref(repo: str, number: int) -> SubjectRef:
    """Subject for an enhancement issue."""
    return SubjectRef(
        kind=SubjectKind.WORK_ITEM, source=Source.GITHUB, external_key=f"{repo}#{number}"
    )


def pull_request_ref(repo: str, number: int) -> SubjectRef:
    """Subject for a pull request."""
    return SubjectRef(
        kind=SubjectKind.PULL_REQUEST, source=Source.GITHUB, external_key=f"{repo}#{number}"
    )


# ---------------------------------------------------------------- releases


def release_event(project: str, dates: ReleaseDates, observed_at: datetime) -> NormalizedEvent:
    """``release.observed`` from the checked-in calendar."""
    key = release_key(project, dates.name)
    payload = ReleaseObserved(
        project=project,
        name=dates.name,
        cycle_start_at=dates.cycle_start,
        enhancements_freeze_at=dates.enhancements_freeze,
        code_freeze_at=dates.code_freeze,
        release_at=dates.release,
        source_url=dates.source_url,
    )
    return new_event(
        source=Source.GITHUB,
        subject=SubjectRef(kind=SubjectKind.RELEASE, source=Source.GITHUB, external_key=key),
        occurred_at=dates.cycle_start,
        observed_at=observed_at,
        payload=payload,
        identity=(payload.model_dump_json(),),
    )


# ---------------------------------------------------------------- issues


# Shared with the webhook normalizer (ADR-0020); REST sends the same values lowercase.
REVIEW_STATES = _REVIEW_STATES
CHECK_RUN_CONCLUSIONS = _CHECK_RUN_CONCLUSIONS


def is_pull_request(issue: Json) -> bool:
    """The REST issues list also returns PRs; they carry a ``pull_request`` key."""
    return "pull_request" in issue


_TIMELINE_KINDS = {
    "MilestonedEvent": "milestoned",
    "DemilestonedEvent": "demilestoned",
    "LabeledEvent": "labeled",
    "UnlabeledEvent": "unlabeled",
    "ClosedEvent": "closed",
    "ReopenedEvent": "reopened",
}


def timeline_to_events(nodes: Iterable[Json]) -> list[dict[str, Any]]:
    """Convert GraphQL ``timelineItems`` nodes to the issue-event shape used below.

    ``{"id", "event", "created_at", "milestone": {"title"}, "label": {"name"}}``. IDs are
    GraphQL node IDs, which are stable across polls.
    """
    out: list[dict[str, Any]] = []
    for node in nodes:
        kind = _TIMELINE_KINDS.get(node.get("__typename", ""))
        if kind is None:
            continue
        event: dict[str, Any] = {"id": node["id"], "event": kind, "created_at": node["createdAt"]}
        if "milestoneTitle" in node:
            event["milestone"] = {"title": node["milestoneTitle"]}
        if node.get("label"):
            event["label"] = {"name": node["label"]["name"]}
        out.append(event)
    return out


def issue_in_release(issue: Json, events: Iterable[Json], release_name: str) -> bool:
    """True if the issue is, or ever was, in milestone ``release_name``.

    Using event history keeps issues that were removed (demilestoned) visible: #6395 had
    no milestone between 2026-11-17 12:05Z and 2026-11-21 00:33Z.
    """
    milestone = issue.get("milestone") or {}
    if milestone.get("title") == release_name:
        return True
    return any(
        e.get("event") in ("milestoned", "demilestoned")
        and (e.get("milestone") or {}).get("title") == release_name
        for e in events
    )


def issue_snapshot(
    issue: Json, *, repo: str, project: str, observed_at: datetime
) -> NormalizedEvent:
    """``work_item.observed`` for an enhancement issue."""
    milestone = (issue.get("milestone") or {}).get("title")
    closed = issue["state"] == "closed"
    state = f"closed:{issue.get('state_reason') or 'completed'}" if closed else "open"
    payload = WorkItemObserved(
        item_type=WorkItemType.FEATURE,
        title=issue["title"],
        state=state,
        status_category="done" if closed else "in_progress",
        labels=tuple(sorted(label["name"] for label in issue.get("labels", []))),
        release_keys=(release_key(project, milestone),) if milestone else (),
        url=issue.get("html_url"),
        description=issue.get("body") or "",
        created_at=parse_ts(issue["created_at"]),
        updated_at=parse_ts(issue["updated_at"]),
    )
    return new_event(
        source=Source.GITHUB,
        subject=work_item_ref(repo, issue["number"]),
        occurred_at=payload.updated_at,
        observed_at=observed_at,
        payload=payload,
        identity=(issue["updated_at"],),
    )


def issue_history(
    events: Iterable[Json], *, repo: str, number: int, project: str, observed_at: datetime
) -> list[NormalizedEvent]:
    """Milestone, label and open/closed changes from issue events (see ``timeline_to_events``).

    Other event types (assigned, subscribed, mentioned, project board changes) are ignored.
    """
    subject = work_item_ref(repo, number)
    out: list[NormalizedEvent] = []
    for e in events:
        kind = e.get("event")
        occurred = parse_ts(e["created_at"])
        payload: WorkItemReleaseChanged | WorkItemLabelChanged | WorkItemStatusChanged
        if kind in ("milestoned", "demilestoned"):
            payload = WorkItemReleaseChanged(
                action=ChangeAction.ADDED if kind == "milestoned" else ChangeAction.REMOVED,
                release_key=release_key(project, e["milestone"]["title"]),
            )
        elif kind in ("labeled", "unlabeled"):
            payload = WorkItemLabelChanged(
                action=ChangeAction.ADDED if kind == "labeled" else ChangeAction.REMOVED,
                label=e["label"]["name"],
            )
        elif kind in ("closed", "reopened"):
            closing = kind == "closed"
            payload = WorkItemStatusChanged(
                from_state="open" if closing else "closed",
                to_state="closed" if closing else "open",
                to_category="done" if closing else "in_progress",
            )
        else:
            continue
        out.append(
            new_event(
                source=Source.GITHUB,
                subject=subject,
                occurred_at=occurred,
                observed_at=observed_at,
                payload=payload,
                identity=(e["id"],),
            )
        )
    return out


# ---------------------------------------------------------------- KEP metadata


def kep_paths(tree: Iterable[Json]) -> dict[int, str]:
    """Map KEP number -> ``kep.yaml`` path from a recursive git tree listing.

    KEP folders live under the *owning* SIG (#6395 is under ``keps/sig-storage/``),
    so they cannot be located from issue labels alone.
    """
    paths: dict[int, str] = {}
    for entry in tree:
        match = _KEP_PATH.match(entry.get("path", ""))
        if match:
            paths[int(match.group(1))] = entry["path"]
    return paths


def kep_spec(
    text: str,
    *,
    path: str,
    repo: str,
    number: int,
    project: str,
    observed_at: datetime,
    occurred_at: datetime,
) -> NormalizedEvent:
    """``work_item.spec_observed`` from a ``kep.yaml`` (feature gates, SIGs, stage)."""
    try:
        doc = yaml.load(text, Loader=_NoDatesLoader) or {}  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise SpecParseError(f"{path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise SpecParseError(f"{path}: top level is {type(doc).__name__}, expected a mapping")
    raw_gates = doc.get("feature-gates") or []
    gates = tuple(str(g["name"]) for g in raw_gates if isinstance(g, dict) and g.get("name"))
    latest = doc.get("latest-milestone")
    payload = WorkItemSpecObserved(
        spec_path=path,
        feature_flags=gates,
        owning_team=doc.get("owning-sig"),
        participating_teams=tuple(str(s) for s in doc.get("participating-sigs") or ()),
        stage=doc.get("stage"),
        target_release_key=release_key(project, str(latest)) if latest else None,
        spec_status=doc.get("status"),
    )
    return new_event(
        source=Source.GITHUB,
        subject=work_item_ref(repo, number),
        occurred_at=occurred_at,
        observed_at=observed_at,
        payload=payload,
        identity=(hashlib.sha256(text.encode()).hexdigest(),),
    )


# ---------------------------------------------------------------- pull requests


def pull_request_events(node: Json, *, observed_at: datetime) -> list[NormalizedEvent]:
    """PR snapshot, its reviews and its latest-commit CI results from a ``PRFields`` node."""
    repo = node["repository"]["nameWithOwner"]
    subject = pull_request_ref(repo, node["number"])
    commit = _latest_commit(node)
    head_sha = commit.get("oid") if commit else None
    updated = parse_ts(node["updatedAt"])
    lane = _lane_snapshot(node)

    pr = PullRequestObserved(
        repo=repo,
        number=node["number"],
        title=node["title"],
        body=node.get("body") or "",
        author=(node.get("author") or {}).get("login"),
        state=_PR_STATES[node["state"]],
        labels=tuple(sorted(n["name"] for n in node["labels"]["nodes"])),
        base_ref=node.get("baseRefName"),
        head_sha=head_sha,
        created_at=parse_ts(node["createdAt"]),
        updated_at=updated,
        merged_at=parse_ts(node["mergedAt"]) if node.get("mergedAt") else None,
        closed_at=parse_ts(node["closedAt"]) if node.get("closedAt") else None,
        url=node.get("url"),
        **lane,
    )
    out = [
        new_event(
            source=Source.GITHUB,
            subject=subject,
            occurred_at=updated,
            observed_at=observed_at,
            payload=pr,
            identity=(node["updatedAt"],),
        )
    ]
    raw_mergeable = node.get("mergeable")
    if head_sha and raw_mergeable in ("MERGEABLE", "CONFLICTING"):
        state: Literal["mergeable", "conflicting"] = (
            "mergeable" if raw_mergeable == "MERGEABLE" else "conflicting"
        )
        out.append(
            new_event(
                source=Source.GITHUB,
                subject=subject,
                occurred_at=updated,
                observed_at=observed_at,
                payload=MergeabilityObserved(head_sha=head_sha, mergeable=state),
                identity=(head_sha, state),
            )
        )
    out.extend(review_events(node["reviews"]["nodes"], subject=subject, observed_at=observed_at))
    comments = (node.get("comments") or {}).get("nodes") or []
    out.extend(comment_events(comments, subject=subject, observed_at=observed_at))
    if commit and head_sha:
        out.extend(_check_events(commit, head_sha, subject, updated, observed_at))
    return out


def review_events(
    reviews: Iterable[Json], *, subject: SubjectRef, observed_at: datetime
) -> list[NormalizedEvent]:
    """One event per submitted review. Pending (draft) reviews are skipped."""
    out: list[NormalizedEvent] = []
    for r in reviews:
        state = _REVIEW_STATES.get(r.get("state", ""))
        if state is None or not r.get("submittedAt"):
            continue
        submitted = parse_ts(r["submittedAt"])
        out.append(
            new_event(
                source=Source.GITHUB,
                subject=subject,
                occurred_at=submitted,
                observed_at=observed_at,
                payload=ReviewSubmitted(
                    review_id=str(r["databaseId"]),
                    reviewer=(r.get("author") or {}).get("login"),
                    state=state,
                    submitted_at=submitted,
                ),
                identity=(r["databaseId"],),
            )
        )
    return out


# Prow commands at the start of a line: /lgtm, /lgtm cancel, /approve, /approve no-issue,
# /approve cancel, /hold, /hold cancel, /unhold, /remove-lgtm, /remove-approve.
_COMMAND = re.compile(
    r"^\s*/(lgtm|approve|hold|unhold|remove-lgtm|remove-approve)\b[ \t]*(cancel)?",
    re.I | re.M,
)
_CANCELS = {
    "unhold": "hold_cancel",
    "remove-lgtm": "lgtm_cancel",
    "remove-approve": "approve_cancel",
}


def prow_commands(body: str) -> tuple[str, ...]:
    """Prow review commands in a comment, in order (``lgtm``, ``approve_cancel``, ...)."""
    out: list[str] = []
    for name, cancel in _COMMAND.findall(body or ""):
        name = name.lower()
        out.append(_CANCELS.get(name) or (f"{name}_cancel" if cancel else name))
    return tuple(out)


def comment_events(
    comments: Iterable[Json], *, subject: SubjectRef, observed_at: datetime
) -> list[NormalizedEvent]:
    """One event per comment: author, time and commands only; the text is not stored."""
    out: list[NormalizedEvent] = []
    for c in comments:
        if not c.get("createdAt") or c.get("databaseId") is None:
            continue
        posted = parse_ts(c["createdAt"])
        out.append(
            new_event(
                source=Source.GITHUB,
                subject=subject,
                occurred_at=posted,
                observed_at=observed_at,
                payload=CommentPosted(
                    comment_id=str(c["databaseId"]),
                    author=(c.get("author") or {}).get("login"),
                    posted_at=posted,
                    commands=prow_commands(c.get("body") or ""),
                ),
                identity=(c["databaseId"],),
            )
        )
    return out


def _lane_snapshot(node: Json) -> dict[str, Any]:
    """Branch, paths, size and commit messages when the lane query asked for them.

    Missing keys stay at the snapshot defaults, so a Kubernetes node still normalizes.
    Paths and messages only: never a patch.
    """
    files = node.get("files") or {}
    paths = tuple(
        n["path"] for n in (files.get("nodes") or []) if isinstance(n, dict) and n.get("path")
    )
    history = node.get("history") or {}
    notes: list[CommitNote] = []
    for n in (history.get("nodes") or [])[:30]:
        commit = (n or {}).get("commit") or {}
        when = commit.get("committedDate")
        if not when:
            continue
        message = "\n".join(
            part for part in (commit.get("messageHeadline"), commit.get("messageBody")) if part
        )
        notes.append(CommitNote(committed_at=parse_ts(when), message=message))
    mergeable = {"MERGEABLE": "mergeable", "CONFLICTING": "conflicting"}.get(
        node.get("mergeable") or "", "unknown"
    )
    out: dict[str, Any] = {}
    if "headRefName" in node:
        out["head_ref"] = node.get("headRefName")
    if "additions" in node:
        out["additions"] = int(node.get("additions") or 0)
    if "deletions" in node:
        out["deletions"] = int(node.get("deletions") or 0)
    if files:
        out["changed_files"] = paths
        out["files_truncated"] = bool((files.get("pageInfo") or {}).get("hasNextPage"))
    if history:
        out["commits"] = tuple(notes)
        out["commits_truncated"] = bool((history.get("pageInfo") or {}).get("hasNextPage"))
    if "mergeable" in node:
        out["mergeable"] = mergeable
    return out


def _latest_commit(node: Json) -> Json | None:
    nodes = (node.get("commits") or {}).get("nodes") or []
    return nodes[-1]["commit"] if nodes else None


def _check_events(
    commit: Json, head_sha: str, subject: SubjectRef, fallback: datetime, observed_at: datetime
) -> list[NormalizedEvent]:
    rollup = commit.get("statusCheckRollup") or {}
    out: list[NormalizedEvent] = []
    for ctx in (rollup.get("contexts") or {}).get("nodes") or []:
        if ctx.get("__typename") == "StatusContext":
            name = ctx["context"]
            conclusion = _STATUS_CONTEXT_STATES.get(ctx.get("state", ""), CheckConclusion.PENDING)
            when = parse_ts(ctx["createdAt"]) if ctx.get("createdAt") else None
        elif ctx.get("__typename") == "CheckRun":
            name = ctx["name"]
            raw = ctx.get("conclusion")
            conclusion = (
                _CHECK_RUN_CONCLUSIONS.get(raw, CheckConclusion.PENDING)
                if raw
                else (CheckConclusion.PENDING)
            )
            when = parse_ts(ctx["completedAt"]) if ctx.get("completedAt") else None
        else:
            continue
        out.append(
            new_event(
                source=Source.GITHUB,
                subject=subject,
                occurred_at=when or fallback,
                observed_at=observed_at,
                payload=CheckCompleted(
                    check_name=name, head_sha=head_sha, conclusion=conclusion, completed_at=when
                ),
                identity=(head_sha, name, conclusion.value, when.isoformat() if when else ""),
            )
        )
    return out
