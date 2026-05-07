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
from datetime import datetime
from pathlib import Path

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    find_project_dir,
    write_unattributed_session,
)
from halyard.git_context import current_branch, infer_project
from halyard.hub import find_hub

_CURSOR_SESSION_FILE = Path.home() / ".halyard" / "cursor-session"
_HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


def record_session_start() -> int:
    """Called by beforeSubmitPrompt hook. Records start timestamp."""
    if _CURSOR_SESSION_FILE.exists():
        return 0  # already tracking this session — budget already checked

    # Budget check fires once per session, before the session file is written
    active = _read_active_project()
    if active:
        project_dir = find_project_dir() or find_hub()
        if project_dir:
            from halyard.budget import check_budget

            warning = check_budget(active, project_dir)
            if warning:
                print(warning)

    _CURSOR_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CURSOR_SESSION_FILE.write_text(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    return 0


def handle_stop_hook() -> int:
    """Called by stop hook. Reads JSON payload from stdin, writes session record."""
    payload = _read_payload()

    project_dir = _resolve_project_dir(payload) or find_hub()
    can_append_project_log = project_dir is not None and (project_dir / AI_LOG_FILENAME).exists()

    now = datetime.now()
    start = _read_session_start() or now
    _clear_session_start()

    usage = payload.get("usage") or payload.get("message", {}).get("usage", {}) or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    cache_read = int(usage.get("cache_read_input_tokens", 0) or usage.get("cache_read", 0))
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or usage.get("cache_write", 0))
    tokens_available = input_tokens > 0 or output_tokens > 0

    model = payload.get("model") or payload.get("stop_model") or "cursor-unknown"

    # Infer project and branch from workspace root when no active timer is running
    roots = payload.get("workspace_roots") or []
    cwd_for_git = Path(roots[0]) if roots else None
    project = _read_active_project() or (infer_project(cwd_for_git) if cwd_for_git else None)
    branch = current_branch(cwd_for_git) if cwd_for_git else None

    session = AiSession(
        start=start,
        end=now,
        tool="cursor",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.0,
        project=project,
        cache_read=cache_read or None,
        cache_write=cache_write or None,
        tokens_available=tokens_available,
        billing="credits",
        source="hook",
        tags=[f"branch:{branch}"] if branch else [],
    )

    if can_append_project_log and project_dir is not None:
        append_session(project_dir, session)
    else:
        path = write_unattributed_session(session)
        print(
            f"[halyard] session saved to {path} — run 'halyard assign-unattributed' to review.",
            file=sys.stderr,
        )
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


def _read_session_start() -> datetime | None:
    if not _CURSOR_SESSION_FILE.exists():
        return None
    try:
        return datetime.fromisoformat(_CURSOR_SESSION_FILE.read_text().strip())
    except ValueError:
        return None


def _clear_session_start() -> None:
    _CURSOR_SESSION_FILE.unlink(missing_ok=True)


def _read_active_project() -> str | None:
    if not _HALYARD_ACTIVE.exists():
        return None
    for line in _HALYARD_ACTIVE.read_text().splitlines():
        if line.startswith("slug="):
            return line[5:]
    return None
