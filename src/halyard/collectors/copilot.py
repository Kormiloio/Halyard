"""GitHub Copilot (VS Code) session importer.

Discovers and parses detailed session metadata from VS Code's internal
workspace storage.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from halyard.ai_log import AiSession, append_session, find_project_dir
from halyard.git_context import commits_in_window, current_branch, infer_project
from halyard.hub import find_hub

_VSCODE_STORAGE_DIR = Path.home() / "Library/Application Support/Code/User/workspaceStorage"
_IMPORTED_STATE_FILE = Path.home() / ".halyard" / "copilot-imported"


def import_copilot_sessions(
    project_dir: Path | None = None,
    *,
    dry_run: bool = False,
    all_projects: bool = False,
) -> list[AiSession]:
    """Import new Copilot sessions. Returns the sessions that were (or would be) written."""
    if not _VSCODE_STORAGE_DIR.exists():
        return []

    already_imported = _load_imported_state()
    workspaces = discover_workspaces()

    imported: list[AiSession] = []
    new_ids: set[str] = set()

    for ws_id, project_path in workspaces.items():
        # 1. Scoping logic
        target_dir: Path | None = None
        if project_dir is not None:
            # User specifically asked for one project. Skip if this workspace
            # doesn't map to it.
            if not _paths_match(project_path, project_dir):
                continue
            target_dir = project_dir
        else:
            # Auto-resolve target directory (local project or hub)
            target_dir = find_project_dir(start=project_path)
            if target_dir is None:
                target_dir = find_hub()

        if target_dir is None and not all_projects:
            continue

        # 2. Find and parse sessions
        ws_dir = _VSCODE_STORAGE_DIR / ws_id
        chat_dir = ws_dir / "chatSessions"
        if not chat_dir.exists():
            continue

        for session_path in chat_dir.glob("*.jsonl"):
            session_id = session_path.stem
            if session_id in already_imported:
                continue

            session = parse_chat_session(session_path)
            if not session:
                continue

            session.session_id = session_id

            # Enrich with edit metadata if present
            edit_state = ws_dir / "chatEditingSessions" / session_id / "state.json"
            if edit_state.exists():
                session.files_touched_count = parse_editing_session(edit_state)

            # Attribution
            session.project = infer_project(project_path)
            session.branch = current_branch(project_path)
            session.commit_count = commits_in_window(project_path, session.start, session.end)
            session.outcome_data_available = (
                session.branch is not None or session.commit_count is not None
            )

            if not dry_run and target_dir is not None:
                append_session(target_dir, session)

            imported.append(session)
            new_ids.add(session_id)

    if not dry_run and new_ids:
        _save_imported_state(already_imported | new_ids)

    return imported


def _paths_match(p1: Path, p2: Path) -> bool:
    try:
        return p1.resolve() == p2.resolve()
    except (OSError, ValueError):
        return p1 == p2


def discover_workspaces() -> dict[str, Path]:
    """Map VS Code storage IDs to absolute project paths."""
    mapping: dict[str, Path] = {}
    for folder in _VSCODE_STORAGE_DIR.iterdir():
        if not folder.is_dir():
            continue

        meta = folder / "workspace.json"
        if not meta.exists():
            continue

        try:
            data = json.loads(meta.read_text())
            folder_uri = data.get("folder")
            if folder_uri and folder_uri.startswith("file://"):
                mapping[folder.name] = Path(unquote(urlparse(folder_uri).path))
        except (json.JSONDecodeError, OSError):
            continue

    return mapping


def parse_chat_session(path: Path) -> AiSession | None:
    """Extract metadata from a VS Code chatSession JSONL."""
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    output_tokens = 0
    user_count = 0
    assistant_count = 0
    tool_calls = 0

    try:
        if path.stat().st_size > 50 * 1024 * 1024:  # 50MB safety cap
            return None

        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    kind = event.get("kind")
                    val = event.get("v")
                    key_path = event.get("k", [])

                    # 1. Start time (from session creation)
                    if kind == 0 and isinstance(val, dict):
                        created = val.get("creationDate")
                        if created:
                            start_dt = datetime.fromtimestamp(created / 1000.0)

                    # 2. Token counts (kind 1 updates to requests[i].completionTokens)
                    if kind == 1 and isinstance(key_path, list):
                        if "completionTokens" in key_path:
                            output_tokens += int(val or 0)
                        if "elapsedMs" in key_path:
                            # Use last elapsed update to push end time forward
                            # but we usually have turn timestamps which are better.
                            pass

                    # 3. Interactions (from requests array in kind 0 or kind 2)
                    requests = []
                    if kind == 0 and isinstance(val, dict):
                        requests = val.get("requests", [])
                    elif kind == 2 and key_path == ["requests"]:
                        requests = val if isinstance(val, list) else []

                    for req in requests:
                        if not isinstance(req, dict):
                            continue
                        user_count += 1
                        ts = req.get("timestamp")
                        if ts:
                            dt = datetime.fromtimestamp(ts / 1000.0)
                            if start_dt is None or dt < start_dt:
                                start_dt = dt
                            if end_dt is None or dt > end_dt:
                                end_dt = dt

                        # Assistant messages and tool calls are in the response array
                        response = req.get("response", [])
                        if isinstance(response, list):
                            for part in response:
                                if not isinstance(part, dict):
                                    continue
                                if part.get("kind") in ("message", "thinking"):
                                    assistant_count += 1
                                if part.get("kind") == "toolInvocationSerialized":
                                    tool_calls += 1

                except json.JSONDecodeError:
                    continue
    except OSError:
        return None

    if not start_dt:
        return None
    if not end_dt:
        end_dt = start_dt + timedelta(minutes=1)

    # Skip 0-work sessions
    if assistant_count == 0 and tool_calls == 0:
        return None

    return AiSession(
        start=start_dt,
        end=end_dt,
        tool="github-copilot",
        model="github-copilot",
        input_tokens=0,
        output_tokens=output_tokens,
        cost_usd=0.0,
        tokens_available=output_tokens > 0,
        interaction_count=user_count + assistant_count,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        prompt_count=user_count,
        tool_calls=tool_calls if tool_calls else None,
        interaction_data_available=True,
        telemetry_source="copilot-jsonl",
        telemetry_trust="observed",
    )


def parse_editing_session(path: Path) -> int:
    """Count files touched in an editing session."""
    try:
        data = json.loads(path.read_text())
        files = data.get("initialFileContents", [])
        if isinstance(files, list):
            # Each entry is [uri, hash]
            return len({f[0] for f in files if isinstance(f, list) and f})
    except (json.JSONDecodeError, OSError):
        pass
    return 0


def _load_imported_state() -> set[str]:
    if not _IMPORTED_STATE_FILE.exists():
        return set()
    return {line.strip() for line in _IMPORTED_STATE_FILE.read_text().splitlines() if line.strip()}


def _save_imported_state(ids: set[str]) -> None:
    _IMPORTED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _IMPORTED_STATE_FILE.write_text("\n".join(sorted(ids)) + "\n")


def _parse_iso(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def copilot_history_present() -> bool:
    """True if GitHub Copilot chat session files exist on disk."""
    if not _VSCODE_STORAGE_DIR.exists():
        return False
    # Check if any workspace has a chatSessions directory with files
    for folder in _VSCODE_STORAGE_DIR.iterdir():
        if (
            folder.is_dir()
            and (folder / "chatSessions").exists()
            and any((folder / "chatSessions").glob("*.jsonl"))
        ):
            return True
    return False


def copilot_imported_any() -> bool:
    """True if any Copilot sessions have been imported already."""
    return _IMPORTED_STATE_FILE.exists() and bool(_IMPORTED_STATE_FILE.read_text().strip())
