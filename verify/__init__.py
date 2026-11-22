"""Fact checker: every AI claim is verified against engine facts before anyone sees it."""

from verify.checker import CheckedClaim, CheckReport, Reason, Verdict, check_claim, check_claims
from verify.claims import Claim
from verify.facts import Fact, FactKind, FactSheet, fact_key

__all__ = [
    "CheckReport",
    "CheckedClaim",
    "Claim",
    "Fact",
    "FactKind",
    "FactSheet",
    "Reason",
    "Verdict",
    "check_claim",
    "check_claims",
    "fact_key",
]
