"""Calendar block export — RFC 5545 iCalendar from AI session log (v2.8)."""

from __future__ import annotations

import hashlib

from halyard.ai_log import AiSession

_PRODID = "-//Halyard//AI Session Schedule//EN"
_CALNAME = "AI Work Sessions"


def _session_uid(s: AiSession) -> str:
    raw = f"{s.start.isoformat()}{s.tool}{s.model}{s.cost_usd:.4f}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return f"{digest}@halyard"


def _fmt_dt(dt: object) -> str:
    from datetime import datetime

    assert isinstance(dt, datetime)
    return dt.strftime("%Y%m%dT%H%M%S")


def _fold(line: str) -> str:
    """Fold a content line to max 75 octets per RFC 5545 §3.1."""
    encoded = line.encode()
    if len(encoded) <= 75:
        return line
    result: list[str] = []
    remaining = line
    while len(remaining.encode()) > 75:
        # Slice by characters until the encoded prefix fits in 75 bytes
        cut = 75
        while len(remaining[:cut].encode()) > 75:
            cut -= 1
        result.append(remaining[:cut])
        remaining = remaining[cut:]
    result.append(remaining)
    return "\r\n ".join(result)


def _escape_text(value: str) -> str:
    """Escape an RFC 5545 TEXT value before folding."""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def session_to_vevent(s: AiSession) -> str:
    project_label = s.project or "unattributed"
    summary = f"{s.tool} — {project_label}"

    desc_parts = [
        f"Model: {s.model}",
        f"Cost: ${s.cost_usd:.4f}",
        f"Tokens: {s.input_tokens:,} in / {s.output_tokens:,} out",
    ]
    if s.tool_calls is not None:
        errors = s.tool_errors or 0
        desc_parts.append(f"Tool calls: {s.tool_calls} ({errors} errors)")
    if s.code_added is not None:
        removed = s.code_removed or 0
        desc_parts.append(f"Code delta: +{s.code_added}/-{removed}")
    if s.tags:
        desc_parts.append(f"Tags: {', '.join(s.tags)}")

    description = "\n".join(desc_parts)

    lines = [
        "BEGIN:VEVENT",
        _fold(f"UID:{_session_uid(s)}"),
        f"DTSTART:{_fmt_dt(s.start)}",
        f"DTEND:{_fmt_dt(s.end)}",
        _fold(f"SUMMARY:{_escape_text(summary)}"),
        _fold(f"DESCRIPTION:{_escape_text(description)}"),
        "END:VEVENT",
    ]
    return "\r\n".join(lines)


def build_calendar(sessions: list[AiSession]) -> str:
    parts = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        f"X-WR-CALNAME:{_CALNAME}",
    ]
    for s in sessions:
        parts.append(session_to_vevent(s))
    parts.append("END:VCALENDAR")
    return "\r\n".join(parts) + "\r\n"
