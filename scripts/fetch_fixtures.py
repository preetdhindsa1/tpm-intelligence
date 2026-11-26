"""Fetch the real #6395 fixtures (CLAUDE.md section 11) into tests/fixtures/github/.

Uses the same client and GraphQL documents as the poller, so tests see production shapes.
Logins in structured fields (PR authors, reviewers) are replaced with stable placeholders
(``user-1``, ``user-2``, ...): the platform measures flow, not people.

    GITHUB_TOKEN=... uv run python scripts/fetch_fixtures.py
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collectors.github_poller.client import GitHubClient
from collectors.github_poller.queries import ISSUE_TIMELINE, MORE_REVIEWS, prs_by_number_query

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "github"
ENH = "/repos/kubernetes/enhancements"
KEP = 6395
# Second freeze removal/re-add case; its REST event history is capped (CLAUDE.md section 7).
LONG_KEP = 2570
KEP_YAML = "keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/kep.yaml"
# Issue-description tracking list + the passing-mention case (#143644).
PRS = [143442, 143445, 143474, 143522, 143644, 143709]

_aliases: dict[str, str] = {}


def alias(login: str | None) -> str | None:
    """Stable placeholder per login."""
    if login is None:
        return None
    return _aliases.setdefault(login, f"user-{len(_aliases) + 1}")


def trim_issue(issue: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "number",
        "title",
        "state",
        "state_reason",
        "created_at",
        "updated_at",
        "closed_at",
        "html_url",
        "body",
    )
    out = {k: issue.get(k) for k in keep}
    out["labels"] = [{"name": label["name"]} for label in issue["labels"]]
    m = issue.get("milestone")
    out["milestone"] = {"title": m["title"], "number": m["number"]} if m else None
    return out


def timeline(gh: GitHubClient, number: int) -> list[dict[str, Any]]:
    """Raw GraphQL timelineItems nodes (all pages), exactly as the poller receives them."""
    nodes: list[dict[str, Any]] = []
    after = None
    while True:
        data = gh.graphql(
            ISSUE_TIMELINE,
            {"owner": "kubernetes", "name": "enhancements", "number": number, "after": after},
        )
        items = data["repository"]["issue"]["timelineItems"]
        nodes.extend(items["nodes"])
        if not items["pageInfo"]["hasNextPage"]:
            return nodes
        after = items["pageInfo"]["endCursor"]


def scrub_pr(node: dict[str, Any]) -> dict[str, Any]:
    if node.get("author"):
        node["author"] = {"login": alias(node["author"]["login"])}
    for review in node["reviews"]["nodes"]:
        if review.get("author"):
            review["author"] = {"login": alias(review["author"]["login"])}
    return node


def main() -> None:
    gh = GitHubClient.from_token(os.environ["GITHUB_TOKEN"])
    OUT.mkdir(parents=True, exist_ok=True)

    issue = gh.get_json(f"{ENH}/issues/{KEP}")
    long_issue = gh.get_json(f"{ENH}/issues/{LONG_KEP}")
    rest_events_long = sum(1 for _ in gh.paginate(f"{ENH}/issues/{LONG_KEP}/events"))
    kep_yaml = gh.get_text(f"{ENH}/contents/{KEP_YAML}")

    data = gh.graphql(prs_by_number_query("kubernetes", "kubernetes", PRS))
    nodes = []
    for n in PRS:
        node = data["repository"][f"pr{n}"]
        page = node["reviews"]["pageInfo"]
        while page["hasNextPage"]:  # complete review history for the fixture
            more = gh.graphql(
                MORE_REVIEWS,
                {
                    "owner": "kubernetes",
                    "name": "kubernetes",
                    "number": n,
                    "after": page["endCursor"],
                },
            )
            reviews = more["repository"]["pullRequest"]["reviews"]
            node["reviews"]["nodes"].extend(reviews["nodes"])
            page = reviews["pageInfo"]
        node["reviews"]["pageInfo"] = {"hasNextPage": False, "endCursor": None}
        nodes.append(scrub_pr(node))

    def write(name: str, obj: Any) -> None:
        (OUT / name).write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")

    write("issue_6395.json", trim_issue(issue))
    write("issue_6395_timeline.json", timeline(gh, KEP))
    write("issue_2570.json", trim_issue(long_issue))
    write("issue_2570_timeline.json", timeline(gh, LONG_KEP))
    write("prs_6395.json", nodes)
    (OUT / "kep_6395.yaml").write_text(kep_yaml)
    write(
        "meta.json",
        {
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "kep_yaml_path": KEP_YAML,
            "prs": PRS,
            "rest_event_count_2570": rest_events_long,
            "note": "Trimmed real data. PR author/reviewer logins replaced by placeholders.",
        },
    )
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    from pipeline.store.tenancy import cli_tenant, use_tenant

    with use_tenant(cli_tenant()):  # TPM_TENANT, else the public demo (ADR-0034)
        main()
