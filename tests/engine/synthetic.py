"""Build small synthetic event streams (same shapes as the real collector emits)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipeline.events import (
    ChangeAction,
    NormalizedEvent,
    PullRequestObserved,
    ReleaseObserved,
    Source,
    SubjectKind,
    SubjectRef,
    WorkItemObserved,
    WorkItemReleaseChanged,
    WorkItemType,
    new_event,
)

ENH, KK = "kubernetes/enhancements", "kubernetes/kubernetes"


def _ref(kind: SubjectKind, key: str) -> SubjectRef:
    return SubjectRef(kind=kind, source=Source.GITHUB, external_key=key)


@dataclass
class Stream:
    """Accumulates events; ``observed`` is when the snapshots were taken."""

    observed: datetime
    events: list[NormalizedEvent] = field(default_factory=list)

    def release(self, name: str, start: datetime, freeze: datetime, release: datetime) -> str:
        key = f"kubernetes:{name}"
        self.events.append(
            new_event(
                source=Source.GITHUB,
                subject=_ref(SubjectKind.RELEASE, key),
                occurred_at=start,
                observed_at=self.observed,
                identity=(name,),
                payload=ReleaseObserved(
                    project="kubernetes",
                    name=name,
                    cycle_start_at=start,
                    enhancements_freeze_at=start,
                    code_freeze_at=freeze,
                    release_at=release,
                ),
            )
        )
        return key

    def feature(self, n: int, release_key: str, changes: list[tuple[datetime, bool]]) -> str:
        key = f"{ENH}#{n}"
        self.events.append(
            new_event(
                source=Source.GITHUB,
                subject=_ref(SubjectKind.WORK_ITEM, key),
                occurred_at=self.observed,
                observed_at=self.observed,
                identity=(n,),
                payload=WorkItemObserved(
                    item_type=WorkItemType.FEATURE,
                    title=f"F{n}",
                    state="open",
                    status_category="in_progress",
                    created_at=changes[0][0],
                    updated_at=self.observed,
                ),
            )
        )
        for at, added in changes:
            self.events.append(
                new_event(
                    source=Source.GITHUB,
                    subject=_ref(SubjectKind.WORK_ITEM, key),
                    occurred_at=at,
                    observed_at=self.observed,
                    identity=(release_key, added, at.isoformat()),
                    payload=WorkItemReleaseChanged(
                        action=ChangeAction.ADDED if added else ChangeAction.REMOVED,
                        release_key=release_key,
                    ),
                )
            )
        return key

    def pr(
        self,
        number: int,
        kep: int,
        created: datetime,
        merged: datetime | None = None,
        closed: datetime | None = None,
        extra: str = "",
    ) -> str:
        key = f"{KK}#{number}"
        state = "merged" if merged else ("closed" if closed else "open")
        self.events.append(
            new_event(
                source=Source.GITHUB,
                subject=_ref(SubjectKind.PULL_REQUEST, key),
                occurred_at=self.observed,
                observed_at=self.observed,
                identity=(number,),
                payload=PullRequestObserved(
                    repo=KK,
                    number=number,
                    title=f"PR {number}",
                    body=f"KEP: https://github.com/{ENH}/issues/{kep}\n{extra}",
                    state=state,
                    created_at=created,
                    updated_at=self.observed,
                    merged_at=merged,
                    closed_at=closed or merged,
                ),
            )
        )
        return key
