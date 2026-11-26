"""Secrets by reference, never stored (ADR-0035, #233).

A team config names a secret (``secret_refs: {github: github-token}``); this resolves the
name for one tenant:

- ``SECRETS_BACKEND=gcp``: Secret Manager secret ``tenant-<tenant>-<ref>`` (latest
  version), read with the service account's credentials;
- otherwise the environment variable ``TENANT_<TENANT>_<REF>`` (upper case, ``-`` → ``_``).

The public demo keeps today's variables (``GITHUB_TOKEN``, ...): it never resolves refs.
A missing secret is ``None`` and the caller skips that connector with a reason. It never
falls back to another tenant's secret or to the demo's.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from collections.abc import Callable

from pipeline.store.tenancy import DEMO, valid

logger = logging.getLogger(__name__)
REF = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def secret_name(tenant: str, ref: str) -> str:
    """``tenant-<tenant>-<ref>``: the Secret Manager name, also shown on the Connect page."""
    if not REF.match(ref):
        raise ValueError(f"not a secret reference: {ref!r}")
    return f"tenant-{valid(tenant)}-{ref}"


def env_name(tenant: str, ref: str) -> str:
    return secret_name(tenant, ref).upper().replace("-", "_")


def _from_gcp(name: str) -> str | None:  # pragma: no cover - needs Google Cloud
    import google.auth
    from google.auth.transport.requests import Request

    from collectors.http import HttpClient, HttpError

    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())  # type: ignore[no-untyped-call]
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or project
    url = f"/v1/projects/{project}/secrets/{name}/versions/latest:access"
    headers = {"Authorization": f"Bearer {credentials.token}"}
    with HttpClient("https://secretmanager.googleapis.com", headers=headers) as http:
        try:
            body = http.get(url).json()
        except HttpError as exc:
            if exc.status == 404:
                return None
            raise
    return base64.b64decode(body["payload"]["data"]).decode()


def resolve(tenant: str, ref: str, *, gcp: Callable[[str], str | None] = _from_gcp) -> str | None:
    """The secret value for ``ref`` in ``tenant``, or None if it is not set."""
    if tenant == DEMO:
        raise ValueError("the public demo uses its own environment variables, not refs")
    if os.getenv("SECRETS_BACKEND", "env").lower() == "gcp":
        return gcp(secret_name(tenant, ref))
    value = os.getenv(env_name(tenant, ref), "")
    return value or None


def team_secret(team: object, purpose: str, demo_env: str) -> str | None:
    """The secret a team's collector uses for ``purpose`` ("github", "jira"), for the current
    tenant: the demo's environment variable for the public demo, else the team's ref."""
    from pipeline.env import configured
    from pipeline.store.tenancy import current_tenant

    tenant = current_tenant.get()
    if tenant is None:
        raise RuntimeError("no tenant: secrets are per tenant (ADR-0035)")
    if tenant == DEMO:
        return configured(demo_env)
    ref = getattr(team, "secret_refs", {}).get(purpose) if team is not None else None
    return resolve(tenant, ref) if ref else None
