"""What an agent returns: individual claims, each citing the facts behind it (CLAUDE.md 8)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from verify.facts import FactKind

ClaimValue = int | float | bool | str | datetime | None


class Claim(BaseModel):
    """One checkable statement.

    ``value`` is compared with the first fact in ``refs``. Further refs are context the
    sentence also relies on; they must exist, and any number in ``text`` must match one of
    them. A claim with no refs, or no value, has no supporting data and is removed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, description="The sentence shown to people.")
    type: FactKind = Field(description="Kind of the value; must match the first ref's kind.")
    refs: tuple[str, ...] = Field(description="Fact keys from the fact sheet, primary first.")
    value: ClaimValue = Field(description="The value the sentence states for refs[0].")
