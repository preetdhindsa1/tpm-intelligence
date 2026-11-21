"""HTTP wrapper: retries, backoff, rate limits, non-retryable errors."""

from __future__ import annotations

import httpx
import pytest

from collectors.http import HttpClient, HttpError, RateLimitTooLongError, RetryPolicy

NOW = 1_800_000_000.0


def make(
    responses: list[httpx.Response | Exception], **policy: float
) -> tuple[HttpClient, list[float], list[httpx.Request]]:
    sleeps: list[float] = []
    requests: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client = HttpClient(
        "https://api.example",
        transport=httpx.MockTransport(handler),
        policy=RetryPolicy(**policy),  # type: ignore[arg-type]
        sleep=sleeps.append,
        clock=lambda: NOW,
        rng=lambda: 1.0,  # no jitter: delay = full backoff
        instrument=False,
    )
    return client, sleeps, requests


def ok(**headers: str) -> httpx.Response:
    return httpx.Response(200, json={"ok": True}, headers=headers)


def test_success_first_try() -> None:
    client, sleeps, requests = make([ok()])
    assert client.get("/x").json() == {"ok": True}
    assert (sleeps, len(requests)) == ([], 1)


def test_5xx_then_success_backs_off_exponentially() -> None:
    client, sleeps, _ = make([httpx.Response(502), httpx.Response(503), ok()])
    assert client.get("/x").status_code == 200
    assert sleeps == [1.0, 2.0]


def test_network_error_is_retried() -> None:
    client, sleeps, _ = make([httpx.ConnectTimeout("slow"), ok()])
    assert client.get("/x").status_code == 200
    assert sleeps == [1.0]


def test_jitter_shrinks_delay_to_at_least_half() -> None:
    client, sleeps, _ = make([httpx.Response(500), ok()])
    client._rng = lambda: 0.0
    client.get("/x")
    assert sleeps == [0.5]


def test_gives_up_after_max_attempts() -> None:
    client, sleeps, requests = make([httpx.Response(500)] * 3, max_attempts=3)
    with pytest.raises(HttpError, match="after 3 attempts"):
        client.get("/x")
    assert len(requests) == 3
    assert sleeps == [1.0, 2.0]  # no sleep after the final attempt


@pytest.mark.parametrize("status", [400, 401, 404, 422])
def test_client_errors_are_not_retried(status: int) -> None:
    client, sleeps, requests = make([httpx.Response(status, text="nope")])
    with pytest.raises(HttpError) as info:
        client.get("/x")
    assert info.value.status == status
    assert (sleeps, len(requests)) == ([], 1)


def test_plain_403_permission_error_is_not_retried() -> None:
    client, _, requests = make([httpx.Response(403, text="Resource not accessible")])
    with pytest.raises(HttpError):
        client.get("/x")
    assert len(requests) == 1


def test_retry_after_header_is_honoured() -> None:
    client, sleeps, _ = make([httpx.Response(429, headers={"retry-after": "120"}), ok()])
    client.get("/x")
    assert sleeps == [120.0]


def test_github_primary_rate_limit_waits_until_reset() -> None:
    limited = httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(NOW + 300))}
    )
    client, sleeps, _ = make([limited, ok()])
    client.get("/x")
    assert sleeps == [301.0]


def test_github_secondary_limit_without_headers() -> None:
    limited = httpx.Response(403, text="You have exceeded a secondary rate limit.")
    client, sleeps, _ = make([limited, ok()])
    client.get("/x")
    assert sleeps == [60.0]


def test_jira_style_429_without_headers_waits_about_two_minutes() -> None:
    client, sleeps, _ = make([httpx.Response(429), ok()], base_delay_s=2.0)
    client.get("/x")
    assert sleeps == [120.0]


def test_refuses_absurd_rate_limit_waits() -> None:
    limited = httpx.Response(429, headers={"retry-after": "99999"})
    client, _, _ = make([limited])
    with pytest.raises(RateLimitTooLongError):
        client.get("/x")


def test_paces_when_quota_nearly_exhausted() -> None:
    reset = str(int(NOW + 60))
    client, sleeps, _ = make([ok(**{"x-ratelimit-remaining": "5", "x-ratelimit-reset": reset})])
    client.get("/x")
    assert sleeps == [61.0]


def test_no_pacing_with_plenty_of_quota() -> None:
    reset = str(int(NOW + 60))
    client, sleeps, _ = make([ok(**{"x-ratelimit-remaining": "4000", "x-ratelimit-reset": reset})])
    client.get("/x")
    assert sleeps == []


def test_timeout_is_configured() -> None:
    client = HttpClient("https://api.example", timeout_s=7.5, instrument=False)
    assert client._client.timeout.read == 7.5
