"""This repo's UX v1 sprint retro per lane (#182): lanes, the window, small samples."""

from __future__ import annotations

from api.service import InMemoryEventSource
from pipeline.events import (
    PullRequestObserved,
    ReleaseObserved,
    Source,
    SubjectKind,
    SubjectRef,
    new_event,
)
from tests.api.test_api import client_at, utc

REPO = "preetdhindsa1/tpm-intelligence"
SEEN = utc(2026, 11, 26)


def ref(kind: SubjectKind, key: str) -> SubjectRef:
    return SubjectRef(kind=kind, source=Source.GITHUB, external_key=key)


def pr(n: int, opened, merged, branch: str, labels: tuple[str, ...]):  # type: ignore[no-untyped-def]
    return new_event(
        source=Source.GITHUB, subject=ref(SubjectKind.PULL_REQUEST, f"{REPO}#{n}"),
        occurred_at=opened, observed_at=SEEN, identity=(n,),
        payload=PullRequestObserved(
            repo=REPO, number=n, title=f"PR {n}", state="merged" if merged else "open",
            head_ref=branch, labels=labels, created_at=opened, merged_at=merged,
            updated_at=SEEN,
        ),
    )  # fmt: skip


def test_lane_retro_counts_only_the_sprint_window_per_lane() -> None:
    release = new_event(
        source=Source.GITHUB, subject=ref(SubjectKind.RELEASE, "tpm-intelligence:Phase 3"),
        occurred_at=utc(2026, 11, 23), observed_at=SEEN, identity=("Phase 3",),
        payload=ReleaseObserved(project="tpm-intelligence", name="Phase 3",
                                cycle_start_at=utc(2026, 11, 30),
                                code_freeze_at=utc(2027, 1, 14, 12), release_at=utc(2027, 1, 20)),
    )  # fmt: skip
    events = [
        release,
        pr(1, utc(2026, 11, 24, 23), utc(2026, 11, 25, 1), "claude/96-docs", ("claude-agent",)),
        pr(2, utc(2026, 11, 25, 2), utc(2026, 11, 25, 6), "claude/97-lab", ("claude-agent",)),
        pr(3, utc(2026, 11, 25, 3), None, "cursor/101-portfolio", ("cursor-agent",)),
        pr(4, utc(2026, 11, 20), utc(2026, 11, 21), "claude/50-old", ("claude-agent",)),
    ]
    body = client_at(SEEN, source=InMemoryEventSource(events)).get("/retro/lanes").json()
    assert (body["label"], body["synthetic"]) == ("UX v1 sprint (Wave 1)", False)
    lanes = {x["lane"]: x for x in body["lanes"]}
    assert (lanes["claude"]["opened"], lanes["claude"]["merged"]) == (2, 2)  # #4 is earlier
    assert lanes["claude"]["median_hours_to_merge"] == 3.0
    assert (lanes["cursor"]["opened"], lanes["cursor"]["still_open"]) == (1, 1)
    assert all(x["small_sample"] for x in body["lanes"])
    assert "login" not in str(body)


def test_lane_retro_needs_pod_lanes() -> None:
    client = client_at(SEEN, source=InMemoryEventSource([]))
    assert client.get("/retro/lanes?project=kubernetes").status_code == 404
