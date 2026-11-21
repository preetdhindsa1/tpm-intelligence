"""The one HTTP client wrapper every collector uses (CLAUDE.md section 7).

Responsibilities:

* timeouts on every request;
* retries with exponential backoff and jitter for network errors, 5xx, and 429;
* rate limits: honours ``Retry-After`` and ``X-RateLimit-Reset`` (GitHub primary and
  secondary limits, Apache Jira's 429), and slows down *before* hitting zero;
* OpenTelemetry: one client span per attempt (httpx instrumentation) plus retry and
  wait metrics and structured logs.

``sleep``, ``clock`` and ``rng`` are injectable so tests run instantly and deterministically.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from opentelemetry import metrics

logger = logging.getLogger(__name__)

_meter = metrics.get_meter(__name__)
_retries = _meter.create_counter("http.client.retries", unit="{retry}")
_rate_limit_wait = _meter.create_counter("http.client.rate_limit_wait", unit="s")

RETRYABLE_STATUS = frozenset({500, 502, 503, 504})


class HttpError(Exception):
    """Non-retryable HTTP failure, or retries exhausted."""

    def __init__(self, message: str, *, status: int | None = None, url: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class RateLimitTooLongError(HttpError):
    """The server asked us to wait longer than ``RetryPolicy.max_rate_limit_wait_s``."""


@dataclass(frozen=True)
class RetryPolicy:
    """Retry and rate-limit settings."""

    max_attempts: int = 5
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0
    max_rate_limit_wait_s: float = 3700.0  # GitHub's hourly window plus margin
    min_remaining: int = 20  # pause until reset when the remaining quota drops this low


def _header_float(headers: Mapping[str, str], name: str) -> float | None:
    value = headers.get(name)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class HttpClient:
    """Synchronous HTTP client with retries, backoff, rate-limit handling and tracing."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 30.0,
        policy: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        rng: Callable[[], float] = random.random,
        instrument: bool = True,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers=dict(headers or {}),
            timeout=timeout_s,
            transport=transport,
            follow_redirects=True,
        )
        if instrument:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor.instrument_client(self._client)
        self.policy = policy or RetryPolicy()
        self._sleep = sleep
        self._clock = clock
        self._rng = rng

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------ public

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send a request, retrying as the policy allows. Returns only 2xx/3xx responses."""
        last_error: str = ""
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:  # connect/read timeouts, resets, DNS
                last_error = f"{type(exc).__name__}: {exc}"
                self._backoff(attempt, url, last_error)
                continue

            wait = self._rate_limit_wait(response)
            if wait is not None:
                self._wait_for_rate_limit(wait, url, response.status_code)
                last_error = f"rate limited ({response.status_code})"
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                self._backoff(attempt, url, last_error)
                continue
            if response.status_code >= 400:
                raise HttpError(
                    f"{method} {url} -> HTTP {response.status_code}: {response.text[:300]}",
                    status=response.status_code,
                    url=url,
                )
            self._pace(response)
            return response
        raise HttpError(
            f"{method} {url} failed after {self.policy.max_attempts} attempts: {last_error}",
            url=url,
        )

    def sleep(self, seconds: float) -> None:
        """Sleep using the injected clock (lets callers pause testably)."""
        self._sleep(seconds)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET with retries."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST with retries (only use for idempotent calls such as GraphQL queries)."""
        return self.request("POST", url, **kwargs)

    # ------------------------------------------------------------ internals

    def _rate_limit_wait(self, response: httpx.Response) -> float | None:
        """Seconds to wait if ``response`` is a rate-limit rejection, else None."""
        status = response.status_code
        if status not in (403, 429):
            return None
        headers = response.headers
        retry_after = _header_float(headers, "retry-after")
        if retry_after is not None:
            return retry_after
        if headers.get("x-ratelimit-remaining") == "0":
            reset = _header_float(headers, "x-ratelimit-reset")
            if reset is not None:
                return max(0.0, reset - self._clock()) + 1.0
        if status == 429:
            return self.policy.base_delay_s * 60  # e.g. Apache Jira: about 2 minutes
        if "rate limit" in response.text.lower():  # GitHub secondary limit without headers
            return 60.0
        return None  # a real 403 (permissions)

    def _wait_for_rate_limit(self, wait_s: float, url: str, status: int) -> None:
        if wait_s > self.policy.max_rate_limit_wait_s:
            raise RateLimitTooLongError(
                f"rate limit wait {wait_s:.0f}s exceeds limit", status=status, url=url
            )
        logger.warning("rate limited; waiting", extra={"url": url, "wait_s": round(wait_s, 1)})
        _rate_limit_wait.add(wait_s, {"reason": "rejected"})
        self._sleep(wait_s)

    def _backoff(self, attempt: int, url: str, reason: str) -> None:
        if attempt >= self.policy.max_attempts:
            return
        delay = min(self.policy.max_delay_s, self.policy.base_delay_s * 2 ** (attempt - 1))
        delay *= 0.5 + self._rng() / 2  # jitter in [50%, 100%]
        logger.warning(
            "retrying request",
            extra={"url": url, "attempt": attempt, "reason": reason, "delay_s": round(delay, 2)},
        )
        _retries.add(1, {"reason": reason.split(":")[0]})
        self._sleep(delay)

    def _pace(self, response: httpx.Response) -> None:
        """Pause until the window resets when the remaining quota is nearly used up."""
        remaining = _header_float(response.headers, "x-ratelimit-remaining")
        reset = _header_float(response.headers, "x-ratelimit-reset")
        if remaining is None or reset is None or remaining > self.policy.min_remaining:
            return
        wait = max(0.0, reset - self._clock()) + 1.0
        if wait > self.policy.max_rate_limit_wait_s:
            return
        logger.warning(
            "rate limit nearly exhausted; pausing until reset",
            extra={"remaining": int(remaining), "wait_s": round(wait, 1)},
        )
        _rate_limit_wait.add(wait, {"reason": "pacing"})
        self._sleep(wait)
