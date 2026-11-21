"""GitHub client: GraphQL error handling."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from collectors.github_poller.client import GitHubClient, GraphQLError
from collectors.http import HttpClient


def client(bodies: list[dict[str, Any]], sleeps: list[float]) -> GitHubClient:
    queue = list(bodies)
    http = HttpClient(
        "https://api.github.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=queue.pop(0))),
        sleep=sleeps.append,
        instrument=False,
    )
    return GitHubClient(http)


def test_graphql_returns_data() -> None:
    assert client([{"data": {"x": 1}}], []).graphql("{x}") == {"x": 1}


def test_graphql_errors_raise() -> None:
    with pytest.raises(GraphQLError, match="bad field"):
        client([{"errors": [{"message": "bad field"}]}], []).graphql("{x}")


def test_graphql_rate_limit_is_retried() -> None:
    sleeps: list[float] = []
    gh = client(
        [{"errors": [{"type": "RATE_LIMITED", "message": "slow down"}]}, {"data": {"x": 1}}], sleeps
    )
    assert gh.graphql("{x}") == {"x": 1}
    assert sleeps == [60.0]


def test_not_found_allowed_only_when_requested() -> None:
    body = {
        "data": {"repository": {"pr1": None}},
        "errors": [{"type": "NOT_FOUND", "message": "gone"}],
    }
    assert client([body], []).graphql("{x}", allow_not_found=True) == {"repository": {"pr1": None}}
    with pytest.raises(GraphQLError):
        client([body], []).graphql("{x}")
