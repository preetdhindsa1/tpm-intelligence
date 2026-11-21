"""Normalization of real #6395 fixtures (CLAUDE.md section 11)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from collectors.github_poller import normalize
from pipeline.events import (
    ChangeAction,
    CheckCompleted,
    PullRequestObserved,
    ReviewSubmitted,
    WorkItemLabelChanged,
    WorkItemReleaseChanged,
    WorkItemSpecObserved,
)
from tests.collectors.conftest import load_json, load_text

OBSERVED = datetime(2026, 11, 21, 12, tzinfo=UTC)
REPO = "kubernetes/enhancements"
V138 = "kubernetes:v1.38"


def events_6395() -> list[dict[str, Any]]:
    return normalize.timeline_to_events(load_json("issue_6395_timeline.json"))


def ts(s: str) -> datetime:
    return normalize.parse_ts(s)


@pytest.fixture
def history() -> list[Any]:
    return normalize.issue_history(
        events_6395(),
        repo=REPO,
        number=6395,
        project="kubernetes",
        observed_at=OBSERVED,
    )


# ---------------------------------------------------------------- #6395 replay


def test_6395_release_and_tracking_history_is_exact(history: list[Any]) -> None:
    """Opted in Sep 21, tracked Sep 23, removed at Code Freeze, re-added Nov 21."""
    relevant = [
        (
            e.occurred_at.isoformat(),
            e.payload.action.value,
            e.payload.release_key
            if isinstance(e.payload, WorkItemReleaseChanged)
            else e.payload.label,
        )
        for e in history
        if isinstance(e.payload, WorkItemReleaseChanged)
        or (
            isinstance(e.payload, WorkItemLabelChanged)
            and e.payload.label in ("tracked/yes", "tracked/no", "lead-opted-in")
        )
    ]
    assert relevant == [
        ("2026-09-21T20:34:30+00:00", "added", "lead-opted-in"),
        ("2026-09-21T20:34:45+00:00", "added", V138),
        ("2026-09-23T06:41:32+00:00", "added", "tracked/yes"),
        ("2026-11-17T12:05:57+00:00", "removed", V138),
        ("2026-11-17T12:05:58+00:00", "added", "tracked/no"),
        ("2026-11-17T12:05:59+00:00", "removed", "tracked/yes"),
        ("2026-11-21T00:33:55+00:00", "added", V138),
        ("2026-11-21T00:33:55+00:00", "added", "tracked/yes"),
        ("2026-11-21T00:33:56+00:00", "removed", "tracked/no"),
    ]


def _in_release_at(history: list[Any], when: datetime) -> bool:
    state = False
    for e in sorted(history, key=lambda e: e.occurred_at):
        if e.occurred_at >= when:
            break
        if isinstance(e.payload, WorkItemReleaseChanged) and e.payload.release_key == V138:
            state = e.payload.action is ChangeAction.ADDED
    return state


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("2026-09-21T00:00:00Z", False),  # before opt-in
        ("2026-11-17T12:00:00Z", True),  # at Code Freeze
        ("2026-11-17T12:06:00Z", False),  # removed 12:05:57
        ("2026-11-20T23:28:24Z", False),  # main PR merges while removed
        ("2026-11-21T00:34:00Z", True),  # re-added 00:33:55
    ],
)
def test_6395_membership_over_time(history: list[Any], when: str, expected: bool) -> None:
    assert _in_release_at(history, ts(when)) is expected


def test_event_ids_are_stable_across_polls(history: list[Any]) -> None:
    again = normalize.issue_history(
        events_6395(),
        repo=REPO,
        number=6395,
        project="kubernetes",
        observed_at=datetime.now(UTC),
    )
    assert [e.event_id for e in again] == [e.event_id for e in history]


def test_irrelevant_issue_events_are_ignored(history: list[Any]) -> None:
    raw_types = {e["event"] for e in events_6395()}
    assert {"labeled", "milestoned"} <= raw_types
    assert {e.event_type for e in history} <= {
        "work_item.release_changed",
        "work_item.label_changed",
        "work_item.status_changed",
    }


def test_timeline_adapter_ignores_unknown_item_types() -> None:
    nodes = [
        {"__typename": "AssignedEvent", "id": "a", "createdAt": "2026-11-01T00:00:00Z"},
        {
            "__typename": "LabeledEvent",
            "id": "b",
            "createdAt": "2026-11-01T00:00:00Z",
            "label": {"name": "tracked/yes"},
        },
    ]
    assert normalize.timeline_to_events(nodes) == [
        {
            "id": "b",
            "event": "labeled",
            "created_at": "2026-11-01T00:00:00Z",
            "label": {"name": "tracked/yes"},
        }
    ]


# ---------------------------------------------------------------- #2570: REST cap regression


def test_2570_freeze_removal_survives_long_history() -> None:
    """Regression: REST issue events cap at ~300 and missed #2570's whole v1.38 history."""
    assert load_json("meta.json")["rest_event_count_2570"] >= 300
    history = normalize.issue_history(
        normalize.timeline_to_events(load_json("issue_2570_timeline.json")),
        repo=REPO,
        number=2570,
        project="kubernetes",
        observed_at=OBSERVED,
    )
    v138 = [
        (e.occurred_at.isoformat(), e.payload.action.value)
        for e in history
        if isinstance(e.payload, WorkItemReleaseChanged) and e.payload.release_key == V138
    ]
    assert v138 == [
        ("2026-09-08T19:30:49+00:00", "added"),
        ("2026-11-17T12:38:52+00:00", "removed"),
        ("2026-11-21T02:12:26+00:00", "added"),
    ]
    assert _in_release_at(history, ts("2026-11-17T12:00:00Z")) is True
    assert _in_release_at(history, ts("2026-11-18T00:00:00Z")) is False
    assert _in_release_at(history, ts("2026-11-21T03:00:00Z")) is True


# ---------------------------------------------------------------- issue snapshot


def test_issue_snapshot() -> None:
    issue = load_json("issue_6395.json")
    event = normalize.issue_snapshot(issue, repo=REPO, project="kubernetes", observed_at=OBSERVED)
    p = event.payload
    assert event.subject.external_key == "kubernetes/enhancements#6395"
    assert p.title == "Dynamic node-local ephemeral volumes"
    assert p.release_keys == (V138,)
    assert {"sig/node", "sig/storage", "stage/alpha", "tracked/yes"} <= set(p.labels)
    assert "https://github.com/kubernetes/kubernetes/pull/143709" in p.description
    assert p.status_category == "in_progress"


def test_issue_in_release_uses_history_when_milestone_removed() -> None:
    issue = {**load_json("issue_6395.json"), "milestone": None}  # state on 2026-11-18
    events = events_6395()
    assert normalize.issue_in_release(issue, events, "v1.38")
    assert not normalize.issue_in_release(issue, events, "v1.37")
    assert not normalize.issue_in_release(issue, [], "v1.38")


def test_pull_requests_are_not_issues() -> None:
    assert normalize.is_pull_request({"number": 1, "pull_request": {}})
    assert not normalize.is_pull_request(load_json("issue_6395.json"))


# ---------------------------------------------------------------- kep.yaml


def test_kep_paths_found_under_owning_sig() -> None:
    tree = [
        {"path": "keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/kep.yaml"},
        {"path": "keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/README.md"},
        {"path": "keps/sig-node/1287-in-place-update-pod-resources/kep.yaml"},
        {"path": "keps/prod-readiness/sig-storage/6395.yaml"},
    ]
    assert normalize.kep_paths(tree) == {
        6395: "keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/kep.yaml",
        1287: "keps/sig-node/1287-in-place-update-pod-resources/kep.yaml",
    }


def test_kep_spec_feature_gate_and_sigs() -> None:
    path = load_json("meta.json")["kep_yaml_path"]
    event = normalize.kep_spec(
        load_text("kep_6395.yaml"),
        path=path,
        repo=REPO,
        number=6395,
        project="kubernetes",
        observed_at=OBSERVED,
        occurred_at=OBSERVED,
    )
    p = event.payload
    assert isinstance(p, WorkItemSpecObserved)
    assert p.feature_flags == ("DynamicNodeLocalEphemeralVolumes",)
    assert p.owning_team == "sig-storage"
    assert p.participating_teams == ("sig-node",)
    assert (p.stage, p.target_release_key, p.spec_status) == ("alpha", V138, "implementable")


def test_kep_spec_tolerates_invalid_dates() -> None:
    """Regression: a real kep.yaml with an impossible date crashed the v1.38 backfill."""
    text = "creation-date: 2026-13-45\nlast-updated: 2026-02-30\nfeature-gates:\n  - name: G\n"
    event = normalize.kep_spec(
        text,
        path="p",
        repo=REPO,
        number=1,
        project="kubernetes",
        observed_at=OBSERVED,
        occurred_at=OBSERVED,
    )
    assert isinstance(event.payload, WorkItemSpecObserved)
    assert event.payload.feature_flags == ("G",)


@pytest.mark.parametrize("text", ["key: [unclosed", "- just\n- a list\n"])
def test_kep_spec_unparseable_raises_spec_error(text: str) -> None:
    with pytest.raises(normalize.SpecParseError):
        normalize.kep_spec(
            text,
            path="p",
            repo=REPO,
            number=1,
            project="kubernetes",
            observed_at=OBSERVED,
            occurred_at=OBSERVED,
        )


def test_kep_spec_without_gates() -> None:
    event = normalize.kep_spec(
        "title: x\nstage: beta\n",
        path="p",
        repo=REPO,
        number=1,
        project="kubernetes",
        observed_at=OBSERVED,
        occurred_at=OBSERVED,
    )
    assert isinstance(event.payload, WorkItemSpecObserved)
    assert event.payload.feature_flags == ()
    assert event.payload.target_release_key is None


# ---------------------------------------------------------------- pull requests


@pytest.fixture
def prs() -> dict[int, list[Any]]:
    return {
        node["number"]: normalize.pull_request_events(node, observed_at=OBSERVED)
        for node in load_json("prs_6395.json")
    }


def _snapshot(events: list[Any]) -> PullRequestObserved:
    [snap] = [e.payload for e in events if isinstance(e.payload, PullRequestObserved)]
    return snap


@pytest.mark.parametrize(
    ("number", "state", "merged_at"),
    [
        (143442, "closed", None),
        (143445, "merged", "2026-10-27T21:57:16Z"),
        (143474, "merged", "2026-11-06T18:17:47Z"),
        (143522, "merged", "2026-11-04T23:07:12Z"),
        (143644, "merged", "2026-11-06T22:29:37Z"),
        (143709, "merged", "2026-11-20T23:28:24Z"),
    ],
)
def test_pr_states_and_merge_times(
    prs: dict[int, list[Any]], number: int, state: str, merged_at: str | None
) -> None:
    snap = _snapshot(prs[number])
    assert snap.state == state
    assert snap.merged_at == (ts(merged_at) if merged_at else None)


def test_main_pr_143709_opened_nov_2_merged_after_code_freeze(prs: dict[int, list[Any]]) -> None:
    snap = _snapshot(prs[143709])
    assert snap.created_at.date().isoformat() == "2026-11-02"
    assert snap.merged_at is not None
    assert snap.merged_at > datetime(2026, 11, 17, 12, tzinfo=UTC)
    assert "6395" in snap.body


def test_reviews_are_individual_records(prs: dict[int, list[Any]]) -> None:
    reviews = [e.payload for e in prs[143709] if isinstance(e.payload, ReviewSubmitted)]
    raw = next(n for n in load_json("prs_6395.json") if n["number"] == 143709)
    submitted = [r for r in raw["reviews"]["nodes"] if r.get("submittedAt")]
    assert len(reviews) == len(submitted)
    assert len(reviews) > 50  # many records; the engine groups them into rounds (M5)
    assert len({r.review_id for r in reviews}) == len(reviews)
    assert all(r.reviewer is None or r.reviewer.startswith("user-") for r in reviews)


def test_ci_results_from_latest_commit(prs: dict[int, list[Any]]) -> None:
    checks = [e.payload for e in prs[143709] if isinstance(e.payload, CheckCompleted)]
    assert checks
    assert len({c.head_sha for c in checks}) == 1
    assert _snapshot(prs[143709]).head_sha == checks[0].head_sha


def test_pending_reviews_are_skipped() -> None:
    subject = normalize.pull_request_ref("kubernetes/kubernetes", 1)
    events = normalize.review_events(
        [
            {"databaseId": 1, "author": None, "state": "PENDING", "submittedAt": None},
            {
                "databaseId": 2,
                "author": {"login": "a"},
                "state": "APPROVED",
                "submittedAt": "2026-11-01T00:00:00Z",
            },
        ],
        subject=subject,
        observed_at=OBSERVED,
    )
    assert [e.payload.review_id for e in events] == ["2"]


def test_unknown_check_states_become_pending() -> None:
    node: dict[str, Any] = {
        **load_json("prs_6395.json")[0],
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "oid": "abc",
                        "statusCheckRollup": {
                            "contexts": {
                                "nodes": [
                                    {
                                        "__typename": "CheckRun",
                                        "name": "build",
                                        "conclusion": None,
                                        "status": "IN_PROGRESS",
                                        "completedAt": None,
                                    },
                                    {
                                        "__typename": "StatusContext",
                                        "context": "pull-unit",
                                        "state": "ERROR",
                                        "createdAt": "2026-11-01T00:00:00Z",
                                    },
                                ]
                            }
                        },
                    }
                }
            ]
        },
    }
    checks = {
        e.payload.check_name: e.payload.conclusion.value
        for e in normalize.pull_request_events(node, observed_at=OBSERVED)
        if isinstance(e.payload, CheckCompleted)
    }
    assert checks == {"build": "pending", "pull-unit": "failure"}
