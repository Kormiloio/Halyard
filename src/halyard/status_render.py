"""Compact text rendering for the v2.74 ambient StatusSnapshot.

Pure function (snapshot -> Rich-markup string) so it is unit-testable
without a loop or a terminal. Every user-derived string (client slug,
hook name) is markup-escaped (v2.38 injection invariant). `~` marks an
estimate; projections are never shown as measured.
"""

from __future__ import annotations

from rich.markup import escape

from halyard.status_snapshot import StatusSnapshot


def _bar(pct: int, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "▓" * filled + "░" * (width - filled)


def render_status_text(snap: StatusSnapshot) -> str:
    cap = snap.capture
    lines: list[str] = []

    health = "[green]capture ok[/]" if cap.healthy else "[red]capture DEGRADED[/]"
    hooks = " ".join(f"{escape(k)}:{escape(v)}" for k, v in sorted(cap.hooks.items()))
    recency = (
        "no sessions yet"
        if cap.minutes_since_last_capture is None
        else f"last {cap.minutes_since_last_capture}m ago"
    )
    lines.append(f"⚓ {health}  ·  {hooks or 'no hooks'}  ·  {recency}")

    sp = snap.spend
    lines.append(f"$ today ${sp.today_usd:.2f}  ·  month ${sp.month_usd:.2f}")
    for c in sp.by_client:
        lines.append(f"   {escape(c.slug):24} ${c.month_usd:.2f}")

    if snap.budgets:
        lines.append("Budgets")
        for b in snap.budgets:
            limit = "—" if b.month_limit_usd is None else f"${b.month_limit_usd:.0f}"
            dtl = "" if b.days_until_limit is None else f"  ~{b.days_until_limit}d to limit"
            lines.append(
                f"   {escape(b.slug):20} {_bar(b.pct)} {b.pct:>3}%  "
                f"~${b.projected_month_end_usd:.0f} proj / {limit}{dtl}"
            )

    a = snap.adrift
    if a.count:
        lines.append(f"[yellow]⚠ adrift {a.count} session(s) · ${a.usd:.2f}[/] — run halyard adopt")
    else:
        lines.append("[green]✓ no adrift sessions[/]")

    return "\n".join(lines)
