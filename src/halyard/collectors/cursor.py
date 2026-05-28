"""Cursor hook collector.

Two entry points, wired up by `halyard install-cursor-hook`:

  beforeSubmitPrompt  →  record_session_start()   (halyard cursor-session)
  stop                →  handle_stop_hook()         (halyard cursor-hook)

The stop payload is structurally identical to Claude Code's Stop payload, with
additional Cursor-specific fields (cursor_version, workspace_roots, user_email,
transcript_path).  workspace_roots[0] is preferred over cwd for project lookup
because it's the actual VS Code workspace folder, not the terminal cwd.

Billing is "credits" for all Cursor sessions — costs are bundled in the plan
and not charged per-token via API.  cost_usd is therefore 0.0.
"""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    find_project_dir,
    maybe_emit_milestones,
    maybe_show_dashboard_hint,
    read_active_project,
    write_unattributed_session,
)
from halyard.collectors import (
    session_has_evidence,
    session_is_implausible,
    session_is_synthetic_telemetry,
)
from halyard.git_context import (
    commits_in_window,
    current_branch,
    current_remote,
    head_sha,
    infer_project,
    numstat_delta,
)
from halyard.hub import find_hub

_CURSOR_SESSION_FILE = Path.home() / ".halyard" / "cursor-session"


def record_session_start() -> int:
    """Called by beforeSubmitPrompt hook. Records start timestamp."""
    if _CURSOR_SESSION_FILE.exists():
        return 0  # already tracking this session — budget already checked

    # Budget check fires once per session, before the session file is written
    active = read_active_project()
    if active:
        project_dir = find_project_dir() or find_hub()
        if project_dir:
            from halyard.budget import check_budget

            warning = check_budget(active, project_dir)
            if warning:
                print(warning)  # budget warning: hooks write to stdout for tool pickup

    cwd = Path.cwd()
    _CURSOR_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "start": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "sha_at_start": head_sha(cwd),
    }
    _CURSOR_SESSION_FILE.write_text(json.dumps(state), encoding="utf-8")
    return 0


def handle_stop_hook() -> int:
    """Called by stop hook. Reads JSON payload from stdin, writes session record."""
    # A real turn always records its start via beforeSubmitPrompt
    # (record_session_start writes this file). No state file ⇒ a
    # stop-only fire (e.g. an external daemon triggering the hook) ⇒
    # not a real turn, do not record.
    if not _CURSOR_SESSION_FILE.exists():
        return 0

    payload = _read_payload()

    project_dir = _resolve_project_dir(payload) or find_hub()
    can_append_project_log = project_dir is not None and (project_dir / AI_LOG_FILENAME).exists()

    now = datetime.now()
    session_state = _read_session_state()
    start = session_state.get("start_dt") or now
    sha_at_start: str | None = session_state.get("sha")
    _clear_session_start()

    usage = payload.get("usage") or payload.get("message", {}).get("usage", {}) or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    cache_read = int(usage.get("cache_read_input_tokens", 0) or usage.get("cache_read", 0))
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or usage.get("cache_write", 0))
    tokens_available = input_tokens > 0 or output_tokens > 0

    model = payload.get("model") or payload.get("stop_model") or "cursor-unknown"

    # D-1: resolve attribution source so provenance is recorded in the log.
    # Priority: active timer > workspace root git inference.
    roots = payload.get("workspace_roots") or []
    cwd_for_git = Path(roots[0]) if roots else None
    branch = current_branch(cwd_for_git) if cwd_for_git else None

    # v2.24: commit count and code delta (numstat uses workspace cwd; sha captured at hook-fire cwd)
    commit_count = commits_in_window(cwd_for_git, start, now) if cwd_for_git else None
    code_added: int | None = None
    code_removed: int | None = None
    files_touched_count: int | None = None
    if sha_at_start and cwd_for_git:
        delta = numstat_delta(cwd_for_git, sha_at_start)
        if delta is not None:
            code_added, code_removed = delta
    files_touched_count = _optional_int(payload, "files_touched_count", "filesTouchedCount")

    interaction_counts = _safe_interaction_counts(payload)
    payload_tool_calls, payload_tool_errors = _safe_tool_counts(payload)

    _active = read_active_project()
    _project: str | None
    _attr_method: str | None
    _extra_tags: list[str]
    if _active:
        _project = _active
        _attr_method = "timer"
        _extra_tags = []
    elif cwd_for_git:
        _inferred = infer_project(cwd_for_git)
        _project = _inferred
        # workspace_roots is Cursor-specific — stronger than pure git inference
        _attr_method = "ws_root" if _inferred else None
        _extra_tags = ["attribution:inferred"] if _inferred else []
    else:
        _project = None
        _attr_method = None
        _extra_tags = []

    _remote = current_remote(cwd_for_git) if cwd_for_git else None

    session = AiSession(
        start=start,
        end=now,
        tool="cursor",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.0,
        project=_project,
        cache_read=cache_read or None,
        cache_write=cache_write or None,
        tokens_available=tokens_available,
        billing="credits",
        source="hook",
        attr_method=_attr_method,
        tags=_extra_tags,
        branch=branch,
        remote=_remote,
        commit_count=commit_count,
        code_added=code_added,
        code_removed=code_removed,
        tool_calls=payload_tool_calls,
        tool_errors=payload_tool_errors,
        interaction_count=interaction_counts["interaction_count"],
        user_message_count=interaction_counts["user_message_count"],
        assistant_message_count=interaction_counts["assistant_message_count"],
        prompt_count=interaction_counts["prompt_count"],
        accepted_suggestion_count=interaction_counts["accepted_suggestion_count"],
        rejected_suggestion_count=interaction_counts["rejected_suggestion_count"],
        files_touched_count=files_touched_count,
        interaction_data_available=bool(interaction_counts["interaction_data_available"]),
        outcome_data_available=any(
            value is not None for value in (branch, commit_count, code_added, code_removed)
        ),
        telemetry_source="cursor-hook",
        telemetry_trust="observed",
    )

    # A stop fire with no evidence of a real turn (the beforeSubmitPrompt
    # /stop chain can fire — incl. via other vendors sharing the hook
    # array — without a Cursor turn) must not become a ledger row. The
    # session-start state was already cleared above.
    if (
        not session_has_evidence(session)
        or session_is_implausible(session)
        or session_is_synthetic_telemetry(session)
    ):
        return 0

    if can_append_project_log and project_dir is not None:
        append_session(project_dir, session)
        maybe_emit_milestones(project_dir)
    else:
        path = write_unattributed_session(session)
        # stderr: hooks communicate back to the tool via stderr, not stdout
        print(
            f"[halyard] session saved to {path} — run 'halyard adopt' in this directory.",
            file=sys.stderr,
        )
    maybe_show_dashboard_hint()
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_project_dir(payload: dict) -> Path | None:  # type: ignore[type-arg]
    """Return the Halyard project dir, preferring workspace_roots from the payload.

    If workspace_roots is non-empty but none match a Halyard project, return None
    rather than falling back to CWD — the workspace is authoritative for Cursor.
    """
    roots = payload.get("workspace_roots") or []
    for root in roots:
        project_dir = find_project_dir(start=Path(root))
        if project_dir is not None:
            return project_dir
    if roots:
        return None  # roots were given but none matched — don't use CWD
    return find_project_dir()


def _read_payload() -> dict:  # type: ignore[type-arg]
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _safe_interaction_counts(payload: dict) -> dict[str, int | bool | None]:  # type: ignore[type-arg]
    prompt_count = _optional_int(payload, "prompt_count", "promptCount")
    if prompt_count is None and "prompt" in payload:
        prompt_count = 1

    user_message_count = _optional_int(payload, "user_message_count", "userMessageCount")
    if user_message_count is None:
        user_message_count = prompt_count

    assistant_message_count = _optional_int(
        payload, "assistant_message_count", "assistantMessageCount"
    )
    interaction_count = _optional_int(payload, "interaction_count", "interactionCount")
    if interaction_count is None:
        known = [user_message_count, assistant_message_count]
        if any(value is not None for value in known):
            interaction_count = sum(value or 0 for value in known)

    accepted = _optional_int(
        payload,
        "accepted_suggestion_count",
        "acceptedSuggestionCount",
        "accepted_suggestions",
    )
    rejected = _optional_int(
        payload,
        "rejected_suggestion_count",
        "rejectedSuggestionCount",
        "rejected_suggestions",
    )
    has_data = any(
        value is not None
        for value in (
            interaction_count,
            user_message_count,
            assistant_message_count,
            prompt_count,
            accepted,
            rejected,
        )
    )
    return {
        "interaction_count": interaction_count,
        "user_message_count": user_message_count,
        "assistant_message_count": assistant_message_count,
        "prompt_count": prompt_count,
        "accepted_suggestion_count": accepted,
        "rejected_suggestion_count": rejected,
        "interaction_data_available": has_data,
    }


def _safe_tool_counts(payload: dict) -> tuple[int | None, int | None]:  # type: ignore[type-arg]
    explicit_calls = _optional_int(payload, "tool_calls", "toolCallsCount")
    explicit_errors = _optional_int(payload, "tool_errors", "toolErrorsCount")
    tool_calls_raw = payload.get("toolCalls") or payload.get("tool_calls")
    if not isinstance(tool_calls_raw, list):
        return explicit_calls, explicit_errors

    calls = len([item for item in tool_calls_raw if isinstance(item, dict)])
    errors = sum(
        1
        for item in tool_calls_raw
        if isinstance(item, dict) and str(item.get("status") or "").lower() == "error"
    )
    return calls, errors


def _optional_int(payload: dict, *keys: str) -> int | None:  # type: ignore[type-arg]
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        with suppress(TypeError, ValueError):
            return max(0, int(value))
    return None


def _read_session_state() -> dict[str, Any]:
    """Return {"start_dt": datetime, "sha": str|None} from the session file.

    Handles both the new JSON format (v2.24+) and the legacy plain ISO timestamp.
    """
    if not _CURSOR_SESSION_FILE.exists():
        return {}
    try:
        raw = _CURSOR_SESSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    try:
        data = json.loads(raw)
        start_dt: datetime | None = None
        with suppress(ValueError, TypeError):
            start_dt = datetime.fromisoformat(data.get("start", ""))
        return {"start_dt": start_dt, "sha": data.get("sha_at_start")}
    except (json.JSONDecodeError, ValueError):
        with suppress(ValueError):
            return {"start_dt": datetime.fromisoformat(raw), "sha": None}
        return {}


def _clear_session_start() -> None:
    _CURSOR_SESSION_FILE.unlink(missing_ok=True)
