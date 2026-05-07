"""Claude Code hook collector.

Two entry points, wired up by `halyard install-hook`:

  UserPromptSubmit  →  record_session_start()  (halyard cc-session)
  Stop              →  handle_stop_hook()       (halyard cc-hook)
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
from halyard.pricing import calculate_cost, model_is_known

_CC_SESSION_FILE = Path.home() / ".halyard" / "cc-session"
_HALYARD_ACTIVE = Path.home() / ".halyard" / "active"


def record_session_start() -> int:
    """Called by UserPromptSubmit hook. Records start timestamp once per session."""
    if _CC_SESSION_FILE.exists():
        return 0  # already tracking this session — budget already checked

    # Budget check fires once per session, before the session file is written
    active = _read_active_project()
    if active:
        cwd = Path.cwd()
        project_dir = find_project_dir(start=cwd) or find_hub()
        if project_dir:
            from halyard.budget import check_budget

            warning = check_budget(active, project_dir)
            if warning:
                print(warning)

    _CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CC_SESSION_FILE.write_text(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    return 0


def handle_stop_hook() -> int:
    """Called by Stop hook. Reads JSON payload from stdin, writes session record."""
    payload = _read_payload()

    # Cursor fires Claude Code's Stop hook internally — cursor.py handles those sessions
    if payload.get("cursor_version"):
        _clear_session_start()
        return 0

    cwd = Path.cwd()
    project_dir = find_project_dir(start=cwd) or find_hub()
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

    model = (
        payload.get("model")
        or payload.get("stop_model")
        or (_read_model_from_settings(project_dir) if project_dir else None)
        or "claude-unknown"
    )

    cost = calculate_cost(model, input_tokens, output_tokens, cache_read, cache_write)
    branch = current_branch(cwd)

    session = AiSession(
        start=start,
        end=now,
        tool="claude-code",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        project=_read_active_project() or infer_project(cwd),
        cache_read=cache_read or None,
        cache_write=cache_write or None,
        tokens_available=tokens_available,
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


def _read_payload() -> dict:  # type: ignore[type-arg]
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _read_session_start() -> datetime | None:
    if not _CC_SESSION_FILE.exists():
        return None
    try:
        return datetime.fromisoformat(_CC_SESSION_FILE.read_text().strip())
    except ValueError:
        return None


def _clear_session_start() -> None:
    _CC_SESSION_FILE.unlink(missing_ok=True)


def _read_active_project() -> str | None:
    if not _HALYARD_ACTIVE.exists():
        return None
    for line in _HALYARD_ACTIVE.read_text().splitlines():
        if line.startswith("slug="):
            return line[5:]
    return None


def _read_model_from_settings(project_dir: Path) -> str | None:
    for path in [
        project_dir / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.json",
    ]:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                model = data.get("model")
                if model and model_is_known(model):
                    return str(model)
            except Exception:
                continue
    return None
