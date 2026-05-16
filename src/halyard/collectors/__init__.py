"""Shared collector helpers."""

from __future__ import annotations

from halyard.ai_log import AiSession

_UNKNOWN_MODELS = {"", "default"}

# A single AI turn captured by a stop hook cannot plausibly span this
# long. Synthetic/broken payloads (e.g. a frozen session-start that
# never advances) produce multi-day "sessions"; reject them.
_MAX_SESSION_SECONDS = 12 * 3600


def session_is_implausible(session: AiSession) -> bool:
    """True if the session's duration is impossible for one turn.

    Catches synthetic hook payloads the evidence predicate can't (they
    carry nonzero tokens): a frozen/ancient start producing a multi-day
    span (>12h), or end-before-start (negative duration) — both are
    physically impossible for a single real turn.
    """
    duration = (session.end - session.start).total_seconds()
    return duration < 0 or duration > _MAX_SESSION_SECONDS


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
