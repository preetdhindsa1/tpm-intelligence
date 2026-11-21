"""Does a PR's code count for the release? (CLAUDE.md section 6) Pure, no I/O.

Code counts if merged before Code Freeze, or later with an approved exception. Kubernetes
records exception approval outside GitHub, so the evidence we accept (approved 2026-11-21)
is: **after Code Freeze, the feature was added back to the release milestone** (as #6395
was at 2026-11-21 00:33:55Z, after its main PR merged at 2026-11-20 23:28:24Z).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from engine.projection import Feature, PullRequest, ReleaseInfo


class CodeStatus(StrEnum):
    """Outcome of the freeze check for one PR."""

    MERGED_BEFORE_FREEZE = "merged_before_freeze"
    MERGED_AFTER_FREEZE_WITH_EXCEPTION = "merged_after_freeze_with_exception"
    MERGED_AFTER_FREEZE_NO_EXCEPTION = "merged_after_freeze_no_exception"
    NOT_MERGED = "not_merged"
    CLOSED_UNMERGED = "closed_unmerged"
    NO_FREEZE_DATE = "no_freeze_date"


COUNTS = frozenset({CodeStatus.MERGED_BEFORE_FREEZE, CodeStatus.MERGED_AFTER_FREEZE_WITH_EXCEPTION})


@dataclass(frozen=True)
class FreezeCheck:
    """Freeze decision with the times it was based on."""

    pull_request_key: str
    status: CodeStatus
    merged_at: datetime | None
    code_freeze_at: datetime | None
    exception_evidence_at: datetime | None = None

    @property
    def counts(self) -> bool:
        """True if the code counts for the release."""
        return self.status in COUNTS


def readded_after_freeze(feature: Feature, release: ReleaseInfo) -> datetime | None:
    """First time the feature was added back to the release after Code Freeze, if ever."""
    freeze = release.code_freeze_at
    if freeze is None:
        return None
    for change in feature.membership:
        if change.release_key == release.key and change.added and change.at > freeze:
            return change.at
    return None


def check_pr(pr: PullRequest, feature: Feature, release: ReleaseInfo) -> FreezeCheck:
    """Classify one linked PR against the release's Code Freeze."""
    freeze = release.code_freeze_at

    def result(status: CodeStatus, evidence: datetime | None = None) -> FreezeCheck:
        return FreezeCheck(pr.key, status, pr.merged_at, freeze, evidence)

    if freeze is None:
        return result(CodeStatus.NO_FREEZE_DATE)
    if pr.state == "closed":
        return result(CodeStatus.CLOSED_UNMERGED)
    if pr.merged_at is None:
        return result(CodeStatus.NOT_MERGED)
    if pr.merged_at <= freeze:
        return result(CodeStatus.MERGED_BEFORE_FREEZE)
    readded = readded_after_freeze(feature, release)
    if readded is not None:
        return result(CodeStatus.MERGED_AFTER_FREEZE_WITH_EXCEPTION, readded)
    return result(CodeStatus.MERGED_AFTER_FREEZE_NO_EXCEPTION)
