"""Gemini CLI hook collector.

Three entry points, wired up by `halyard install-gemini-hook`:

  SessionStart  →  record_session_start()   (halyard gc-session)
  AfterModel    →  record_model_usage()      (halyard gc-model)
  AfterAgent    →  handle_agent_stop()       (halyard gc-hook)

SessionStart saves the turn start time + cwd.  AfterModel accumulates per-call
token counts.  AfterAgent finalises the record and resets the token accumulators
for the next turn (multiple turns can occur within one Gemini CLI session).

AfterModel payload (llm_response.usageMetadata):
  promptTokenCount      — cumulative input tokens for this API call
  candidatesTokenCount  — output tokens for this API call
  totalTokenCount       — promptTokenCount + candidatesTokenCount

We keep:
  prompt_tokens  = last promptTokenCount  (Gemini cumulates history in prompt)
  output_tokens  = sum of candidatesTokenCount across all model calls in the turn
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    find_project_dir,
    maybe_show_dashboard_hint,
    read_active_project,
    write_unattributed_session,
)
from halyard.collectors import (
    session_has_evidence,
    session_is_implausible,
    session_is_synthetic_telemetry,
)
from halyard.collectors.gemini_history import (
    GeminiModelStats,
    find_session_file,
    parse_session_file,
)
from halyard.git_context import (
    commits_in_window,
    current_branch,
    current_remote,
    infer_project_with_source,
)
from halyard.hub import find_hub
from halyard.model_breakdown import ModelSeg
from halyard.model_breakdown import cost_of as _breakdown_cost
from halyard.model_breakdown import encode as _encode_breakdown
from halyard.model_breakdown import primary_model as _primary_model
from halyard.pricing import calculate_cost

_GC_SESSION_FILE = Path.home() / ".halyard" / "gc-session"


def record_session_start() -> int:
    """Called by SessionStart hook. Saves start time, session_id, and cwd."""
    payload = _read_payload()
    cwd_str = payload.get("cwd", "")

    # Budget check fires before writing the new session state
    active = read_active_project()
    if active:
        cwd = Path(cwd_str) if cwd_str else Path.cwd()
        project_dir = find_project_dir(start=cwd) or find_hub()
        if project_dir:
            from halyard.budget import check_budget

            warning = check_budget(active, project_dir)
            if warning:
                print(warning)  # budget warning: hooks write to stdout for tool pickup

    now_str = payload.get("timestamp") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    state = {
        "turn_start": now_str,
        "session_id": payload.get("session_id", ""),
        "cwd": cwd_str,
        "model": "",
        "prompt_tokens": 0,
        "output_tokens": 0,
        "cache_tokens": 0,
    }
    _GC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _GC_SESSION_FILE.write_text(json.dumps(state))
    return 0


def record_model_usage() -> int:
    """Called by AfterModel hook. Accumulates token counts from each API call."""
    payload = _read_payload()
    state = _read_state()
    if state is None:
        return 0

    llm_req = payload.get("llm_request") or {}
    llm_res = payload.get("llm_response") or {}
    usage = llm_res.get("usageMetadata") or {}

    model = llm_req.get("model") or state.get("model") or ""
    prompt_tokens = int(usage.get("promptTokenCount") or 0)
    candidates_tokens = int(usage.get("candidatesTokenCount") or 0)
    cached_tokens = int(usage.get("cachedContentTokenCount") or 0)

    state["model"] = model or state.get("model", "")
    # Keep the latest (largest) cumulative prompt token count
    state["prompt_tokens"] = max(int(state.get("prompt_tokens", 0)), prompt_tokens)
    # Accumulate output tokens across all model calls in this turn
    state["output_tokens"] = int(state.get("output_tokens", 0)) + candidates_tokens
    # Keep the largest cumulative cached token count
    state["cache_tokens"] = max(int(state.get("cache_tokens", 0)), cached_tokens)

    _GC_SESSION_FILE.write_text(json.dumps(state))
    return 0


def handle_agent_stop() -> int:
    """Called by AfterAgent hook. Writes a session record and resets token accumulators."""
    payload = _read_payload()
    state = _read_state()
    # No gc-session ⇒ SessionStart never ran ⇒ AfterAgent fired without
    # a real turn (e.g. an external daemon). Not a session.
    if state is None:
        return 0

    cwd_str = (state or {}).get("cwd") or payload.get("cwd") or ""
    cwd = Path(cwd_str) if cwd_str else Path.cwd()
    project_dir = (find_project_dir(start=cwd) if cwd_str else find_project_dir()) or find_hub()
    can_append_project_log = project_dir is not None and (project_dir / AI_LOG_FILENAME).exists()

    now = datetime.now()
    turn_start_str = (state or {}).get("turn_start")
    try:
        start = datetime.fromisoformat(turn_start_str) if turn_start_str else now
    except (ValueError, TypeError):
        start = now

    # Stale state guard: a gc-session older than 12 hours cannot be a real session.
    # Delete it silently rather than writing a phantom multi-day record.
    max_stale_seconds = 12 * 3600
    if (now - start).total_seconds() > max_stale_seconds:
        if _GC_SESSION_FILE.exists():
            _GC_SESSION_FILE.unlink()
        return 0

    branch = current_branch(cwd)
    commit_count = commits_in_window(cwd, start, now)
    base_tags: list[str] = []

    # D-1: resolve attribution source before building the session so provenance
    # is recorded in the log line.
    _active = read_active_project()
    if _active:
        _gc_project: str | None = _active
        _gc_attr_method: str | None = "timer"
        _gc_inferred_tag: list[str] = []
    else:
        _gc_project, _gc_rung = infer_project_with_source(cwd)
        _gc_attr_method = _gc_rung  # repo-map | toml | git-auto | None
        _gc_inferred_tag = ["attribution:inferred"] if _gc_project else []

    _remote = current_remote(cwd)

    # Try to enrich from the history file for accurate multi-model cost
    session_id = (state or {}).get("session_id") or ""
    history_summary = None
    if session_id:
        history_path = find_session_file(session_id)
        if history_path:
            history_summary = parse_session_file(history_path)

    rich_session_id: str | None = session_id or None
    rich_tool_calls: int | None = None
    rich_tool_errors: int | None = None
    rich_wall_seconds: int | None = None
    rich_model_breakdown: str | None = None
    rich_code_added: int | None = None
    rich_code_removed: int | None = None
    rich_resume_command: str | None = None
    rich_interaction_count: int | None = None
    rich_user_message_count: int | None = None
    rich_assistant_message_count: int | None = None
    rich_prompt_count: int | None = None
    rich_interaction_data_available: bool | None = None

    if history_summary:
        model = history_summary.dominant_model or "gemini-unknown"
        net_input = history_summary.total_input
        output_tokens = history_summary.total_output
        cache_tokens = history_summary.total_cache
        cost = history_summary.cost_usd
        tokens_available = net_input > 0 or output_tokens > 0
        tags = base_tags + _gc_inferred_tag
        # Rich telemetry — use proper fields, not tags
        if history_summary.total_tool_calls:
            rich_tool_calls = history_summary.total_tool_calls
        if history_summary.total_tool_errors:
            rich_tool_errors = history_summary.total_tool_errors
        rich_wall_seconds = max(0, int((now - start).total_seconds()))
        rich_model_breakdown = _format_model_breakdown(history_summary.model_stats) or None
        # Multi-model: cost is Σ per-model and the primary model is the
        # costliest, so per-model rollups and the one-line model stay
        # correct. Single-model: untouched (rich_model_breakdown None).
        if rich_model_breakdown:
            _segs = _model_segs(history_summary.model_stats)
            if _segs:
                model = _primary_model(_segs)
            _bc = _breakdown_cost(rich_model_breakdown)
            if _bc is not None:
                cost = _bc
        rich_code_added = history_summary.code_added
        rich_code_removed = history_summary.code_removed
        rich_resume_command = history_summary.resume_command
        rich_interaction_count = history_summary.interaction_count
        rich_user_message_count = history_summary.user_message_count
        rich_assistant_message_count = history_summary.assistant_message_count
        rich_prompt_count = history_summary.prompt_count
        rich_interaction_data_available = True
    else:
        # Fall back to accumulated hook state
        model = (state or {}).get("model") or payload.get("model") or "gemini-unknown"
        prompt_tokens = int((state or {}).get("prompt_tokens") or 0)
        output_tokens = int((state or {}).get("output_tokens") or 0)
        cache_tokens = int((state or {}).get("cache_tokens") or 0)
        net_input = max(0, prompt_tokens - cache_tokens)
        cost = calculate_cost(model, net_input, output_tokens, cache_read=cache_tokens)
        tokens_available = prompt_tokens > 0 or output_tokens > 0
        tags = base_tags + _gc_inferred_tag
        rich_wall_seconds = max(0, int((now - start).total_seconds()))

    session = AiSession(
        start=start,
        end=now,
        tool="gemini-cli",
        model=model,
        input_tokens=net_input,
        output_tokens=output_tokens,
        cost_usd=cost,
        project=_gc_project,
        cache_read=cache_tokens or None,
        tokens_available=tokens_available,
        billing="api",
        source="hook",
        attr_method=_gc_attr_method,
        tags=tags,
        session_id=rich_session_id,
        tool_calls=rich_tool_calls,
        tool_errors=rich_tool_errors,
        wall_seconds=rich_wall_seconds,
        model_breakdown=rich_model_breakdown,
        code_added=rich_code_added,
        code_removed=rich_code_removed,
        resume_command=rich_resume_command,
        branch=branch,
        remote=_remote,
        commit_count=commit_count,
        interaction_count=rich_interaction_count,
        user_message_count=rich_user_message_count,
        assistant_message_count=rich_assistant_message_count,
        prompt_count=rich_prompt_count,
        interaction_data_available=rich_interaction_data_available,
        telemetry_source="gemini-history" if history_summary else "gemini-hook",
        telemetry_trust="observed",
    )

    # A hook fire with no evidence of a real turn (aborted turn,
    # SessionStart-only state, or a spurious/shared invocation) must not
    # become a ledger row. Still reset state so the next turn is clean.
    if (
        not session_has_evidence(session, history=history_summary is not None)
        or session_is_implausible(session)
        or session_is_synthetic_telemetry(session)
    ):
        _reset_state(payload)
        return 0

    if can_append_project_log and project_dir is not None:
        append_session(project_dir, session)
    else:
        path = write_unattributed_session(session)
        # stderr: hooks communicate back to the tool via stderr, not stdout
        print(
            f"[halyard] session saved to {path} — run 'halyard adopt' in this directory.",
            file=sys.stderr,
        )
    _reset_state(payload)
    maybe_show_dashboard_hint()
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_payload() -> dict:  # type: ignore[type-arg]
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _read_state() -> dict[str, Any] | None:
    if not _GC_SESSION_FILE.exists():
        return None
    try:
        result: dict[str, Any] = json.loads(_GC_SESSION_FILE.read_text())
        return result
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def _reset_state(payload: dict) -> None:  # type: ignore[type-arg]
    """After writing a record, reset token accumulators and update turn_start for next turn."""
    state = _read_state()
    if state is None:
        return
    # Next turn starts now
    state["turn_start"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    state["model"] = ""
    state["prompt_tokens"] = 0
    state["output_tokens"] = 0
    state["cache_tokens"] = 0
    _GC_SESSION_FILE.write_text(json.dumps(state))


def _model_segs(model_stats: list[GeminiModelStats]) -> list[ModelSeg]:
    return [
        ModelSeg(s.model, s.input_tokens, s.output_tokens, s.cache_tokens, 0)
        for s in model_stats
        if s.model and s.requests > 0
    ]


def _format_model_breakdown(model_stats: list[GeminiModelStats]) -> str:
    """v2.61 usage-form breakdown, only for genuinely multi-model
    sessions (``model:in/out/cr/cw|…``). Single-model → '' so the
    caller keeps ``model_breakdown=None`` and the single-model path."""
    segs = _model_segs(model_stats)
    if len(segs) < 2:
        return ""
    return _encode_breakdown(segs)
