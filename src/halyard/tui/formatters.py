"""Formatting helpers for the Textual TUI."""

from __future__ import annotations

from datetime import timedelta


def tool_icon(tool: str) -> str:
    """Return a compact ASCII marker for an AI tool slug."""
    normalized = tool.lower()
    if "claude" in normalized:
        return "C"
    if "cursor" in normalized:
        return "X"
    if "gemini" in normalized:
        return "G"
    if "codex" in normalized:
        return "O"
    return "A"


def cost_str(usd: float) -> str:
    """Render USD cost with enough precision for small model calls."""
    return f"${usd:.4f}"


def duration_str(delta: timedelta) -> str:
    """Render a compact duration."""
    seconds = max(0, int(delta.total_seconds()))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{remaining_seconds}s"


def truncate(value: str, width: int) -> str:
    """Trim text to a fixed width with an ellipsis-like suffix."""
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "."


def budget_css_class(spend: float, limit: float | None) -> str:
    """Map spend ratio to the TUI budget CSS class."""
    if limit is None or limit <= 0:
        return "budget-ok"
    ratio = spend / limit
    if ratio > 1:
        return "budget-over"
    if ratio >= 0.8:
        return "budget-high"
    if ratio >= 0.5:
        return "budget-warn"
    return "budget-ok"
