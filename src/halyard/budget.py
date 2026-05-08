"""Budget limits — per-project daily/monthly spend caps with warn-only enforcement."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import tomli_w

from halyard.ai_log import AI_LOG_FILENAME, AiSession, parse_sessions

_BUDGETS_FILE = Path.home() / ".halyard" / "budgets.toml"


@dataclass
class ProjectBudget:
    daily_usd: float | None = None
    monthly_usd: float | None = None


@dataclass
class BudgetStatus:
    slug: str
    today_spend: float
    today_limit: float | None
    month_spend: float
    month_limit: float | None


def load_budgets() -> dict[str, ProjectBudget]:
    """Read ~/.halyard/budgets.toml. Returns empty dict if absent or corrupted."""
    if not _BUDGETS_FILE.exists():
        return {}
    try:
        data = tomllib.loads(_BUDGETS_FILE.read_text())
    except tomllib.TOMLDecodeError:
        return {}
    result: dict[str, ProjectBudget] = {}
    for slug, entry in data.items():
        if not isinstance(entry, dict):
            continue
        daily = entry.get("daily_usd")
        monthly = entry.get("monthly_usd")
        result[slug] = ProjectBudget(
            daily_usd=float(daily) if daily is not None else None,
            monthly_usd=float(monthly) if monthly is not None else None,
        )
    return result


def check_budget(
    project_slug: str,
    project_dir: Path,
    now: datetime | None = None,
) -> str | None:
    """Return a warning string if any limit is exceeded, else None."""
    budgets = load_budgets()
    budget = budgets.get(project_slug)
    if budget is None:
        return None

    if now is None:
        now = datetime.now()

    if not (project_dir / AI_LOG_FILENAME).exists():
        return None

    sessions = parse_sessions(project_dir)
    today_spend, month_spend = _sum_api_spend(sessions, now)

    warnings: list[str] = []
    if budget.daily_usd is not None and today_spend > budget.daily_usd:
        warnings.append(f"today ${today_spend:.2f} / ${budget.daily_usd:.2f}  ⚠ over daily limit")
    if budget.monthly_usd is not None and month_spend > budget.monthly_usd:
        warnings.append(
            f"monthly ${month_spend:.2f} / ${budget.monthly_usd:.2f}  ⚠ over monthly limit"
        )

    if not warnings:
        return None

    first_line = f"⚠  Halyard budget: {project_slug}  {' '.join(warnings)}"
    return first_line + "\n   Session will proceed. Run `halyard budget` to review."


def budget_status(now: datetime | None = None) -> list[BudgetStatus]:
    """Return spend-vs-limit for all configured projects.

    Uses hub log (all sessions tagged with project=) if available, else CWD project dir.
    """
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub

    if now is None:
        now = datetime.now()

    budgets = load_budgets()
    statuses: list[BudgetStatus] = []

    # Prefer hub because it captures sessions across all projects.
    # Fall back to the CWD project dir for single-project setups.
    hub = find_hub()
    cwd_dir = find_project_dir()

    for slug, budget in budgets.items():
        today_spend, month_spend = 0.0, 0.0

        for candidate in filter(None, [hub, cwd_dir]):
            if not (candidate / AI_LOG_FILENAME).exists():
                continue
            all_sessions = parse_sessions(candidate)
            # Filter by project slug to ensure correctness even in project-local logs.
            sessions = [s for s in all_sessions if s.project == slug]
            today_spend, month_spend = _sum_api_spend(sessions, now)
            break  # first valid source wins

        statuses.append(
            BudgetStatus(
                slug=slug,
                today_spend=today_spend,
                today_limit=budget.daily_usd,
                month_spend=month_spend,
                month_limit=budget.monthly_usd,
            )
        )

    return statuses


def set_budget(
    slug: str,
    daily_usd: float | None = None,
    monthly_usd: float | None = None,
) -> ProjectBudget:
    """Add or update a budget entry. Returns the final ProjectBudget."""
    _BUDGETS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load existing data as raw dict to preserve other entries
    if _BUDGETS_FILE.exists():
        try:
            data: dict[str, object] = dict(tomllib.loads(_BUDGETS_FILE.read_text()))
        except tomllib.TOMLDecodeError:
            data = {}
    else:
        data = {}

    existing = data.get(slug)
    entry: dict[str, float] = {}
    if isinstance(existing, dict):
        if "daily_usd" in existing:
            entry["daily_usd"] = float(existing["daily_usd"])
        if "monthly_usd" in existing:
            entry["monthly_usd"] = float(existing["monthly_usd"])

    if daily_usd is not None:
        entry["daily_usd"] = daily_usd
    if monthly_usd is not None:
        entry["monthly_usd"] = monthly_usd

    data[slug] = entry
    _BUDGETS_FILE.write_text(tomli_w.dumps(data))

    return ProjectBudget(
        daily_usd=entry.get("daily_usd"),
        monthly_usd=entry.get("monthly_usd"),
    )


def _sum_api_spend(sessions: list[AiSession], now: datetime) -> tuple[float, float]:
    """Return (today_spend, month_spend) for billing=api sessions."""
    today_spend = 0.0
    month_spend = 0.0
    for s in sessions:
        if s.billing != "api":
            continue
        if s.cost_usd <= 0:
            continue
        if not s.tokens_available:
            continue
        if s.start.date() == now.date():
            today_spend += s.cost_usd
        if s.start.year == now.year and s.start.month == now.month:
            month_spend += s.cost_usd
    return round(today_spend, 4), round(month_spend, 4)
