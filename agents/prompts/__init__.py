"""Versioned prompt files (CLAUDE.md section 8): ``agents/prompts/<name>.v<N>.md``.

A prompt's identity is its name, version and the SHA-256 of its text. The SHA is part of the
cache fingerprint, so editing a prompt file can never serve a stale cached answer, and
prompt changes are visible in review and must pass ``make evals``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
_NAME = re.compile(r"^(?P<name>[a-z0-9_]+)\.v(?P<version>\d+)\.md$")


@dataclass(frozen=True)
class Prompt:
    """A loaded prompt."""

    name: str
    version: int
    text: str

    @property
    def sha(self) -> str:
        """SHA-256 of the text."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def label(self) -> str:
        """``name.vN`` for logs and the usage ledger."""
        return f"{self.name}.v{self.version}"


def load_prompt(name: str, version: int | None = None, directory: Path = PROMPTS_DIR) -> Prompt:
    """Load ``name`` at ``version``, or its highest version."""
    found = {
        int(m["version"]): p
        for p in directory.glob(f"{name}.v*.md")
        if (m := _NAME.match(p.name)) and m["name"] == name
    }
    if not found:
        raise FileNotFoundError(f"no prompt files for {name!r} in {directory}")
    v = max(found) if version is None else version
    if v not in found:
        raise FileNotFoundError(f"{name}.v{v}.md not found")
    return Prompt(name, v, found[v].read_text())
