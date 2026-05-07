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

from halyard.ai_log import AI_LOG_FILENAME, AiSession, append_session, find_project_dir
from halyard.git_context import current_branch, infer_project
from halyard.hub import find_hub
from halyard.pricing import calculate_cost

_GC_SESSION_FILE = Path.home() / ".halyard" / "gc-session"


def record_session_start() -> int:
    """Called by SessionStart hook. Saves start time, session_id, and cwd."""
    payload = _read_payload()
    now_str = payload.get("timestamp") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    state = {
        "turn_start": now_str,
        "session_id": payload.get("session_id", ""),
        "cwd": payload.get("cwd", ""),
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

    cwd_str = (state or {}).get("cwd") or payload.get("cwd") or ""
    cwd = Path(cwd_str) if cwd_str else Path.cwd()
    project_dir = (find_project_dir(start=cwd) if cwd_str else find_project_dir()) or find_hub()

    if project_dir is None or not (project_dir / AI_LOG_FILENAME).exists():
        _reset_state(payload)
        return 0

    now = datetime.now()
    turn_start_str = (state or {}).get("turn_start")
    try:
        start = datetime.fromisoformat(turn_start_str) if turn_start_str else now
    except ValueError:
        start = now

    model = (state or {}).get("model") or payload.get("model") or "gemini-unknown"
    prompt_tokens = int((state or {}).get("prompt_tokens") or 0)
    output_tokens = int((state or {}).get("output_tokens") or 0)
    cache_tokens = int((state or {}).get("cache_tokens") or 0)
    # promptTokenCount is cumulative (includes cached); net_input is the billable portion
    net_input = max(0, prompt_tokens - cache_tokens)
    tokens_available = prompt_tokens > 0 or output_tokens > 0
    branch = current_branch(cwd)

    session = AiSession(
        start=start,
        end=now,
        tool="gemini-cli",
        model=model,
        input_tokens=net_input,
        output_tokens=output_tokens,
        cost_usd=calculate_cost(model, net_input, output_tokens, cache_read=cache_tokens),
        project=_read_active_project() or infer_project(cwd),
        cache_read=cache_tokens or None,
        tokens_available=tokens_available,
        billing="api",
        source="hook",
        tags=[f"branch:{branch}"] if branch else [],
    )

    append_session(project_dir, session)
    _reset_state(payload)
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


def _read_active_project() -> str | None:
    active = Path.home() / ".halyard" / "active"
    if not active.exists():
        return None
    for line in active.read_text().splitlines():
        if line.startswith("slug="):
            return line[5:]
    return None
