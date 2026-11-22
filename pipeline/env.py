"""Reading optional settings that may hold a deployment placeholder.

Secrets added by hand after a deploy (GitHub token, Anthropic key, OAuth app) start with
the value ``unconfigured`` in Secret Manager so Cloud Run can start (ADR-0017). Code
treats that placeholder exactly like a missing value.
"""

from __future__ import annotations

import os

PLACEHOLDER = "unconfigured"


def configured(name: str) -> str | None:
    """The environment value, or None when it is empty or still the placeholder."""
    value = os.environ.get(name, "").strip()
    return None if not value or value == PLACEHOLDER else value
