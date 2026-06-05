"""Reconstruct a corrupted hledger timeclock into clean ``i``/``o`` windows.

The auto human timer can leave a stream of bare clock-ins with no matching
clock-out (one orphaned ``i`` per Hub restart). Under the parser's
last-``i``-before-``o`` semantics that silently drops billable time. This module
rebuilds the file under the same 30-minute presence-window rule the live timer
applies:

- consecutive ``;auto`` clock-ins within ``INACTIVITY_MINUTES`` collapse into a
  single window (the corruption-healing case);
- a gap of ``INACTIVITY_MINUTES`` or more splits into separate windows (idle is
  not billed);
- every dangling open is closed.

Manual entries (no ``;auto`` tag) are preserved verbatim — only their ``o`` is
re-emitted at the same timestamp. The original ``i`` line is always kept as
written, so project tokens (``:`` vs ``/``), the ``;auto`` tag, and any manual
comment survive untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from halyard.auto_timer import INACTIVITY_MINUTES

_TS_FMT = "%Y-%m-%d %H:%M:%S"


# v5.18/B18: hledger timeclock natively accepts an HH:MM timestamp with no
# seconds. The shared reports parser is strict "%Y-%m-%d %H:%M:%S" and returns
# None for the bare-minute form, which previously caused a full rewrite to
# silently drop hand-edited valid entries like ``i 2026-06-01 09:00 client:proj``.
# Parse the seconds-optional form locally so such lines are recognised, not lost.
def _parse_ts(day: str, time: str) -> datetime | None:
    for fmt in (_TS_FMT, "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(f"{day} {time}", fmt)
        except ValueError:
            continue
    return None


def _is_record_marker(marker: str) -> bool:
    """A token that introduces a timeclock record (clock-in / clock-out)."""
    return marker in ("i", "o")


@dataclass
class _Open:
    orig_i_line: str
    kind: str  # "auto" | "manual"
    project: str
    start_ts: datetime
    last_ts: datetime
    merged: bool = False  # absorbed a later clock-in (a dropped-open run)


def _needs_repair(lines: list[str]) -> bool:
    """True if the file has structural corruption a rewrite would fix.

    Flags dropped opens (``i`` while already open), orphan closes (``o`` with no
    open), and backward closes (``o`` before its open → negative window). A
    forward clock-out far from its open is **not** flagged: in a clean file a
    legitimate multi-hour window (built from sub-30-min pings) looks exactly like
    that once the pings are merged away, and re-flagging it would crush it.
    """
    is_open = False
    open_ts: datetime | None = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith(";"):
            continue
        parts = stripped.split()
        if len(parts) < 3:
            continue
        ts = _parse_ts(parts[1], parts[2])
        if ts is None:
            continue
        if parts[0] == "i" and len(parts) >= 4:
            if is_open:
                return True  # dropped open
            is_open = True
            open_ts = ts
        elif parts[0] == "o":
            if not is_open:
                return True  # orphan close
            if open_ts is not None and ts < open_ts:
                return True  # backward close → negative window
            is_open = False
    return False


def reconstruct_timeclock(
    lines: list[str], *, inactivity_minutes: int = INACTIVITY_MINUTES
) -> list[str]:
    """Return repaired timeclock lines (no trailing newlines on each item).

    Idempotency: capping a stale clock-out requires the intermediate activity
    pings, which a first pass merges away. So a structurally-sound file is
    returned unchanged — re-running is a safe no-op and never crushes a
    legitimate multi-hour window down to its endpoints. A lone trailing open
    (a possibly-live window) is likewise left as-is.
    """
    repaired, _dropped = reconstruct_timeclock_with_drops(
        lines, inactivity_minutes=inactivity_minutes
    )
    return repaired


def reconstruct_timeclock_with_drops(
    lines: list[str], *, inactivity_minutes: int = INACTIVITY_MINUTES
) -> tuple[list[str], int]:
    """Like :func:`reconstruct_timeclock`, but also report how many lines were
    dropped as unrecoverably malformed.

    v5.18/B18: the old rewrite silently dropped (bare ``continue``, no
    ``out.append``) every line with <3 tokens, every timestamp failing the
    strict ``%Y-%m-%d %H:%M:%S`` parse, and every ``i`` with no project — which
    erased hand-edited *valid* entries (hledger accepts seconds-less ``HH:MM``,
    and the module docstring promises manual entries survive verbatim). We now
    only drop a line that is a recognisable-but-unparseable record marker, echo
    every other non-conforming line verbatim, and return the drop count so the
    caller can surface it instead of discarding billable time in silence.
    """
    if not _needs_repair(lines):
        return [raw.rstrip("\n") for raw in lines], 0

    window = timedelta(minutes=inactivity_minutes)
    out: list[str] = []
    open_win: _Open | None = None
    seen_record = False
    dropped = 0

    def flush(o: _Open) -> None:
        out.append(o.orig_i_line)
        out.append(f"o {o.last_ts.strftime(_TS_FMT)}")

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        # Header comments / blanks before any record pass through verbatim.
        if not stripped or stripped.startswith(";"):
            if not seen_record:
                out.append(line)
            continue

        parts = stripped.split()
        marker = parts[0]
        # v5.18/B18: a line is only dropped if it is a known-bad record — an
        # ``i``/``o`` marker we cannot parse a timestamp from (too few tokens or
        # an unrecognised time form). Anything else (a non-record annotation, a
        # plausible-but-unexpected line) is preserved verbatim rather than erased.
        ts = _parse_ts(parts[1], parts[2]) if len(parts) >= 3 else None
        if ts is None:
            if _is_record_marker(marker):
                dropped += 1  # genuinely corrupt clock record — drop, but counted
            else:
                out.append(line)  # not a record; keep it verbatim
            continue
        if marker == "i" and len(parts) < 4:
            dropped += 1  # clock-in with no project — corrupt, counted
            continue

        if marker == "i" and len(parts) >= 4:
            seen_record = True
            kind = "auto" if ";auto" in stripped else "manual"
            project = parts[3]
            if (
                open_win is not None
                and open_win.kind == "auto"
                and kind == "auto"
                and project == open_win.project
                and open_win.last_ts <= ts <= open_win.last_ts + window
            ):
                open_win.last_ts = ts  # merge into the running window
                open_win.merged = True
            else:
                if open_win is not None:
                    flush(open_win)
                open_win = _Open(line, kind, project, ts, ts)
        elif marker == "o":
            seen_record = True
            if open_win is not None:
                if open_win.merged:
                    # A dropped-open run: the auto-timer was pinging, so a close
                    # beyond the 30-min window is stale — cap at the last real
                    # activity, never billing the idle gap.
                    if open_win.last_ts < ts <= open_win.last_ts + window:
                        open_win.last_ts = ts
                elif ts > open_win.last_ts:
                    # A clean single-clock-in window: the clock-out is
                    # authoritative (a legitimate multi-hour session), so trust
                    # it verbatim. Only a backward close is dropped.
                    open_win.last_ts = ts
                flush(open_win)
                open_win = None
            # orphan close (no open) is dropped

    if open_win is not None:
        if open_win.merged:
            # A dropped-open run that never got its close: end it at the last
            # activity ping.
            flush(open_win)
        else:
            # A lone trailing clock-in may be a live in-progress window — keep
            # it open, never fabricate a close.
            out.append(open_win.orig_i_line)

    return out, dropped


def counted_minutes(lines: list[str]) -> float:
    """Sum billable minutes from clean i/o pairs (sequential pairing)."""
    total = 0.0
    open_ts: datetime | None = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith(";"):
            continue
        parts = stripped.split()
        if len(parts) < 3:
            continue
        ts = _parse_ts(parts[1], parts[2])
        if ts is None:
            continue
        if parts[0] == "i" and len(parts) >= 4:
            open_ts = ts
        elif parts[0] == "o" and open_ts is not None:
            # Clamp: a backward (corrupt) pair contributes 0, never negative.
            total += max(0.0, (ts - open_ts).total_seconds() / 60)
            open_ts = None
    return total
