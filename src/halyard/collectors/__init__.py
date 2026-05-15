"""Shared collector helpers."""

from __future__ import annotations

from halyard.ai_log import AiSession

_UNKNOWN_MODELS = {"", "default"}


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
