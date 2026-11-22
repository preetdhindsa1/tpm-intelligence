"""Jira REST v2 issue JSON -> normalized events (Apache Kafka; CLAUDE.md sections 6-7). Pure.

Produces the same event types as the GitHub collector, so nothing downstream depends on
the source:

- ``work_item.observed``: current snapshot (type, status and status category, fix
  versions as release keys, labels, parent, description, URL).
- ``work_item.release_changed``: every Fix Version change in the changelog, **plus** the
  versions the issue had when it was created. Jira's changelog does not record values set
  at creation, so they are rebuilt by undoing the changelog from the current state
  (KAFKA-21181: 4.2.0 and 4.3.0 were set at creation, 4.0.0 and 4.1.0 added later).
- ``work_item.label_changed`` and ``work_item.status_changed`` from the changelog.
- ``reference.observed`` for each remote link to a GitHub pull request (raw evidence; the
  linker decides the method and confidence).

Who made a change is never read (no per-person data, CLAUDE.md section 10).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

from pipeline.events import (
    ChangeAction,
    NormalizedEvent,
    ReferenceObserved,
    SubjectKind,
    SubjectRef,
    WorkItemLabelChanged,
    WorkItemObserved,
    WorkItemReleaseChanged,
    WorkItemStatusChanged,
    WorkItemType,
    new_event,
    release_key,
)
from pipeline.events import Source as EventSource

Json = Mapping[str, Any]
Category = Literal["todo", "in_progress", "done"]

# Jira's built-in status categories (CLAUDE.md section 6).
CATEGORY_KEYS: Mapping[str, Category] = {
    "new": "todo",
    "indeterminate": "in_progress",
    "done": "done",
}

# Apache Jira's KAFKA workflow, for changelog entries (which carry status names only).
# A team connector may override these (CLAUDE.md section 6: per-team overrides).
DEFAULT_STATUS_CATEGORIES: Mapping[str, Category] = {
    "Open": "todo",
    "Reopened": "todo",
    "To Do": "todo",
    "In Progress": "in_progress",
    "Patch Available": "in_progress",
    "In Review": "in_progress",
    "Resolved": "done",
    "Closed": "done",
    "Done": "done",
}

ITEM_TYPES: Mapping[str, WorkItemType] = {
    "Initiative": WorkItemType.INITIATIVE,
    "Epic": WorkItemType.EPIC,
    "New Feature": WorkItemType.FEATURE,
    "Improvement": WorkItemType.STORY,
    "Story": WorkItemType.STORY,
    "Task": WorkItemType.STORY,
    "Test": WorkItemType.STORY,
    "Wish": WorkItemType.STORY,
    "Sub-task": WorkItemType.SUBTASK,
    "Bug": WorkItemType.BUG,
}

_GITHUB_PR = re.compile(r"^https://github\.com/(?P<repo>[\w.-]+/[\w.-]+)/pull/(?P<n>\d+)/?$")


def parse_ts(value: str) -> datetime:
    """Jira timestamps look like ``2025-10-24T09:12:33.000+0000``."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")


def work_item_ref(key: str) -> SubjectRef:
    """Subject for a Jira issue, e.g. ``KAFKA-19831``."""
    return SubjectRef(kind=SubjectKind.WORK_ITEM, source=EventSource.JIRA, external_key=key)


def item_type(issue: Json) -> WorkItemType:
    """Generic type; ``subtask`` for any Jira sub-task type."""
    t = issue["fields"]["issuetype"]
    if t.get("subtask"):
        return WorkItemType.SUBTASK
    return ITEM_TYPES.get(t["name"], WorkItemType.STORY)


def category(
    status_name: str,
    category_key: str | None = None,
    overrides: Mapping[str, Category] | None = None,
) -> Category:
    """Status category: a team override, else Jira's category key, else the workflow map."""
    if overrides and status_name in overrides:
        return overrides[status_name]
    if category_key is not None and category_key in CATEGORY_KEYS:
        return CATEGORY_KEYS[category_key]
    return DEFAULT_STATUS_CATEGORIES.get(status_name, "in_progress")


def _changes(issue: Json, field: str) -> list[tuple[str, datetime, str | None, str | None]]:
    """(history id, time, from, to) for one field, oldest first."""
    out = [
        (h["id"], parse_ts(h["created"]), item.get("fromString"), item.get("toString"))
        for h in issue.get("changelog", {}).get("histories", [])
        for item in h["items"]
        if item["field"] == field
    ]
    return sorted(out, key=lambda c: (c[1], c[0]))


def _labels(value: str | None) -> set[str]:
    return set((value or "").split())


def initial_fix_versions(issue: Json) -> set[str]:
    """Fix versions at creation: the current ones with the changelog undone, newest first."""
    state = {v["name"] for v in issue["fields"].get("fixVersions", [])}
    for _, _, before, after in reversed(_changes(issue, "Fix Version")):
        if after:
            state.discard(after)
        if before:
            state.add(before)
    return state


def initial_labels(issue: Json) -> set[str]:
    """Labels at creation, rebuilt the same way (Jira logs labels as space-separated lists)."""
    state = set(issue["fields"].get("labels", []))
    for _, _, before, after in reversed(_changes(issue, "labels")):
        state = (state - _labels(after)) | _labels(before)
    return state


def issue_snapshot(
    issue: Json,
    *,
    project: str,
    base_url: str,
    observed_at: datetime,
    overrides: Mapping[str, Category] | None = None,
) -> NormalizedEvent:
    """``work_item.observed`` for the issue as it is now."""
    f = issue["fields"]
    status = f["status"]
    payload = WorkItemObserved(
        item_type=item_type(issue),
        title=f["summary"],
        state=status["name"],
        status_category=category(
            status["name"], status.get("statusCategory", {}).get("key"), overrides
        ),
        labels=tuple(sorted(f.get("labels", []))),
        release_keys=tuple(
            sorted(release_key(project, v["name"]) for v in f.get("fixVersions", []))
        ),
        parent_key=(f.get("parent") or {}).get("key"),
        description=f.get("description") or "",
        url=f"{base_url.rstrip('/')}/browse/{issue['key']}",
        created_at=parse_ts(f["created"]),
        updated_at=parse_ts(f["updated"]),
    )
    return new_event(
        source=EventSource.JIRA,
        subject=work_item_ref(issue["key"]),
        occurred_at=payload.updated_at,
        observed_at=observed_at,
        payload=payload,
        identity=(payload.updated_at.isoformat(),),
    )


def issue_history(
    issue: Json,
    *,
    project: str,
    observed_at: datetime,
    overrides: Mapping[str, Category] | None = None,
) -> list[NormalizedEvent]:
    """Release, label and status changes, including the state at creation."""
    key = issue["key"]
    subject = work_item_ref(key)
    created = parse_ts(issue["fields"]["created"])
    out: list[NormalizedEvent] = []

    def emit(at: datetime, payload: Any, identity: tuple[object, ...]) -> None:
        out.append(
            new_event(
                source=EventSource.JIRA,
                subject=subject,
                occurred_at=at,
                observed_at=observed_at,
                payload=payload,
                identity=identity,
            )
        )

    for version in sorted(initial_fix_versions(issue)):
        emit(
            created,
            WorkItemReleaseChanged(
                action=ChangeAction.ADDED, release_key=release_key(project, version)
            ),
            ("created", "fix_version", version),
        )
    for hid, at, before, after in _changes(issue, "Fix Version"):
        if before:
            emit(
                at,
                WorkItemReleaseChanged(
                    action=ChangeAction.REMOVED, release_key=release_key(project, before)
                ),
                (hid, "removed", before),
            )
        if after:
            emit(
                at,
                WorkItemReleaseChanged(
                    action=ChangeAction.ADDED, release_key=release_key(project, after)
                ),
                (hid, "added", after),
            )

    for label in sorted(initial_labels(issue)):
        emit(
            created,
            WorkItemLabelChanged(action=ChangeAction.ADDED, label=label),
            ("created", "label", label),
        )
    for hid, at, before, after in _changes(issue, "labels"):
        old, new = _labels(before), _labels(after)
        for label in sorted(new - old):
            emit(
                at,
                WorkItemLabelChanged(action=ChangeAction.ADDED, label=label),
                (hid, "added", label),
            )
        for label in sorted(old - new):
            emit(
                at,
                WorkItemLabelChanged(action=ChangeAction.REMOVED, label=label),
                (hid, "removed", label),
            )

    for hid, at, before, after in _changes(issue, "status"):
        if after:
            emit(
                at,
                WorkItemStatusChanged(
                    from_state=before, to_state=after, to_category=category(after, None, overrides)
                ),
                (hid, before, after),
            )
    return out


def pull_request_ref(url: str) -> SubjectRef | None:
    """Subject for a GitHub pull request URL, or None for anything else."""
    m = _GITHUB_PR.match(url.strip())
    if not m:
        return None
    return SubjectRef(
        kind=SubjectKind.PULL_REQUEST,
        source=EventSource.GITHUB,
        external_key=f"{m.group('repo')}#{m.group('n')}",
    )


def remote_link_events(
    key: str, links: Iterable[Json], *, observed_at: datetime
) -> list[NormalizedEvent]:
    """``reference.observed`` for each remote link that points at a GitHub pull request."""
    out: list[NormalizedEvent] = []
    for link in links:
        pr = pull_request_ref(link.get("object", {}).get("url", ""))
        if pr is None:
            continue
        out.append(
            new_event(
                source=EventSource.JIRA,
                subject=work_item_ref(key),
                occurred_at=observed_at,
                observed_at=observed_at,
                payload=ReferenceObserved(pull_request=pr, evidence="remote_link"),
                identity=(link["id"], pr.external_key),
            )
        )
    return out
