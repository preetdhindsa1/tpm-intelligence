"""GitHub webhook payloads -> the same normalized events the poller emits (ADR-0020).

The poller reads GraphQL; webhooks carry REST shapes. Each event here uses the poller's
identity, so a fact that arrives both ways (the poller keeps running as a 5-minute
reconciliation) gets the same event ID and is stored once:

* PR snapshot: ``updated_at`` (GraphQL ``updatedAt`` is the same instant and string).
* Review: the numeric review ID (GraphQL ``databaseId``).
* Comment: the numeric comment ID (GraphQL ``databaseId``).
* Check run: head SHA, name, conclusion and completion time.
* Planning issue: the snapshot from the payload; milestone, label and close history is
  fetched from the issue's GraphQL timeline, because only the timeline carries the IDs the
  poller uses (``issues`` payloads have none).

Comment text is never kept: only Prow review commands, as in the poller.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any, Literal

from collectors.github_poller import normalize as gh
from connectors.schema import GitHubPlanning, TeamConfig
from pipeline.events import (
    CheckCompleted,
    CheckConclusion,
    CommentPosted,
    NormalizedEvent,
    PullRequestObserved,
    ReviewSubmitted,
    Source,
    new_event,
)

Json = Mapping[str, Any]
Timeline = Callable[[str, int], list[dict[str, Any]]]


def _pr_state(pr: Json) -> Literal["open", "closed", "merged"]:
    if pr.get("merged") or pr.get("merged_at"):
        return "merged"
    return "closed" if pr.get("state") == "closed" else "open"


def pull_request_snapshot(repo: str, pr: Json, *, observed_at: datetime) -> NormalizedEvent:
    """``pull_request.observed`` from a REST pull request object."""
    payload = PullRequestObserved(
        repo=repo,
        number=pr["number"],
        title=pr["title"],
        body=pr.get("body") or "",
        author=(pr.get("user") or {}).get("login"),
        state=_pr_state(pr),
        labels=tuple(sorted(label["name"] for label in pr.get("labels") or [])),
        base_ref=(pr.get("base") or {}).get("ref"),
        head_sha=(pr.get("head") or {}).get("sha"),
        created_at=gh.parse_ts(pr["created_at"]),
        updated_at=gh.parse_ts(pr["updated_at"]),
        merged_at=gh.parse_ts(pr["merged_at"]) if pr.get("merged_at") else None,
        closed_at=gh.parse_ts(pr["closed_at"]) if pr.get("closed_at") else None,
        url=pr.get("html_url"),
    )
    return new_event(
        source=Source.GITHUB,
        subject=gh.pull_request_ref(repo, pr["number"]),
        occurred_at=payload.updated_at,
        observed_at=observed_at,
        payload=payload,
        identity=(pr["updated_at"],),
    )


def review_event(
    repo: str, number: int, review: Json, *, observed_at: datetime
) -> NormalizedEvent | None:
    """``pull_request.review_submitted``; None for pending (unsubmitted) reviews."""
    state = gh.REVIEW_STATES.get(str(review.get("state", "")).upper())
    if state is None or not review.get("submitted_at"):
        return None
    submitted = gh.parse_ts(review["submitted_at"])
    return new_event(
        source=Source.GITHUB,
        subject=gh.pull_request_ref(repo, number),
        occurred_at=submitted,
        observed_at=observed_at,
        payload=ReviewSubmitted(
            review_id=str(review["id"]),
            reviewer=(review.get("user") or {}).get("login"),
            state=state,
            submitted_at=submitted,
        ),
        identity=(review["id"],),
    )


def comment_event(
    repo: str, number: int, comment: Json, *, observed_at: datetime
) -> NormalizedEvent:
    """``pull_request.comment_posted``: author, time and Prow commands; no text."""
    posted = gh.parse_ts(comment["created_at"])
    return new_event(
        source=Source.GITHUB,
        subject=gh.pull_request_ref(repo, number),
        occurred_at=posted,
        observed_at=observed_at,
        payload=CommentPosted(
            comment_id=str(comment["id"]),
            author=(comment.get("user") or {}).get("login"),
            posted_at=posted,
            commands=gh.prow_commands(comment.get("body") or ""),
        ),
        identity=(comment["id"],),
    )


def check_events(repo: str, run: Json, *, observed_at: datetime) -> list[NormalizedEvent]:
    """``pull_request.check_completed`` for each PR the check run belongs to."""
    raw = run.get("conclusion")
    conclusion = (
        gh.CHECK_RUN_CONCLUSIONS.get(str(raw).upper(), CheckConclusion.PENDING)
        if raw
        else CheckConclusion.PENDING
    )
    when = gh.parse_ts(run["completed_at"]) if run.get("completed_at") else None
    head_sha = run["head_sha"]
    name = run["name"]
    return [
        new_event(
            source=Source.GITHUB,
            subject=gh.pull_request_ref(repo, pr["number"]),
            occurred_at=when or observed_at,
            observed_at=observed_at,
            payload=CheckCompleted(
                check_name=name, head_sha=head_sha, conclusion=conclusion, completed_at=when
            ),
            identity=(head_sha, name, conclusion.value, when.isoformat() if when else ""),
        )
        for pr in run.get("pull_requests") or []
    ]


class WebhookNormalizer:
    """Turns one delivery into events, using the team files to know which repo is what."""

    def __init__(self, teams: Iterable[TeamConfig], timeline: Timeline | None = None) -> None:
        self._code: set[str] = set()
        self._planning: dict[str, str] = {}  # planning repo -> release-key project
        for team in teams:
            self._code.update(r.lower() for r in team.code.repos)
            if isinstance(team.planning, GitHubPlanning):
                self._planning[team.planning.repo.lower()] = team.project
        self._timeline = timeline

    @property
    def repos(self) -> frozenset[str]:
        """Every repository a team lists (the receiver's allowlist)."""
        return frozenset(self._code | set(self._planning))

    def __call__(
        self, event: str, payload: dict[str, Any], observed_at: datetime
    ) -> list[NormalizedEvent]:
        """Events for one delivery; empty for anything not handled."""
        repo_name = str((payload.get("repository") or {}).get("full_name", ""))
        repo = repo_name.lower()
        # Planning first: a team may plan and code in the same repository (the demo team).
        if event == "issues" and repo in self._planning:
            return self._planning_issue(repo_name, payload, observed_at)
        if repo in self._code:
            return self._code_event(event, repo_name, payload, observed_at)
        return []

    def _code_event(
        self, event: str, repo: str, payload: dict[str, Any], observed_at: datetime
    ) -> list[NormalizedEvent]:
        out: list[NormalizedEvent] = []
        pr = payload.get("pull_request")
        if event in ("pull_request", "pull_request_review") and pr:
            out.append(pull_request_snapshot(repo, pr, observed_at=observed_at))
        if event == "pull_request_review" and pr and payload.get("review"):
            review = review_event(repo, pr["number"], payload["review"], observed_at=observed_at)
            if review is not None:
                out.append(review)
        issue = payload.get("issue") or {}
        if (
            event == "issue_comment"
            and payload.get("action") in ("created", "edited")
            and "pull_request" in issue
        ):
            out.append(
                comment_event(repo, issue["number"], payload["comment"], observed_at=observed_at)
            )
        if event == "check_run" and payload.get("check_run"):
            out.extend(check_events(repo, payload["check_run"], observed_at=observed_at))
        return out

    def _planning_issue(
        self, repo: str, payload: dict[str, Any], observed_at: datetime
    ) -> list[NormalizedEvent]:
        issue = payload["issue"]
        if gh.is_pull_request(issue):
            return []
        project = self._planning[repo.lower()]
        out = [gh.issue_snapshot(issue, repo=repo, project=project, observed_at=observed_at)]
        if self._timeline is not None:
            history = self._timeline(repo, issue["number"])
            out += gh.issue_history(
                history, repo=repo, number=issue["number"], project=project, observed_at=observed_at
            )
        return out
