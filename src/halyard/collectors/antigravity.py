"""Antigravity (Google) transcript collector.

Two entry points, both reading the same per-conversation JSONL transcript:

  Stop / PostInvocation hook  →  handle_stop_hook()   (halyard ag-hook)
  halyard import-antigravity  →  import_antigravity_sessions()

Antigravity also keeps a ``conversations/<cascade-id>.db`` SQLite store, but
every payload column in it is undocumented binary protobuf, so it is
deliberately not read (see openspec/changes/v5.24-antigravity-collector).

Spend quarantine: Antigravity reports no tokens, no model id, and no cost
anywhere — the hook payload's ``modelName`` is literally ``"auto"``. Rows
are therefore written with zero tokens, zero cost, ``tokens_available=false``
and ``billing=credits``, which excludes them from every spend aggregate
(``usage.sum_spend`` skips rows where ``billing != "api"`` or
``cost_usd <= 0``). Time still counts; spend does not.

Privacy: only ``created_at``/``type``/``source``/``status`` are read. The
``content`` and ``thinking`` fields are never touched (non-negotiable 5).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
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
from halyard.collectors import iter_bounded_lines, session_has_evidence, session_is_implausible
from halyard.git_context import commits_in_window, current_branch, infer_project
from halyard.hub import find_hub

_ANTIGRAVITY_DIR = Path.home() / ".gemini" / "antigravity"
_BRAIN_DIR = _ANTIGRAVITY_DIR / "brain"
_TRANSCRIPT_REL = Path(".system_generated") / "logs" / "transcript.jsonl"
_IMPORTED_STATE_FILE = Path.home() / ".halyard" / "antigravity-imported"
# Hook-recorded conversation_id → workspace path. The transcript itself
# carries no workspace reference, and its content is off-limits, so the
# importer can only attribute conversations the hook has seen.
_WORKSPACE_STATE_DIR = Path.home() / ".halyard" / "ag-sessions"

_JOB_PREFIX = "antigravity:"

# conversation_id arrives from untrusted hook stdin and is used to build
# state-file paths. Same guard as windsurf.py (v5.16/B07).
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")

_MAX_TRANSCRIPT_BYTES = 50 * 1024 * 1024

# Observed transcript ``type`` values (v5.24 spike, 355-record sample).
_TOOL_TYPES = frozenset(
    {"RUN_COMMAND", "VIEW_FILE", "CODE_ACTION", "LIST_DIRECTORY", "GREP_SEARCH"}
)
_USER_TYPE = "USER_INPUT"
_ERROR_TYPE = "ERROR_MESSAGE"
_MODEL_SOURCE = "MODEL"


def _safe_state_path(conversation_id: str, state_dir: Path, suffix: str) -> Path | None:
    """Map an untrusted conversation_id to a path strictly inside ``state_dir``."""
    if not conversation_id or conversation_id in {".", ".."}:
        return None
    if not _SAFE_ID.match(conversation_id):
        return None
    path = state_dir / f"{conversation_id}{suffix}"
    try:
        resolved = path.resolve()
        root = state_dir.resolve()
    except OSError:
        return None
    if resolved.parent != root:
        return None
    return path


def _parse_iso_utc(ts: str) -> datetime | None:
    """Parse an Antigravity ``created_at`` into a naive *local* datetime.

    Transcript timestamps are ISO-8601 UTC with a ``Z`` suffix
    (``2026-08-09T18:58:04Z``) while the ledger writes local time. Failing to
    convert shifts every Antigravity session by the UTC offset.
    """
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    return dt


def _normalize_model(raw: Any) -> str:
    """Antigravity reports ``modelName`` as ``"auto"``; never a real model id."""
    if not isinstance(raw, str) or not raw.strip():
        return "antigravity-unknown"
    name = raw.strip()
    if name == "auto":
        return "antigravity-auto"
    return name


def transcript_path_for(conversation_id: str) -> Path:
    """Canonical transcript location for a conversation id."""
    return _BRAIN_DIR / conversation_id / _TRANSCRIPT_REL


def discover_transcripts() -> dict[str, Path]:
    """Map conversation id → transcript path for every conversation on disk."""
    found: dict[str, Path] = {}
    if not _BRAIN_DIR.exists():
        return found
    try:
        entries = sorted(_BRAIN_DIR.iterdir())
    except OSError:
        return found
    for conv_dir in entries:
        if not conv_dir.is_dir():
            continue
        transcript = conv_dir / _TRANSCRIPT_REL
        if transcript.exists():
            found[conv_dir.name] = transcript
    return found


def parse_transcript(path: Path) -> AiSession | None:
    """Build an AiSession from an Antigravity transcript.

    Metadata only: ``created_at``, ``type``, ``source``, ``status``. The
    ``content`` and ``thinking`` fields are never read.
    """
    # v5.34: a whole-file size rejection lived here. The transcript is
    # streamed below, so it bounded nothing but the session size and
    # dropped the largest ones in silence. Bounds now live in
    # iter_bounded_lines (longest line + total parse budget).
    first: datetime | None = None
    last: datetime | None = None
    records = 0
    user_count = 0
    model_count = 0
    tool_calls = 0
    tool_errors = 0

    try:
        for raw_line in iter_bounded_lines(path, label="antigravity transcript"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue

            records += 1
            stamp = _parse_iso_utc(record.get("created_at", ""))
            if stamp is not None:
                if first is None or stamp < first:
                    first = stamp
                if last is None or stamp > last:
                    last = stamp

            rec_type = record.get("type")
            if rec_type == _USER_TYPE:
                user_count += 1
            elif rec_type in _TOOL_TYPES:
                tool_calls += 1

            exit_code = record.get("exit_code")
            if (
                rec_type == _ERROR_TYPE
                or record.get("error")
                or (isinstance(exit_code, int) and exit_code != 0)
            ):
                tool_errors += 1

            if record.get("source") == _MODEL_SOURCE:
                model_count += 1
    except OSError:
        return None

    if first is None or last is None or records == 0:
        return None

    return AiSession(
        start=first,
        end=last,
        tool="antigravity",
        model="antigravity-unknown",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        tokens_available=False,
        billing="credits",
        wall_seconds=max(0, int((last - first).total_seconds())),
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        interaction_count=records,
        user_message_count=user_count,
        assistant_message_count=model_count,
        prompt_count=user_count,
        interaction_data_available=True,
        telemetry_source="antigravity-transcript",
        telemetry_trust="inferred",
    )


def _record_workspace(conversation_id: str, workspace: str) -> None:
    """Remember which workspace a conversation belongs to (hook path only)."""
    path = _safe_state_path(conversation_id, _WORKSPACE_STATE_DIR, ".json")
    if path is None:
        return
    _WORKSPACE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps({"workspace": workspace}), encoding="utf-8")
    except OSError:
        return


def _read_workspace(conversation_id: str) -> Path | None:
    path = _safe_state_path(conversation_id, _WORKSPACE_STATE_DIR, ".json")
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    workspace = data.get("workspace") if isinstance(data, dict) else None
    return Path(workspace) if isinstance(workspace, str) and workspace else None


def _attribute(session: AiSession, workspace: Path | None) -> None:
    """Attach project/branch/commit metadata when a workspace is known."""
    if workspace is None:
        return
    session.project = infer_project(workspace)
    session.attr_method = "git"
    session.branch = current_branch(workspace)
    session.commit_count = commits_in_window(workspace, session.start, session.end)
    session.outcome_data_available = session.branch is not None or session.commit_count is not None


def import_antigravity_sessions(
    project_dir: Path | None = None,
    *,
    dry_run: bool = False,
    all_projects: bool = False,
) -> list[AiSession]:
    """Import new or grown Antigravity conversations."""
    transcripts = discover_transcripts()
    if not transcripts:
        return []

    already = _load_imported_state()
    present_ids = set(transcripts)
    imported: list[AiSession] = []
    newly: dict[str, int] = {}

    for conversation_id, transcript in transcripts.items():
        current_size = _transcript_size(transcript)
        prior = already.get(conversation_id)
        if prior is not None and prior == current_size:
            continue

        workspace = _read_workspace(conversation_id)

        target_dir: Path | None
        if project_dir is not None:
            if workspace is None or not _paths_match(workspace, project_dir):
                continue
            target_dir = project_dir
        else:
            start = workspace or Path.cwd()
            target_dir = find_project_dir(start=start) or find_hub()

        if target_dir is None and not all_projects:
            continue

        # One malformed transcript must skip-and-continue, never abort the
        # batch and silently drop every later conversation (v5.16/B08).
        try:
            session = parse_transcript(transcript)
        except (OSError, ValueError, TypeError, OverflowError):
            continue
        if session is None:
            continue
        if not session_has_evidence(session) or session_is_implausible(session):
            continue

        session.session_id = conversation_id
        session.job_id = f"{_JOB_PREFIX}{conversation_id}"
        _attribute(session, workspace)

        if not dry_run and target_dir is not None:
            append_session(target_dir, session)

        imported.append(session)
        newly[conversation_id] = current_size

    if not dry_run and newly:
        updated: dict[str, int | None] = {
            cid: size for cid, size in already.items() if cid in present_ids
        }
        updated.update(newly)
        _save_imported_state(updated)

    return imported


def handle_stop_hook(payload: dict[str, Any]) -> int:
    """Record a finished Antigravity turn (Stop / PostInvocation hook).

    Hooks block the agent loop synchronously, so this stays an append.
    """
    conversation_id = payload.get("conversationId")
    if not isinstance(conversation_id, str) or not _SAFE_ID.match(conversation_id):
        return 0

    workspaces = payload.get("workspacePaths")
    workspace: Path | None = None
    if isinstance(workspaces, list) and workspaces:
        first = workspaces[0]
        if isinstance(first, str) and first:
            workspace = Path(first)
            _record_workspace(conversation_id, first)

    # Prefer the payload's transcriptPath: the documented layout and the
    # observed one disagree, so never rely on a hardcoded path.
    raw_path = payload.get("transcriptPath")
    transcript: Path | None = None
    if isinstance(raw_path, str) and raw_path:
        candidate = Path(raw_path)
        if candidate.exists():
            transcript = candidate
    if transcript is None:
        candidate = transcript_path_for(conversation_id)
        if candidate.exists():
            transcript = candidate
    if transcript is None:
        return 0

    try:
        session = parse_transcript(transcript)
    except (OSError, ValueError, TypeError, OverflowError):
        return 0
    if session is None:
        return 0

    session.model = _normalize_model(payload.get("modelName"))
    session.session_id = conversation_id
    session.job_id = f"{_JOB_PREFIX}{conversation_id}"
    session.client_surface = "ide"

    if not session_has_evidence(session) or session_is_implausible(session):
        return 0

    active = read_active_project()
    _attribute(session, workspace)
    if active:
        session.project = active
        session.attr_method = "timer"

    start_dir = workspace or Path.cwd()
    target_dir = find_project_dir(start=start_dir) or find_hub()
    if target_dir and (target_dir / AI_LOG_FILENAME).exists():
        append_session(target_dir, session)
        maybe_emit_milestones(target_dir)
        maybe_show_dashboard_hint()
    else:
        write_unattributed_session(session)
    return 0


def _paths_match(p1: Path, p2: Path) -> bool:
    try:
        return p1.resolve() == p2.resolve()
    except (OSError, ValueError):
        return p1 == p2


def _transcript_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def _load_imported_state() -> dict[str, int | None]:
    """Map conversation id → transcript size recorded at import (codex v5.2 format)."""
    if not _IMPORTED_STATE_FILE.exists():
        return {}
    try:
        text = _IMPORTED_STATE_FILE.read_text(encoding="utf-8")
    except OSError:
        return {}
    state: dict[str, int | None] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        cid, _, size_str = line.partition("\t")
        cid = cid.strip()
        if not cid:
            continue
        try:
            state[cid] = int(size_str) if size_str else None
        except ValueError:
            state[cid] = None
    return state


def _save_imported_state(state: dict[str, int | None]) -> None:
    _IMPORTED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{cid}\t{size}" if size is not None else cid for cid, size in sorted(state.items())]
    _IMPORTED_STATE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def antigravity_present() -> bool:
    """True if Antigravity is installed on this machine."""
    return _ANTIGRAVITY_DIR.exists()


def antigravity_history_present() -> bool:
    """True if any Antigravity transcript exists on disk."""
    return bool(discover_transcripts())


def antigravity_imported_any() -> bool:
    """True if any Antigravity conversation has been imported already."""
    if not _IMPORTED_STATE_FILE.exists():
        return False
    try:
        return bool(_IMPORTED_STATE_FILE.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def latest_transcript_mtime() -> float | None:
    """Newest transcript mtime, for doctor's lagging-capture check."""
    newest: float | None = None
    for path in discover_transcripts().values():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def read_payload() -> dict[str, Any]:
    """Read the JSON hook payload from stdin."""
    if sys.stdin.isatty():
        return {}
    try:
        return cast(dict[str, Any], json.loads(sys.stdin.read()))
    except (json.JSONDecodeError, EOFError, ValueError):
        return {}
