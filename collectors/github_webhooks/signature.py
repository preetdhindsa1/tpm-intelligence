"""GitHub webhook signatures (``X-Hub-Signature-256``). Pure.

GitHub signs each delivery body with HMAC-SHA256 using the webhook secret and sends
``sha256=<hex>``. Compare in constant time so the check leaks nothing through timing.
"""

from __future__ import annotations

import hashlib
import hmac

PREFIX = "sha256="


def sign(secret: str, body: bytes) -> str:
    """The header value GitHub would send for ``body`` (used by tests and the demo tool)."""
    return PREFIX + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, header: str | None) -> bool:
    """True only for a well-formed header that matches ``body`` under ``secret``."""
    if not secret or not header or not header.startswith(PREFIX):
        return False
    return hmac.compare_digest(sign(secret, body), header)
