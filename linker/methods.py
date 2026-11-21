"""Link methods and statuses (CLAUDE.md section 6).

Methods are listed strongest first. Confidence *values* per method are defined in M4
(ADR-0004); the database stores the method, a numeric confidence and a status.
"""

from __future__ import annotations

from enum import StrEnum


class LinkMethod(StrEnum):
    """How a PR -> work item link was established, strongest evidence first."""

    EXPLICIT_KEY = "explicit_key"
    TRACKING_ISSUE_LINK = "tracking_issue_link"
    REMOTE_LINK = "remote_link"
    FEATURE_GATE = "feature_gate"
    LABELS = "labels"
    AI_SUGGESTED = "ai_suggested"

    @property
    def rank(self) -> int:
        """0 = strongest. Use to pick the best method when several apply."""
        return list(LinkMethod).index(self)


class LinkStatus(StrEnum):
    """Lifecycle of a link.

    ``verified`` links count as facts. ``suggested`` links (always the case for
    ``ai_suggested`` until a rule or a person confirms them) are shown but never counted.
    """

    VERIFIED = "verified"
    SUGGESTED = "suggested"
    REJECTED = "rejected"
