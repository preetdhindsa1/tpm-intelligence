"""Link pack protocol — implement one per planning style, not per company."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from linker.rules import LinkCandidate, LinkIndex, PullRequestInfo


class LinkPack(Protocol):
    """Deterministic PR → work-item linking for one planning style."""

    name: str

    def link(
        self,
        pull_request: PullRequestInfo,
        index: LinkIndex,
    ) -> Sequence[LinkCandidate]:
        """Propose links for one PR against the indexed work items."""
        ...
