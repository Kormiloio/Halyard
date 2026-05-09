"""Terminal visuals — trail-themed CLI output for halyard stop and halyard report."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime

from rich.panel import Panel
from rich.text import Text

# ---------------------------------------------------------------------------
# Trail bar — horizontal progress fill used in the stop card
# ---------------------------------------------------------------------------

_BAR_FULL = "▓"
_BAR_EMPTY = "░"
_BAR_WIDTH = 22
_BAR_TARGET_MINUTES = 90.0  # "full bar" at 1h 30m — typical deep-work session


def _trail_bar(elapsed_minutes: float) -> Text:
    fraction = min(1.0, elapsed_minutes / _BAR_TARGET_MINUTES)
    filled = round(_BAR_WIDTH * fraction)
    empty = _BAR_WIDTH - filled
    t = Text()
    t.append(_BAR_FULL * filled, style="bold green")
    t.append(_BAR_EMPTY * empty, style="dim")
    return t


# ---------------------------------------------------------------------------
# Stop card — shown after `halyard stop`
# ---------------------------------------------------------------------------


def stop_card(slug: str, elapsed_minutes: float, elapsed_str: str, backfill_count: int) -> Panel:
    """Rich Panel celebrating a completed trail segment."""
    body = Text()
    body.append(f"  {slug}\n", style="bold")
    body.append("  ")
    body.append_text(_trail_bar(elapsed_minutes))
    body.append(f"  {elapsed_str}\n")
    body.append("\n")
    if backfill_count:
        noun = "session" if backfill_count == 1 else "sessions"
        body.append(f"  {backfill_count} AI {noun} attributed\n", style="green")
    else:
        body.append("  AI sessions captured automatically\n", style="dim")
    return Panel(
        body,
        title="[bold green]trail closed[/]",
        border_style="green",
        padding=(0, 1),
        expand=False,
    )


# ---------------------------------------------------------------------------
# Trail heatmap — monthly calendar shown in `halyard report`
# ---------------------------------------------------------------------------

# Characters ordered by attribution quality, lowest → highest.
_HEAT: list[tuple[str, str]] = [
    ("·", "dim"),  # no sessions
    ("░", "yellow"),  # sessions exist, none attributed
    ("▒", "yellow"),  # sessions exist, some attributed
    ("█", "green"),  # all sessions attributed
]


def _day_char(total: int, attributed: int) -> tuple[str, str]:
    if total == 0:
        return _HEAT[0]
    if attributed == 0:
        return _HEAT[1]
    if attributed < total:
        return _HEAT[2]
    return _HEAT[3]


def trail_heatmap(sessions: list, period: datetime) -> Panel:
    """Rich Panel showing a GitHub-style attribution heatmap for the month."""
    from halyard.ai_log import AiSession

    year, month = period.year, period.month

    # Aggregate per-day stats
    day_total: dict[date, int] = defaultdict(int)
    day_attr: dict[date, int] = defaultdict(int)

    for s in sessions:
        if not isinstance(s, AiSession):
            continue
        d = s.start.date()
        if d.year == year and d.month == month:
            day_total[d] += 1
            if s.project:
                day_attr[d] += 1

    # Build the calendar grid
    today = datetime.now().date()
    weeks = calendar.monthcalendar(year, month)
    month_label = period.strftime("%B %Y")

    body = Text()
    body.append("  Mo  Tu  We  Th  Fr  Sa  Su\n", style="bold dim")

    for week in weeks:
        body.append("  ")
        for day_num in week:
            if day_num == 0:
                body.append("·   ", style="dim")
            else:
                d = date(year, month, day_num)
                char, style = _day_char(day_total[d], day_attr[d])
                # Future dates always dim
                if d > today:
                    char, style = "·", "dim"
                body.append(char, style=style)
                body.append("   ")
        body.append("\n")

    body.append("\n")
    body.append("  · none  ", style="dim")
    body.append("░ unattributed  ", style="yellow")
    body.append("▒ partial  ", style="yellow")
    body.append("█ attributed", style="green")
    body.append("\n")

    return Panel(
        body,
        title=f"[bold]Trail · {month_label}[/]",
        border_style="dim",
        padding=(0, 1),
        expand=False,
    )
