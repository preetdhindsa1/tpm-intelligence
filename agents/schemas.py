"""Structured output shared by agents: a list of claims (CLAUDE.md section 8)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from verify.claims import Claim
from verify.facts import FactKind


class ClaimOut(BaseModel):
    """What the model returns for one claim (dates are ISO 8601 strings)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="One short sentence shown to people. Numbers as digits.")
    type: FactKind = Field(description="The kind of the primary fact (first ref).")
    refs: list[str] = Field(description="Fact keys from the fact sheet, primary first.")
    value: bool | float | str | None = Field(
        description="The primary fact's value as stated in the sentence."
    )

    def to_claim(self) -> Claim:
        """Convert to the fact checker's model."""
        return Claim(text=self.text, type=self.type, refs=tuple(self.refs), value=self.value)


class ClaimsOut(BaseModel):
    """An agent's whole answer."""

    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimOut]
