"""Windsurf (Codeium) hook collector.

Three entry points, wired up by `halyard install-windsurf-hook`:

  pre_user_prompt        →  record_turn(is_start=True)   (halyard windsurf-session-start)
  post_cascade_response  →  record_turn(is_start=False)  (halyard windsurf-session-stop)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

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
)
from halyard.git_context import infer_project_with_source
from halyard.hub import find_hub

_WS_TTL = timedelta(minutes=30)

# v5.16/B07: trajectory_id arrives from untrusted hook stdin and is used to
# build a state-file path. Only allow a safe slug so it cannot escape the
# ws-sessions/ root via traversal ("..", "/", absolute, leading "..").
_SAFE_TID = re.compile(r"^[A-Za-z0-9._-]+$")


def _ws_sessions_dir() -> Path:
    return Path.home() / ".halyard" / "ws-sessions"


def _safe_state_path(tid: str, state_dir: Path) -> Path | None:
    """v5.16/B07: map an untrusted trajectory_id to a path strictly inside
    ``state_dir``. Returns None for anything that would escape the root."""
    if not tid or tid in {".", ".."} or not _SAFE_TID.match(tid):
        return None
    path = state_dir / f"{tid}.json"
    try:
        resolved = path.resolve()
        root = state_dir.resolve()
    except OSError:
        return None
    if resolved.parent != root:
        return None
    return path


def record_turn(payload: dict[str, Any], is_start: bool) -> int:
    """Called by Windsurf hooks. Records turn metadata and updates session state."""
    tid = payload.get("trajectory_id")
    if not tid:
        return 0

    state_dir = _ws_sessions_dir()
    # v5.16/B07: sanitize trajectory_id before any mkdir/write so a malicious
    # payload cannot traverse out of ws-sessions/ and overwrite arbitrary JSON.
    path = _safe_state_path(str(tid), state_dir)
    if path is None:
        return 0

    state_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    state = _read_state(path) or {
        "start": now.isoformat(timespec="seconds"),
        "user_count": 0,
        "assistant_count": 0,
        "model": payload.get("model_name") or "windsurf-unknown",
    }

    state["last_activity"] = now.isoformat(timespec="seconds")
    if is_start:
        state["user_count"] += 1
        if "model_name" in payload:
            state["model"] = payload["model_name"]
    else:
        state["assistant_count"] += 1

    path.write_text(json.dumps(state), encoding="utf-8")

    # Trigger finalization of OTHER stale sessions while we are here
    finalize_stale_sessions()

    return 0


def finalize_stale_sessions(project_dir: Path | None = None) -> int:
    """Close and log Windsurf sessions that have seen no activity for >30 mins."""
    state_dir = _ws_sessions_dir()
    if not state_dir.exists():
        return 0

    count = 0
    now = datetime.now()
    for path in state_dir.glob("*.json"):
        state = _read_state(path)
        if not state:
            path.unlink(missing_ok=True)
            continue

        last_act = datetime.fromisoformat(state["last_activity"])
        if now - last_act > _WS_TTL and _finalize_one(path, state, project_dir):
            count += 1
    return count


def _finalize_one(path: Path, state: dict[str, Any], project_dir: Path | None) -> bool:
    """Convert a trajectory state file to an AiSession record."""
    start = datetime.fromisoformat(state["start"])
    end = datetime.fromisoformat(state["last_activity"])
    model = state.get("model", "windsurf-unknown")

    session = AiSession(
        start=start,
        end=end,
        tool="windsurf",
        model=model,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        tokens_available=False,
        interaction_count=state["user_count"] + state["assistant_count"],
        user_message_count=state["user_count"],
        assistant_message_count=state["assistant_count"],
        prompt_count=state["user_count"],
        interaction_data_available=True,
        telemetry_source="windsurf-hook",
        telemetry_trust="observed",
    )

    if not session_has_evidence(session) or session_is_implausible(session):
        path.unlink(missing_ok=True)
        return False

    # Resolve project
    cwd = Path.cwd()
    target_dir = project_dir or find_project_dir(start=cwd) or find_hub()
    active = read_active_project()

    proj, method = infer_project_with_source(cwd)
    if active:
        proj, method = active, "timer"

    session.project = proj
    session.attr_method = method

    if target_dir and (target_dir / AI_LOG_FILENAME).exists():
        append_session(target_dir, session)
        maybe_emit_milestones(target_dir)
        maybe_show_dashboard_hint()
    else:
        write_unattributed_session(session)

    path.unlink(missing_ok=True)
    return True


def _read_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return None


def read_payload() -> dict[str, Any]:
    """Read JSON payload from stdin."""
    if sys.stdin.isatty():
        return {}
    try:
        return cast(dict[str, Any], json.loads(sys.stdin.read()))
    except (json.JSONDecodeError, EOFError):
        return {}
