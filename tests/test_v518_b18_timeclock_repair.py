"""v5.18/B18 — timeclock repair must not silently delete valid billable lines.

Regression guard for the HIGH-severity pre-release blocker: once ``_needs_repair``
triggered on one anomaly, the full rewrite dropped (bare ``continue``, no
``out.append``) any line with <3 tokens, any timestamp failing the strict
``%Y-%m-%d %H:%M:%S`` parse, and any ``i`` with no project. But hledger timeclock
natively accepts the seconds-less ``HH:MM`` form, and the module docstring
promises manual entries are "preserved verbatim". So a hand-edited valid entry
like ``i 2026-06-01 09:00 client:proj`` was erased on ``repair --apply``.
"""

from __future__ import annotations

from halyard.timeclock_repair import (
    counted_minutes,
    reconstruct_timeclock,
    reconstruct_timeclock_with_drops,
)


def _pairs(lines: list[str]) -> list[tuple[str, str]]:
    out, open_ts = [], None
    for line in lines:
        p = line.split()
        if not p:
            continue
        if p[0] == "i":
            open_ts = f"{p[1]} {p[2]}"
        elif p[0] == "o" and open_ts is not None:
            out.append((open_ts, f"{p[1]} {p[2]}"))
            open_ts = None
    return out


# ---------------------------------------------------------------------------
# (a) the previously-erased valid input is now handled correctly
# ---------------------------------------------------------------------------


def test_secondsless_manual_entry_survives_full_rewrite():
    # A corruption elsewhere (the trailing dropped-open run) forces a full
    # rewrite. The hand-edited seconds-less manual entry must NOT be deleted.
    lines = [
        "i 2026-06-01 09:00 client:proj",  # valid HH:MM manual entry, no seconds
        "o 2026-06-01 17:00",
        "i 2026-06-01 18:00:00 kormilo/halyard  ;auto",  # dropped open below
        "i 2026-06-01 18:10:00 kormilo/halyard  ;auto",
        "o 2026-06-01 18:30:00",
    ]
    out = reconstruct_timeclock(lines)
    # The seconds-less window is preserved (8h), not silently dropped to 0.
    # (the re-emitted ``o`` is normalised to the seconds form).
    assert ("2026-06-01 09:00", "2026-06-01 17:00:00") in _pairs(out)
    # Its original verbatim i line is intact.
    assert "i 2026-06-01 09:00 client:proj" in out
    assert counted_minutes(out) == 8 * 60 + 30


def test_secondsless_open_is_a_clean_dropped_open_anomaly():
    # Two seconds-less auto clock-ins with no close between them are a genuine
    # dropped-open run — they must merge, not be discarded as "unparseable".
    lines = [
        "i 2026-06-01 09:00 kormilo/halyard  ;auto",
        "i 2026-06-01 09:10 kormilo/halyard  ;auto",
        "o 2026-06-01 09:30",
    ]
    out = reconstruct_timeclock(lines)
    assert _pairs(out) == [("2026-06-01 09:00", "2026-06-01 09:30:00")]


def test_unrecognised_nonrecord_line_preserved_verbatim():
    # A plausible-but-unexpected non-record line (not a comment, not i/o) must
    # be echoed verbatim, never silently erased during a rewrite.
    lines = [
        "account expenses:travel",  # a stray hledger-style directive
        "i 2026-06-01 09:00:00 kormilo/halyard  ;auto",
        "i 2026-06-01 09:10:00 kormilo/halyard  ;auto",  # dropped open → triggers rewrite
        "o 2026-06-01 09:30:00",
    ]
    out = reconstruct_timeclock(lines)
    assert "account expenses:travel" in out


def test_corrupt_record_is_dropped_but_counted():
    # A truly malformed clock record (bad date) is still dropped — but the count
    # is surfaced, not silently swallowed.
    lines = [
        "i 2026-13-99 09:00:00 kormilo/halyard  ;auto",  # impossible date → known-bad
        "i 2026-06-01 09:00:00 kormilo/halyard  ;auto",
        "i 2026-06-01 09:10:00 kormilo/halyard  ;auto",  # dropped open → triggers rewrite
        "o 2026-06-01 09:30:00",
    ]
    out, dropped = reconstruct_timeclock_with_drops(lines)
    assert dropped == 1
    assert _pairs(out) == [("2026-06-01 09:00:00", "2026-06-01 09:30:00")]


def test_clockin_without_project_is_dropped_but_counted():
    lines = [
        "i 2026-06-01 09:00:00",  # no project token → corrupt clock-in
        "i 2026-06-01 09:05:00 kormilo/halyard  ;auto",
        "i 2026-06-01 09:10:00 kormilo/halyard  ;auto",  # dropped open → triggers rewrite
        "o 2026-06-01 09:30:00",
    ]
    out, dropped = reconstruct_timeclock_with_drops(lines)
    assert dropped == 1
    assert ("2026-06-01 09:05:00", "2026-06-01 09:30:00") in _pairs(out)


# ---------------------------------------------------------------------------
# (b) benign / normal input still works — guard against over-restriction
# ---------------------------------------------------------------------------


def test_clean_seconds_form_unchanged_and_no_drops():
    lines = [
        "; header",
        "i 2026-06-01 10:00:00 kormilo/halyard  ;auto",
        "o 2026-06-01 10:30:00",
    ]
    out, dropped = reconstruct_timeclock_with_drops(lines)
    # Structurally sound → returned verbatim, nothing dropped.
    assert out == [
        "; header",
        "i 2026-06-01 10:00:00 kormilo/halyard  ;auto",
        "o 2026-06-01 10:30:00",
    ]
    assert dropped == 0


def test_normal_repair_reports_zero_drops():
    # A typical dropped-open corruption: repaired cleanly with no line losses.
    lines = [
        "i 2026-06-01 10:00:00 kormilo/halyard  ;auto",
        "i 2026-06-01 10:10:00 kormilo/halyard  ;auto",
        "i 2026-06-01 10:25:00 kormilo/halyard  ;auto",
        "o 2026-06-01 10:30:00",
    ]
    out, dropped = reconstruct_timeclock_with_drops(lines)
    assert dropped == 0
    assert _pairs(out) == [("2026-06-01 10:00:00", "2026-06-01 10:30:00")]


def test_repair_is_idempotent_with_secondsless_entries():
    lines = [
        "i 2026-06-01 09:00 client:proj",
        "o 2026-06-01 17:00",
        "i 2026-06-01 18:00:00 kormilo/halyard  ;auto",
        "i 2026-06-01 18:10:00 kormilo/halyard  ;auto",
        "o 2026-06-01 18:30:00",
    ]
    once = reconstruct_timeclock(lines)
    twice = reconstruct_timeclock(once)
    assert twice == once
