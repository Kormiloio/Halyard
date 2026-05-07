"""AI plan and subscription configuration.

Plans describe how Halyard accounts for AI tool costs that are not captured
directly from API responses — seat subscriptions (Claude Max, Copilot),
credit-based tools (Cursor, Factory), and direct API billing.
"""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

AI_PLANS_FILENAME = "ai-plans.toml"

Billing = Literal["api", "seat", "credits"]
Allocation = Literal[
    "active_minutes", "session_count", "project_weight", "manual", "direct", "credits"
]


class AiPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    tool: str
    billing: Billing
    monthly_usd: float | None = None
    included_credits: int | None = None
    credit_to_usd: float | None = None
    allocation: Allocation = "direct"
    starts_on: date | None = None
    ends_on: date | None = None

    def is_active_in(self, year: int, month: int) -> bool:
        """Return True if this plan covers any part of the given month."""
        period_start = date(year, month, 1)
        period_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        if self.starts_on and self.starts_on >= period_end:
            return False
        return not (self.ends_on and self.ends_on < period_start)


def read_ai_plans(project_dir: Path) -> list[AiPlan]:
    """Read ai-plans.toml from the project directory. Returns empty list if absent."""
    path = project_dir / AI_PLANS_FILENAME
    if not path.exists():
        return []
    data = tomllib.loads(path.read_text())
    return [AiPlan.model_validate(plan) for plan in data.get("plan", [])]
