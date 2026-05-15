"""Usage analytics widget."""

from __future__ import annotations

from datetime import datetime

from rich.markup import escape
from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.tui.formatters import cost_str, truncate
from halyard.usage import DailyUsageBucket, build_usage_analytics, compact_number


class UsagePane(Static):
    """Render high-signal usage analytics for the active TUI filter."""

    last_rendered_text = ""

    def render_sessions(self, sessions: list[AiSession], now: datetime | None = None) -> None:
        usage = build_usage_analytics(sessions, range_key="all", now=now)
        summary = usage.summary

        if not sessions:
            self.last_rendered_text = "〜 Voyage Stats\n\nNo sessions in view."
            self.update(self.last_rendered_text)
            return

        peak = "--" if summary.peak_hour is None else f"{_hour_label(summary.peak_hour)}"
        favorite = summary.favorite_model or "--"
        lines = [
            "〜 Voyage Stats",
            "",
            f"Sessions {summary.sessions:>5}   Tokens {compact_number(summary.total_tokens):>7}",
            (
                f"Active   {summary.active_days:>5}d  "
                f"Streak {summary.current_streak_days}d / {summary.longest_streak_days}d"
            ),
            f"Peak     {peak:>5}   Cost {cost_str(summary.total_cost_usd):>9}",
            f"Favorite {truncate(favorite, 24)}",
        ]
        if summary.unattributed_sessions:
            from halyard.ai_log import unattributed_log_path
            from halyard.doctor import _group_unattributed_by_remote

            groups = _group_unattributed_by_remote(unattributed_log_path())
            lines.append(
                f"⚠ Unattributed: {summary.unattributed_sessions} session(s) — run halyard adopt"
            )
            for remote, count in sorted(groups.items(), key=lambda x: -x[1]):
                lines.append(f"  {truncate(remote, 36)} ({count})")
        if summary.token_data_missing_sessions:
            lines.append(f"Missing token data: {summary.token_data_missing_sessions}")
        lines.extend(["", "Swells  (30d)"])
        lines.append(_activity_line(usage.daily[-30:]))
        lines.extend(["", "Top Models"])
        for bucket in usage.by_model[:4]:
            pct = int(bucket.token_share * 100)
            bar = "#" * max(1, min(16, pct // 6)) if bucket.tokens else "-"
            model = escape(truncate(bucket.model, 18))
            tokens = compact_number(bucket.tokens)
            lines.append(f"{model:18} {tokens:>7} {pct:>3}% {bar}")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _activity_line(days: list[DailyUsageBucket]) -> str:
    chars = []
    for bucket in days:
        tokens = bucket.tokens
        sessions = bucket.sessions
        missing = bucket.has_missing_token_data
        if missing and tokens == 0:
            chars.append("?")
        elif tokens >= 100_000 or sessions >= 10:
            chars.append("▓")  # heavy seas
        elif tokens >= 20_000 or sessions >= 4:
            chars.append("▒")  # moderate
        elif tokens > 0 or sessions > 0:
            chars.append("░")  # light chop
        else:
            chars.append("·")  # doldrums
    return "".join(chars)


def _hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12}{suffix}"
