"""Who is acting: signed requests from the web app and an approver allowlist (ADR-0016).

Reading is public. Actions (drafting or approving executive updates, deciding AI link
suggestions, saving scenarios, generating a risk note with paid AI) need an approver.

The browser never talks to the API with a secret. It calls a same-origin Next.js route,
which checks the GitHub sign-in (Auth.js) and forwards the call with:

    X-TPM-User:      the GitHub login
    X-TPM-Time:      Unix seconds
    X-TPM-Signature: hex HMAC-SHA256(secret, user \\n time \\n METHOD \\n path \\n sha256(body))

Version 2 (``X-TPM-Signature-Version: 2``, ADR-0034) appends ``\\n tenant``, the tenant in
``X-TPM-Tenant`` (the demo when absent). Version 1 is accepted for the public demo only.

The API recomputes the signature with the shared secret, rejects it after
``MAX_AGE`` seconds, and checks the login against ``APPROVERS``. The API is the only
place that enforces permissions; the web app only decides what to show.

``AUTH_MODE``:
- ``required`` (default): unsigned actions are refused. With no secret configured,
  every action is refused (fail closed).
- ``local``: for development on a laptop. Unsigned requests act as the local user, as before
  sign-in existed. Signed requests are still verified.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request

from pipeline.store.tenancy import DEMO

MAX_AGE = 300  # seconds a signature stays valid
LOCAL_LOGIN = "local"


@dataclass(frozen=True)
class AuthConfig:
    """How actions are authorised."""

    mode: Literal["required", "local"]
    secret: bytes | None
    approvers: frozenset[str]

    @classmethod
    def from_env(cls) -> AuthConfig:
        """``AUTH_MODE``, ``TPM_ACTION_SECRET``, ``APPROVERS`` (comma-separated logins)."""
        mode = os.getenv("AUTH_MODE", "required").strip().lower()
        if mode not in ("required", "local"):
            raise ValueError(f"AUTH_MODE must be 'required' or 'local', not {mode!r}")
        secret = os.getenv("TPM_ACTION_SECRET", "")
        approvers = frozenset(
            a.strip().lower() for a in os.getenv("APPROVERS", "").split(",") if a.strip()
        )
        return cls(mode, secret.encode() if secret else None, approvers)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Actor:
    """A person making a request."""

    login: str
    approver: bool
    signed_in: bool

    @property
    def recorded_as(self) -> str:
        """How decisions record this person."""
        if not self.signed_in:
            return f"user:{self.login} (local, unauthenticated)"
        return f"user:{self.login}"


ANONYMOUS = Actor("anonymous", approver=False, signed_in=False)


def signature(
    secret: bytes,
    user: str,
    ts: str,
    method: str,
    path: str,
    body: bytes,
    tenant: str | None = None,
) -> str:
    """The HMAC the web app sends and the API checks. Version 2 adds the tenant as a sixth
    line (ADR-0034), so a signature for one tenant cannot be replayed against another."""
    digest = hashlib.sha256(body).hexdigest()
    lines = [user, ts, method.upper(), path, digest]
    if tenant is not None:
        lines.append(tenant)
    message = "\n".join(lines).encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _path(request: Request) -> str:
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


async def identify(
    request: Request, config: AuthConfig, now: Callable[[], float] = time.time
) -> Actor:
    """Who is making this request (anonymous if unsigned in required mode)."""
    user = request.headers.get("x-tpm-user")
    if user is None:
        if config.mode == "local":
            return Actor(LOCAL_LOGIN, approver=True, signed_in=False)
        return ANONYMOUS
    ts = request.headers.get("x-tpm-time", "")
    sig = request.headers.get("x-tpm-signature", "")
    if config.secret is None:
        raise HTTPException(401, "sign-in is not configured on this server")
    try:
        age = abs(now() - int(ts))
    except ValueError as exc:
        raise HTTPException(401, "bad signature time") from exc
    if age > MAX_AGE:
        raise HTTPException(401, "signature expired")
    version = request.headers.get("x-tpm-signature-version", "1").strip()
    named = (request.headers.get("x-tpm-tenant") or "").strip() or DEMO
    if version == "2":
        tenant: str | None = named
    elif version == "1" and named == DEMO:
        tenant = None  # version 1 covers the public demo only
    else:
        raise HTTPException(401, "this request needs a version 2 signature")
    expected = signature(
        config.secret, user, ts, request.method, _path(request), await request.body(), tenant
    )
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "bad signature")
    login = user.lower()
    access = getattr(request.state, "access", None)
    if access is not None and access.tenant != DEMO:  # a private tenant: its members' roles
        return Actor(login, approver=access.approver, signed_in=True)
    return Actor(login, approver=login in config.approvers, signed_in=True)


async def require_approver(
    request: Request, config: AuthConfig, now: Callable[[], float] = time.time
) -> Actor:
    """The acting approver, or 401 (not signed in) / 403 (not on the allowlist)."""
    actor = await identify(request, config, now)
    if actor is ANONYMOUS:
        raise HTTPException(401, "sign in with GitHub to do this")
    if not actor.approver:
        raise HTTPException(403, f"{actor.login} is not an approver")
    return actor
