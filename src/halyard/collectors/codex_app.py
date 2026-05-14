"""Codex Desktop session importer.

Reads JSONL session files from ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl,
extracts token usage and timing, and appends records to the Halyard project's
ai-sessions.log.

State is maintained in ~/.halyard/codex-imported (one session UUID per line)
so repeated runs don't duplicate entries.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession, append_session, find_project_dir
from halyard.git_context import commits_in_window, current_branch, infer_project
from halyard.hub import find_hub

_CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
_IMPORTED_STATE_FILE = Path.home() / ".halyard" / "codex-imported"
_UUID_RE = re.compile(
    r"rollout-\d{4}-\d{2}-\d{2}T[\d-]+-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


def import_codex_sessions(
    project_dir: Path | None = None,
    *,
    dry_run: bool = False,
    all_projects: bool = False,
) -> list[AiSession]:
    """Import new Codex sessions. Returns the sessions that were (or would be) written."""
    if not _CODEX_SESSIONS_DIR.exists():
        return []

    already_imported = _load_imported_state()
    session_files = sorted(_CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"))

    imported: list[AiSession] = []
    newly_imported_ids: list[str] = []

    for path in session_files:
        session_id = _extract_uuid(path)
        if session_id is None or session_id in already_imported:
            continue

        parsed = _parse_session_file(path)
        if parsed is None:
            continue

        session, cwd = parsed

        # Resolve project directory
        target_dir = project_dir
        if target_dir is None and cwd is not None:
            target_dir = find_project_dir(start=Path(cwd))
        if target_dir is None:
            target_dir = find_hub()
        if target_dir is None and not all_projects:
            continue  # can't associate with any Halyard project
        if target_dir is not None and not (target_dir / AI_LOG_FILENAME).exists():
            continue  # project not initialised

        # Enrich project attribution and branch via git when not already set
        if cwd is not None:
            cwd_path = Path(cwd)
            if session.project is None:
                session.project = infer_project(cwd_path)
            session.branch = current_branch(cwd_path)
            session.commit_count = commits_in_window(cwd_path, session.start, session.end)
            session.outcome_data_available = (
                session.branch is not None or session.commit_count is not None
            )

        if not dry_run and target_dir is not None:
            append_session(target_dir, session)

        imported.append(session)
        newly_imported_ids.append(session_id)

    if not dry_run and newly_imported_ids:
        _save_imported_state(already_imported | set(newly_imported_ids))

    return imported


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------


def _parse_session_file(path: Path) -> tuple[AiSession, str | None] | None:
    """Parse one rollout JSONL file. Returns (AiSession, cwd) or None to skip."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    session_start: datetime | None = None
    session_end: datetime | None = None
    cwd: str | None = None
    model: str = "codex"
    last_token_usage: dict | None = None  # type: ignore[type-arg]
    user_message_count = 0
    assistant_message_count = 0
    tool_calls = 0
    tool_errors = 0

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")
        ts_str = event.get("timestamp", "")
        ts = _parse_iso(ts_str)

        if ts is not None:
            if session_start is None or ts < session_start:
                session_start = ts
            if session_end is None or ts > session_end:
                session_end = ts

        payload = event.get("payload", {})

        if event_type == "session_meta":
            cwd = payload.get("cwd") or cwd
            # Use start timestamp from meta when available (more accurate)
            meta_start = _parse_iso(payload.get("timestamp", ""))
            if meta_start is not None:
                session_start = meta_start

        elif event_type == "turn_context":
            cwd = payload.get("cwd") or cwd
            m = payload.get("model")
            if m:
                model = str(m)

        elif event_type == "event_msg":
            msg_type = payload.get("type", "")
            if msg_type == "token_count":
                info = payload.get("info") or {}
                usage = info.get("total_token_usage")
                if usage:
                    last_token_usage = usage
            elif msg_type in {"user_message", "user_input", "input_text"}:
                user_message_count += 1
            elif msg_type in {"agent_message", "assistant_message", "assistant"}:
                assistant_message_count += 1
            elif msg_type in {"exec_command_begin", "apply_patch_begin", "tool_call_begin"}:
                tool_calls += 1
            elif msg_type in {"exec_command_end", "apply_patch_end", "tool_call_end"}:
                if _payload_failed(payload):
                    tool_errors += 1

    if session_start is None or session_end is None:
        return None

    # Extract token counts from last cumulative snapshot.
    # Newer o-series Codex sessions report total_tokens only (input/output = 0).
    total_input = 0
    cached_input = 0
    output_tokens = 0
    total_tokens = 0

    if last_token_usage:
        total_input = int(last_token_usage.get("input_tokens", 0))
        cached_input = int(last_token_usage.get("cached_input_tokens", 0))
        output_tokens = int(last_token_usage.get("output_tokens", 0))
        total_tokens = int(last_token_usage.get("total_tokens", 0))

    # Skip sessions with no real work.
    if output_tokens == 0 and total_tokens == 0:
        return None

    # o-series fallback: use total_tokens as net_input proxy, mark breakdown unavailable.
    tokens_available = output_tokens > 0
    if tokens_available:
        net_input = max(0, total_input - cached_input)
    else:
        net_input = total_tokens
        output_tokens = 0

    session = AiSession(
        start=session_start,
        end=session_end,
        tool="codex",
        model=model,
        input_tokens=net_input,
        output_tokens=output_tokens,
        cost_usd=0.0,
        cache_read=cached_input or None,
        tokens_available=tokens_available,
        billing="credits",
        source="sdk",
        tool_calls=tool_calls if tool_calls else None,
        tool_errors=tool_errors if tool_errors else None,
        wall_seconds=max(0, int((session_end - session_start).total_seconds())),
        interaction_count=(
            user_message_count + assistant_message_count
            if user_message_count or assistant_message_count
            else None
        ),
        user_message_count=user_message_count if user_message_count else None,
        assistant_message_count=assistant_message_count if assistant_message_count else None,
        prompt_count=user_message_count if user_message_count else None,
        interaction_data_available=bool(user_message_count or assistant_message_count),
        telemetry_source="codex-jsonl",
        telemetry_trust="observed",
    )
    return session, cwd


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def _load_imported_state() -> set[str]:
    if not _IMPORTED_STATE_FILE.exists():
        return set()
    return {line.strip() for line in _IMPORTED_STATE_FILE.read_text().splitlines() if line.strip()}


def _save_imported_state(ids: set[str]) -> None:
    _IMPORTED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _IMPORTED_STATE_FILE.write_text("\n".join(sorted(ids)) + "\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_uuid(path: Path) -> str | None:
    m = _UUID_RE.search(path.name)
    return m.group(1) if m else None


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # Normalise to local naive for consistency with the rest of Halyard
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _payload_failed(payload: dict) -> bool:  # type: ignore[type-arg]
    exit_code = payload.get("exit_code")
    if exit_code is None:
        exit_code = payload.get("exitCode")
    if exit_code is not None:
        try:
            return int(exit_code) != 0
        except (TypeError, ValueError):
            return False
    status = str(payload.get("status") or "").lower()
    return status in {"error", "failed", "failure"}
