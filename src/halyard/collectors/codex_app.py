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
from datetime import UTC, datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession, append_session, find_project_dir

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
        if target_dir is None and not all_projects:
            continue  # can't associate with any Halyard project
        if target_dir is not None and not (target_dir / AI_LOG_FILENAME).exists():
            continue  # project not initialised

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

    if session_start is None or session_end is None:
        return None

    # Extract token counts from last cumulative snapshot
    total_input = 0
    cached_input = 0
    output_tokens = 0

    if last_token_usage:
        total_input = int(last_token_usage.get("input_tokens", 0))
        cached_input = int(last_token_usage.get("cached_input_tokens", 0))
        output_tokens = int(last_token_usage.get("output_tokens", 0))

    # Skip plugin-init sessions with no real work
    if output_tokens == 0:
        return None

    net_input = max(0, total_input - cached_input)

    session = AiSession(
        start=session_start,
        end=session_end,
        tool="codex",
        model=model,
        input_tokens=net_input,
        output_tokens=output_tokens,
        cost_usd=0.0,
        cache_read=cached_input or None,
        tokens_available=True,
        billing="credits",
        source="sdk",
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
        # Normalise to naive UTC for consistent comparison
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except ValueError:
        return None
