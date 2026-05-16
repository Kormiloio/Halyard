"""Shared collector helpers."""

from __future__ import annotations

from datetime import datetime

from halyard.ai_log import AiSession

_UNKNOWN_MODELS = {"", "default"}

# A single AI turn captured by a stop hook cannot plausibly span this
# long. Synthetic/broken payloads (e.g. a frozen session-start that
# never advances) produce multi-day "sessions"; reject them.
_MAX_SESSION_SECONDS = 12 * 3600

# Grace for benign clock skew / timezone slop. A session whose start is
# beyond this far in the future has not happened yet — impossible.
_FUTURE_START_GRACE_SECONDS = 5 * 60


def session_starts_in_future(session: AiSession, *, now: datetime | None = None) -> bool:
    """True if the session's start has not happened yet.

    A genuine turn cannot start in the future. An external writer can
    append rows with any timestamp (observed: rows dated days ahead);
    these must never surface. Narrow on purpose — only the future
    check, so applying it at read time can't retroactively hide
    long-but-real historical sessions.
    """
    clock = now or datetime.now()
    start = session.start
    # Defensive: a directly-constructed session may carry tzinfo while
    # `clock` is naive. parse_sessions already normalises, but coerce
    # here too so no caller can trip "can't subtract offset-naive and
    # offset-aware datetimes".
    if start.tzinfo is not None:
        start = start.astimezone().replace(tzinfo=None)
    if clock.tzinfo is not None:
        clock = clock.astimezone().replace(tzinfo=None)
    return (start - clock).total_seconds() > _FUTURE_START_GRACE_SECONDS


def session_is_implausible(session: AiSession, *, now: datetime | None = None) -> bool:
    """True if the session is physically impossible for one real turn.

    Catches synthetic/garbage payloads the evidence predicate can't
    (they carry nonzero tokens):
    - a multi-day span (>12h),
    - end-before-start (negative duration),
    - a start in the future (the turn has not happened yet).
    All three are impossible for a single genuine turn.
    """
    duration = (session.end - session.start).total_seconds()
    if duration < 0 or duration > _MAX_SESSION_SECONDS:
        return True
    return session_starts_in_future(session, now=now)


# Exact canned payloads the thedotmack claude-mem worker-service.cjs
# daemon appends directly to ai-sessions.log, bypassing every collector
# write guard. Token pair + legacy model + $0 + no project is a
# machine fingerprint genuine current work cannot reproduce.
_SYNTHETIC_FINGERPRINTS: set[tuple[int, int, str]] = {
    (2000, 400, "claude-3.5-sonnet"),
    (100, 50, "gemini-2.0-pro"),
}


def session_is_synthetic_telemetry(session: AiSession) -> bool:
    """True for the claude-mem daemon's canned, unattributed $0 rows.

    Deliberately narrow: requires the exact token pair, the exact
    legacy model string, zero cost, and no project simultaneously —
    a combination real current sessions never produce, so there are no
    false positives. The durable defence is applying this at read time
    (parse_sessions), since the daemon writes the log directly and
    never touches a Halyard collector.
    """
    if session.cost_usd != 0:
        return False
    if session.project:
        return False
    return (
        session.input_tokens,
        session.output_tokens,
        session.model,
    ) in _SYNTHETIC_FINGERPRINTS


def _model_is_real(model: str) -> bool:
    return bool(model) and model not in _UNKNOWN_MODELS and not model.endswith("-unknown")


def session_has_evidence(session: AiSession, *, history: bool = False) -> bool:
    """True if a stop-hook fire shows any sign that a real turn happened.

    A collector hook can fire with nothing behind it (an aborted turn, a
    SessionStart-only state, or a spurious/shared hook invocation). Such
    fires must not become ledger rows. A turn counts as real if it
    produced ANY signal: tokens, a parsed history summary, tool calls,
    interactions, code delta, a commit, or an identified model.
    """
    if history:
        return True
    if session.input_tokens > 0 or session.output_tokens > 0:
        return True
    if session.cache_read or session.cache_write:
        return True
    if session.tool_calls or session.tool_errors:
        return True
    if any(
        (
            session.interaction_count,
            session.user_message_count,
            session.assistant_message_count,
            session.prompt_count,
            session.accepted_suggestion_count,
            session.rejected_suggestion_count,
        )
    ):
        return True
    if session.code_added or session.code_removed or session.files_touched_count:
        return True
    if session.commit_count:
        return True
    return _model_is_real(session.model)
