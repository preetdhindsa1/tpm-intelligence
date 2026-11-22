"""Kubernetes enhancement / KEP linking (ADR-0004)."""

from __future__ import annotations

from collections.abc import Sequence

from linker.rules import LinkCandidate, LinkIndex, PullRequestInfo, link_pull_request


class KepPack:
    """KEP numbers, tracking lists, and feature gates."""

    name = "kep"

    def link(
        self,
        pull_request: PullRequestInfo,
        index: LinkIndex,
    ) -> Sequence[LinkCandidate]:
        """Delegate to the existing deterministic KEP rules."""
        return link_pull_request(pull_request, index)
