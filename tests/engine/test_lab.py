"""Lane classification, collisions and lab counts. No live GitHub calls."""

from __future__ import annotations

from datetime import datetime, timedelta

from engine.lab import (
    LabReport,
    LaneSpec,
    cap_open_agent_prs,
    classify_lane,
    collisions,
    extra_for_sizes,
    lab_report,
)
from engine.projection import Check, Comment, PullRequest, ReleaseInfo, Review, World
from pipeline.events import CommitNote
from tests.engine.conftest import utc

RULES = (
    LaneSpec("claude", ("claude-agent",), ("claude/",), ("Co-Authored-By: Claude",)),
    LaneSpec("cursor", ("cursor-agent",), ("cursor/",), ("Co-authored-by: Cursor Agent",)),
    LaneSpec("human", ("harpreet",), ("harpreet/",), ()),
)
T0 = utc(2026, 12, 1, 9)


def _pr(**kw: object) -> PullRequest:
    base: dict[str, object] = {
        "key": "preetdhindsa1/tpm-intelligence#1",
        "repo": "preetdhindsa1/tpm-intelligence",
        "number": 1,
        "title": "t",
        "body": "",
        "author": "someone",
        "labels": (),
        "created_at": T0,
        "state": "open",
        "merged_at": None,
        "closed_at": None,
        "reviews": (),
        "checks": (),
    }
    base.update(kw)
    return PullRequest(**base)  # type: ignore[arg-type]


def test_label_beats_branch_and_trailer() -> None:
    lane = classify_lane(
        ("cursor-agent",),
        "claude/x",
        ("Co-Authored-By: Claude",),
        RULES,
    )
    assert lane == "cursor"


def test_branch_beats_trailer() -> None:
    assert classify_lane((), "cursor/1-lab", ("Co-Authored-By: Claude",), RULES) == "cursor"


def test_trailer_alone_selects_claude_but_not_over_a_human_branch() -> None:
    assert classify_lane((), None, ("Co-Authored-By: Claude",), RULES) == "claude"
    assert classify_lane((), "harpreet/1-docs", ("Co-Authored-By: Claude",), RULES) == "human"


def test_no_match_and_dependabot_are_unassigned() -> None:
    assert classify_lane((), None, (), RULES) is None
    assert classify_lane((), "Claude/foo", (), RULES) is None
    assert classify_lane((), "dependabot/npm_and_yarn/something", (), RULES) is None


def test_shared_paths_collide_and_empty_or_closed_do_not() -> None:
    left = _pr(key="repo#1", number=1, changed_files=("engine/lab.py",))
    right = _pr(key="repo#2", number=2, changed_files=("engine/lab.py", "README.md"))
    empty = _pr(key="repo#3", number=3, changed_files=())
    closed = _pr(key="repo#4", number=4, state="closed", changed_files=("engine/lab.py",))
    found = collisions([left, right, empty, closed])
    assert len(found) == 1
    assert found[0].kind == "shared_files"
    assert found[0].pull_requests == ("repo#1", "repo#2")
    assert found[0].paths == ("engine/lab.py",)
    assert found[0].truncated is False


def test_merge_conflict_with_main_and_unknown_is_not_one() -> None:
    conflict = _pr(mergeable="conflicting")
    unknown = _pr(key="repo#2", number=2, mergeable="unknown")
    kinds = {(c.kind, c.pull_requests) for c in collisions([conflict, unknown])}
    assert ("merge_conflict", ("preetdhindsa1/tpm-intelligence#1",)) in kinds
    assert all(c.pull_requests != ("repo#2",) for c in collisions([unknown]))


def test_two_reviews_inside_an_hour_are_one_round_and_the_author_does_not_start_it() -> None:
    pr = _pr(
        author="author",
        reviews=(
            Review("1", "preetdhindsa1", "commented", T0 + timedelta(minutes=10)),
            Review("2", "preetdhindsa1", "approved", T0 + timedelta(minutes=40)),
        ),
        comments=(Comment("c", "author", T0 + timedelta(minutes=1), ()),),
    )
    report = _report([pr])
    assert report.review_round_counts == (1,)
    assert report.time_to_first_review_hours == (10 / 60,)
    assert report.still_waiting == 0


def test_only_open_prs_without_a_review_are_waiting() -> None:
    open_pr = _pr(key="repo#1", number=1)
    merged = _pr(key="repo#2", number=2, state="merged", merged_at=T0 + timedelta(hours=1))
    closed = _pr(key="repo#3", number=3, state="closed", closed_at=T0 + timedelta(hours=1))
    assert _report([open_pr, merged, closed]).still_waiting == 1


def test_queue_counts_until_the_pool_reviews() -> None:
    waiting = _pr(key="repo#1", number=1, head_ref="claude/1")
    reviewed = _pr(
        key="repo#2",
        number=2,
        head_ref="cursor/2",
        reviews=(Review("1", "preetdhindsa1", "approved", T0 + timedelta(hours=2)),),
    )
    report = _report([waiting, reviewed], as_of=T0 + timedelta(days=1))
    day = next(point for point in report.queue if point.day == "2026-12-01")
    assert day.count == 1


def test_cap_holds_the_second_agent_pr_and_ignores_human() -> None:
    first = _pr(key="repo#1", number=1, head_ref="claude/1", created_at=T0)
    second = _pr(
        key="repo#2",
        number=2,
        head_ref="cursor/2",
        created_at=T0 + timedelta(hours=1),
    )
    human = _pr(
        key="repo#3",
        number=3,
        head_ref="harpreet/3",
        created_at=T0 + timedelta(minutes=30),
    )
    lanes = {"repo#1": "claude", "repo#2": "cursor", "repo#3": "human"}
    replay = cap_open_agent_prs([first, second, human], lanes, 1, n_merged=0)
    assert replay.observed_max_open == 2
    assert replay.held == 1
    assert replay.scenario_max_open is None
    assert replay.comparable is False


def test_fewer_than_20_merges_is_not_comparable() -> None:
    merged = _pr(state="merged", merged_at=T0 + timedelta(days=1), head_ref="claude/1")
    report = _report([merged])
    assert report.n_merged == 1
    assert report.small_sample is True
    assert report.cap.scenario_max_open is None
    assert report.size.extra_pull_requests is None


def test_size_cap_splits_only_above_the_cap() -> None:
    assert extra_for_sizes([900, 400, 0], 400) == 2


def test_rework_needs_a_commit_after_the_first_round() -> None:
    later = CommitNote(committed_at=T0 + timedelta(hours=3), message="fix")
    with_commit = _pr(
        reviews=(Review("1", "preetdhindsa1", "commented", T0 + timedelta(hours=1)),),
        commits=(later,),
    )
    missing = _pr(
        key="repo#2",
        number=2,
        reviews=(Review("1", "preetdhindsa1", "changes_requested", T0 + timedelta(hours=1)),),
    )
    no_times = _pr(
        key="repo#3",
        number=3,
        reviews=(Review("1", "preetdhindsa1", "commented", T0 + timedelta(hours=1)),),
    )
    report = _report([with_commit, missing, no_times])
    assert report.rework == 2


def test_ci_failure_is_a_count_of_pull_requests() -> None:
    bad = _pr(checks=(Check("unit", "failure", T0),))
    report = _report([bad])
    assert report.ci_failures == 1


def test_no_lower_bound_keeps_a_pull_request_opened_before_the_cycle() -> None:
    early = _pr(key="repo#9", number=9, created_at=utc(2026, 11, 1))
    start = utc(2026, 11, 30)
    assert _report([early], since=None).n_pull_requests == 1
    assert _report([early], since=start).n_pull_requests == 0


def test_dependabot_is_not_the_cursor_lane() -> None:
    bot = _pr(head_ref="dependabot/npm_and_yarn/left-pad", author="dependabot[bot]")
    report = _report([bot])
    assert report.buckets == (report.buckets[0],)
    assert report.buckets[0].lane == "dependabot"
    assert report.arrivals[0].lane == "dependabot"


def test_approval_rate_counts_an_approving_round_or_a_merge_by_the_pool() -> None:
    approved = _pr(
        key="repo#1",
        number=1,
        state="merged",
        merged_at=T0 + timedelta(hours=5),
        reviews=(Review("1", "preetdhindsa1", "approved", T0 + timedelta(hours=1)),),
    )
    bare = _pr(key="repo#2", number=2, state="merged", merged_at=T0 + timedelta(hours=6))
    by_owner = _pr(key="repo#3", number=3, state="merged", merged_at=T0 + timedelta(hours=6),
                   merged_by="preetdhindsa1")  # fmt: skip
    by_other = _pr(key="repo#4", number=4, state="merged", merged_at=T0 + timedelta(hours=6),
                   merged_by="someone")  # fmt: skip
    report = _report([approved, bare, by_owner, by_other])
    assert report.approved_merged == 2  # the approving round and the owner's merge
    assert report.approval_rate == 0.5
    assert report.median_hours_to_merge == 6.0
    assert _report([_pr()]).approval_rate is None


def _report(
    prs: list[PullRequest], *, as_of: datetime | None = None, since: datetime | None = None
) -> LabReport:
    when = as_of or (T0 + timedelta(days=2))
    world = World(
        as_of=when,
        releases={
            "tpm-intelligence:Phase 3": ReleaseInfo(
                "tpm-intelligence:Phase 3",
                "Phase 3",
                utc(2026, 11, 30),
                utc(2026, 12, 14, 12),
                utc(2027, 1, 14, 12),
                utc(2027, 1, 20),
            )
        },
        features={},
        pull_requests={pr.key: pr for pr in prs},
    )
    return lab_report(world, "tpm-intelligence:Phase 3", RULES, ("preetdhindsa1",), since=since)
