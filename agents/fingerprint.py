"""Cache key for an AI call: a hash of everything that determines its output (CLAUDE.md 8).

Same task, prompt version, model and input facts -> same key -> reuse the stored result
instead of paying for another call. Pure, no I/O.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def fingerprint(*, task: str, prompt_sha: str, model: str, inputs: Any) -> str:
    """SHA-256 over canonical JSON (sorted keys, no whitespace, ISO dates via ``str``)."""
    payload = {"task": task, "prompt": prompt_sha, "model": model, "inputs": inputs}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
