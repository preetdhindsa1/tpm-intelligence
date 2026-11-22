"""AI configuration from the environment (CLAUDE.md section 8: models come from config).

Model IDs are never hard-coded at call sites: every task names a *role* (``simple`` or
``summary``) and the role maps to a model here.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelRole(StrEnum):
    """Cheaper model for simple tasks, stronger model for summaries (CLAUDE.md section 8)."""

    SIMPLE = "simple"
    SUMMARY = "summary"


class AISettings(BaseSettings):
    """``AI_*`` environment variables. ``ANTHROPIC_API_KEY`` is read by the SDK itself."""

    model_config = SettingsConfigDict(env_prefix="AI_", extra="ignore")

    model_simple: str = "claude-haiku-5-5"
    model_summary: str = "claude-opus-5-5"
    daily_budget_usd: float = Field(2.0, gt=0)
    slow_at: float = Field(0.8, gt=0, le=1)  # fraction of the cap where non-essential calls slow
    slow_interval_s: float = Field(60.0, ge=0)  # min gap between non-essential calls when slow
    essential_overage: float = Field(0.0, ge=0)  # essential calls may exceed the cap by this share
    odds_change_points: float = Field(10.0, gt=0)  # re-run only if odds move this much
    trace_content: bool = True  # record prompts/outputs in spans (public data only)
    timeout_s: float = Field(120.0, gt=0)
    max_retries: int = Field(3, ge=0)

    def model_for(self, role: ModelRole) -> str:
        """Model ID for a role."""
        return self.model_simple if role is ModelRole.SIMPLE else self.model_summary
