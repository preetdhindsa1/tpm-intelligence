"""GraphQL documents. The fixture script and the poller share these, so tests see the
exact response shape production sees."""

from __future__ import annotations

PR_FIELDS = """
fragment PRFields on PullRequest {
  number
  title
  body
  url
  state
  createdAt
  updatedAt
  mergedAt
  closedAt
  baseRefName
  repository { nameWithOwner }
  author { login __typename }
  labels(first: 50) { nodes { name } }
  reviews(first: 100) {
    pageInfo { hasNextPage endCursor }
    nodes { databaseId author { login __typename } state submittedAt body }
  }
  comments(first: 100) {
    pageInfo { hasNextPage endCursor }
    nodes { databaseId author { login __typename } createdAt body }
  }
  commits(last: 1) {
    nodes {
      commit {
        oid
        statusCheckRollup {
          contexts(first: 100) {
            nodes {
              __typename
              ... on CheckRun { name conclusion status completedAt }
              ... on StatusContext { context state createdAt }
            }
          }
        }
      }
    }
  }
}
"""

SEARCH_PRS = (
    PR_FIELDS
    + """
query SearchPRs($q: String!, $first: Int!, $after: String) {
  rateLimit { cost remaining resetAt }
  search(query: $q, type: ISSUE, first: $first, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ...PRFields }
  }
}
"""
)

MORE_REVIEWS = """
query MoreReviews($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { databaseId author { login __typename } state submittedAt body }
      }
    }
  }
}
"""


MORE_COMMENTS = """
query MoreComments($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      comments(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { databaseId author { login __typename } createdAt body }
      }
    }
  }
}
"""


def search_prs_query(*, lane: bool) -> str:
    """PR search document. Lane teams also ask for paths, size and commit messages."""
    if not lane:
        return SEARCH_PRS
    return (
        PR_FIELDS
        + LANE_FIELDS
        + """
query SearchPRs($q: String!, $first: Int!, $after: String) {
  rateLimit { cost remaining resetAt }
  search(query: $q, type: ISSUE, first: $first, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ...PRFields ...LaneFields }
  }
}
"""
    )


LANE_FIELDS = """
fragment LaneFields on PullRequest {
  headRefName
  additions
  deletions
  mergeable
  files(first: 100) {
    pageInfo { hasNextPage }
    nodes { path }
  }
  history: commits(last: 30) {
    pageInfo { hasNextPage }
    nodes { commit { committedDate messageHeadline messageBody } }
  }
}
"""


def prs_by_number_query(owner: str, name: str, numbers: list[int], *, lane: bool = False) -> str:
    """One query fetching several PRs by number via aliases (``pr143709: pullRequest(...)``)."""
    if not numbers:
        raise ValueError("numbers must not be empty")
    spread = "...PRFields ...LaneFields" if lane else "...PRFields"
    fields = "\n".join(f"    pr{n}: pullRequest(number: {int(n)}) {{ {spread} }}" for n in numbers)
    extra = LANE_FIELDS if lane else ""
    return (
        PR_FIELDS
        + extra
        + f"""
query PRsByNumber {{
  rateLimit {{ cost remaining resetAt }}
  repository(owner: "{owner}", name: "{name}") {{
{fields}
  }}
}}
"""
    )


# Issue history. The REST issue events/timeline endpoints are capped at about 300 items and
# drop the newest events on long-lived KEPs (CLAUDE.md section 7), so history comes from here.
ISSUE_TIMELINE = """
query IssueTimeline($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      timelineItems(
        first: 100
        after: $after
        itemTypes: [MILESTONED_EVENT, DEMILESTONED_EVENT, LABELED_EVENT, UNLABELED_EVENT,
                    CLOSED_EVENT, REOPENED_EVENT]
      ) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          __typename
          ... on MilestonedEvent { id createdAt milestoneTitle }
          ... on DemilestonedEvent { id createdAt milestoneTitle }
          ... on LabeledEvent { id createdAt label { name } }
          ... on UnlabeledEvent { id createdAt label { name } }
          ... on ClosedEvent { id createdAt stateReason }
          ... on ReopenedEvent { id createdAt }
        }
      }
    }
  }
}
"""
