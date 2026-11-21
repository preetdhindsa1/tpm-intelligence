"""GitHub API access: REST (issues, issue events, file contents) and GraphQL (PRs)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping
from typing import Any

from collectors.http import HttpClient, HttpError, RetryPolicy

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class GraphQLError(HttpError):
    """GraphQL returned errors."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("; ".join(str(e.get("message")) for e in errors))
        self.errors = errors

    @property
    def rate_limited(self) -> bool:
        """True when GitHub rejected the query for rate limiting."""
        return any(e.get("type") == "RATE_LIMITED" for e in self.errors)


class GitHubClient:
    """Read-only GitHub client. All calls go through :class:`HttpClient`."""

    def __init__(self, http: HttpClient, *, graphql_rate_limit_retries: int = 2) -> None:
        self._http = http
        self._graphql_retries = graphql_rate_limit_retries

    @classmethod
    def from_token(cls, token: str, **http_kwargs: Any) -> GitHubClient:
        """Build a client authenticated with a (read-only) token."""
        http = HttpClient(
            API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "tpm-intelligence-poller",
            },
            policy=http_kwargs.pop("policy", RetryPolicy()),
            **http_kwargs,
        )
        return cls(http)

    def close(self) -> None:
        """Release connections."""
        self._http.close()

    # ------------------------------------------------------------ REST

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET one REST resource."""
        return self._http.get(path, params=dict(params or {})).json()

    def paginate(self, path: str, params: Mapping[str, Any] | None = None) -> Iterator[Any]:
        """Yield every item of a paginated REST list, following ``Link: rel="next"``."""
        url: str | None = path
        query: dict[str, Any] | None = {"per_page": 100, **dict(params or {})}
        while url:
            response = self._http.get(url, params=query)
            yield from response.json()
            match = _NEXT_LINK.search(response.headers.get("link", ""))
            url, query = (match.group(1), None) if match else (None, None)

    def get_text(self, path: str) -> str:
        """GET a repository file's raw contents (``/repos/{o}/{r}/contents/{path}``)."""
        response = self._http.get(path, headers={"Accept": "application/vnd.github.raw"})
        return response.text

    # ------------------------------------------------------------ GraphQL

    def graphql(
        self,
        query: str,
        variables: Mapping[str, Any] | None = None,
        *,
        allow_not_found: bool = False,
    ) -> dict[str, Any]:
        """Run a GraphQL query and return ``data``. Raises :class:`GraphQLError` on errors.

        With ``allow_not_found``, NOT_FOUND errors (e.g. a deleted PR in a batch) are
        logged and the partial ``data`` is returned with ``None`` for the missing parts.
        """
        payload = {"query": query, "variables": dict(variables or {})}
        for attempt in range(self._graphql_retries + 1):
            body = self._http.post("/graphql", json=payload).json()
            errors = body.get("errors")
            if errors and allow_not_found and all(e.get("type") == "NOT_FOUND" for e in errors):
                logger.warning("GraphQL objects not found", extra={"errors": errors})
                errors = None
            if not errors:
                data: dict[str, Any] = body["data"]
                return data
            error = GraphQLError(errors)
            if not error.rate_limited or attempt == self._graphql_retries:
                raise error
            logger.warning("GraphQL rate limited; retrying", extra={"attempt": attempt + 1})
            self._http.sleep(60.0)
        raise AssertionError("unreachable")
