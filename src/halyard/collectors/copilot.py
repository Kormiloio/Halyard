"""GitHub Copilot (VS Code) session importer.

Discovers and parses detailed session metadata from VS Code's internal
workspace storage.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

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
    # v3.12 coexistence: sessions already captured live via the OTel
    # receiver carry job_id=copilot-otel:<id> in the target ledger.
    # Cache the captured-id set per target dir so the importer never
    # double-counts an OTel-sourced session.
    otel_captured: dict[Path, set[str]] = {}

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

        # Authoritative coexistence check: any session already recorded
        # via OTel in the resolved target ledger is skipped (the state
        # file is the fast path; this survives a cleared state file).
        captured = otel_captured.get(target_dir) if target_dir is not None else None
        if target_dir is not None and captured is None:
            captured = _otel_captured_ids(target_dir)
            otel_captured[target_dir] = captured

        for session_path in chat_dir.glob("*.jsonl"):
            session_id = session_path.stem
            if session_id in already_imported:
                continue
            if captured and session_id in captured:
                continue

            # v5.16/B08: one malformed chat session must skip-and-continue,
            # never abort the batch and silently drop every later session.
            try:
                session = parse_chat_session(session_path)
            except (OSError, ValueError, TypeError, OverflowError):
                continue
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
            data = json.loads(meta.read_text(encoding="utf-8"))
            folder_uri = data.get("folder")
            if folder_uri and folder_uri.startswith("file://"):
                # url2pathname handles Windows's file:///C:/... convention
                # (strips the leading slash), where bare Path(unquote(...path))
                # would produce '/C:/...' and break.
                mapping[folder.name] = Path(url2pathname(urlparse(folder_uri).path))
        except (json.JSONDecodeError, OSError):
            continue

    return mapping


def _apply_patch(state: dict[str, Any], key_path: list[Any], value: Any) -> None:
    """Set ``value`` at ``key_path`` within ``state``.

    VS Code chat sessions are an incremental log: a kind-0 snapshot followed by
    kind-1/kind-2 events that each set a value at a nested key path (e.g.
    ``["requests", 0, "response"]``).
    """
    cur: Any = state
    try:
        for key in key_path[:-1]:
            if isinstance(key, int) and isinstance(cur, list):
                # Grow the list so a patch targeting an index beyond the
                # kind-0 snapshot (a request added after the snapshot was
                # taken) materialises instead of being dropped (v5.21).
                while len(cur) <= key:
                    cur.append({})
            cur = cur[key]

        last_key = key_path[-1]
        if isinstance(last_key, int) and isinstance(cur, list):
            while len(cur) <= last_key:
                cur.append({})
        cur[last_key] = value
    except (KeyError, IndexError, TypeError):
        return


def parse_chat_session(path: Path) -> AiSession | None:
    """Extract metadata from a VS Code chatSession JSONL.

    The file is an incremental log: an optional kind-0 snapshot followed by
    kind-1 (scalar) and kind-2 (value) patches targeting a key path ``k``.
    Reconstruct the final state by applying the patches, then count from it.
    Earlier versions read events line-by-line and only handled a kind-2 update
    whose path was exactly ``["requests"]``; current VS Code emits the model
    output via ``["requests", N, "response"]`` sub-path updates, so every recent
    session looked empty and was skipped. Metadata only — no message/response
    content is ever read.
    """
    state: dict[str, Any] = {}
    # Track response parts per request index to handle incremental patches
    # that would otherwise overwrite previous parts in the reconstructed state.
    all_response_parts: dict[int, list[dict[str, Any]]] = {}

    try:
        if path.stat().st_size > 50 * 1024 * 1024:  # 50MB safety cap
            return None
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("kind")
                if kind == 0 and isinstance(event.get("v"), dict):
                    state = event["v"]
                elif kind in (1, 2) and isinstance(event.get("k"), list):
                    key_path = event["k"]
                    val = event.get("v")
                    _apply_patch(state, key_path, val)

                    # Evidence aggregation: if this is a response patch,
                    # keep it even if a later patch overwrites it in 'state'.
                    if (
                        len(key_path) == 3
                        and key_path[0] == "requests"
                        and isinstance(key_path[1], int)
                        and key_path[2] == "response"
                        and isinstance(val, list)
                    ):
                        parts = all_response_parts.setdefault(key_path[1], [])
                        for part in val:
                            if isinstance(part, dict) and part not in parts:
                                parts.append(part)
    except OSError:
        return None

    start_dt: datetime | None = None
    end_dt: datetime | None = None
    output_tokens = 0
    user_count = 0
    assistant_count = 0
    tool_calls = 0

    created = state.get("creationDate")
    if isinstance(created, (int, float)):
        # v5.16/B08: an out-of-range epoch-millis value raises OSError/
        # OverflowError/ValueError from fromtimestamp; treat it as no start.
        start_dt = _safe_fromtimestamp_ms(created)

    requests = state.get("requests")
    req_list = requests if isinstance(requests, list) else []

    # Every patched request index already exists in req_list: _apply_patch
    # grows the list on out-of-bounds indices. Iterating beyond it (an
    # earlier revision padded missing indices with ``{}``) only fabricates
    # phantom user turns — never do that.
    for i, req in enumerate(req_list):
        if not isinstance(req, dict):
            continue
        user_count += 1
        ts = req.get("timestamp")
        if isinstance(ts, (int, float)):
            # v5.16/B08: guard out-of-range epoch-millis (see _safe_fromtimestamp_ms).
            dt = _safe_fromtimestamp_ms(ts)
            if dt is not None:
                if start_dt is None or dt < start_dt:
                    start_dt = dt
                if end_dt is None or dt > end_dt:
                    end_dt = dt
        ct = req.get("completionTokens")
        if isinstance(ct, (int, float)):
            output_tokens += int(ct)

        # Prefer the aggregated response parts: VS Code emits the model
        # output as successive ["requests", N, "response"] patches and a
        # later patch overwrites earlier parts in the reconstructed state.
        response = all_response_parts.get(i) or req.get("response")
        if isinstance(response, list):
            for part in response:
                if not isinstance(part, dict):
                    continue
                part_kind = part.get("kind")
                if part_kind in ("message", "thinking"):
                    assistant_count += 1
                elif part_kind == "toolInvocationSerialized":
                    tool_calls += 1

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
        data = json.loads(path.read_text(encoding="utf-8"))
        files = data.get("initialFileContents", [])
        if isinstance(files, list):
            # Each entry is [uri, hash]
            return len({f[0] for f in files if isinstance(f, list) and f})
    except (json.JSONDecodeError, OSError):
        pass
    return 0


_OTEL_JOB_PREFIX = "copilot-otel:"


def record_otel_capture(session_id: str) -> None:
    """Mark a session id as captured via the OTel receiver (v3.12).

    Adds the id to the shared importer dedup state so the v3.7 importer
    skips it. Read-modify-write so a concurrent importer append is not
    clobbered. Best-effort: a write failure must never break live capture.
    """
    if not session_id:
        return
    try:
        ids = _load_imported_state()
        if session_id in ids:
            return
        _save_imported_state(ids | {session_id})
    except OSError:
        pass


def _otel_captured_ids(target_dir: Path) -> set[str]:
    """Session ids already recorded in ``target_dir`` via the OTel path.

    Reads the ledger and collects the ``session_id`` of any row whose
    ``job_id`` is ``copilot-otel:<id>`` (or whose telemetry source is the
    OTel collector). Bounded by the existing parser; failures yield an
    empty set so the importer degrades to the state-file fast path.
    """
    from halyard.ai_log import AI_LOG_FILENAME, parse_sessions

    if not (target_dir / AI_LOG_FILENAME).exists():
        return set()
    try:
        sessions = parse_sessions(target_dir)
    except (OSError, ValueError):
        return set()
    captured: set[str] = set()
    for s in sessions:
        if s.telemetry_source == "copilot-otel" and s.session_id:
            captured.add(s.session_id)
        elif s.job_id and s.job_id.startswith(_OTEL_JOB_PREFIX):
            captured.add(s.job_id[len(_OTEL_JOB_PREFIX) :])
    return captured


def _load_imported_state() -> set[str]:
    if not _IMPORTED_STATE_FILE.exists():
        return set()
    return {
        line.strip()
        for line in _IMPORTED_STATE_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _save_imported_state(ids: set[str]) -> None:
    _IMPORTED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _IMPORTED_STATE_FILE.write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8")


def _safe_fromtimestamp_ms(ms: int | float) -> datetime | None:
    """Convert epoch-milliseconds to a local datetime, or None if out of range.

    v5.16/B08: ``datetime.fromtimestamp`` raises OSError/OverflowError/ValueError
    for values outside the platform's representable range (a crafted
    ``creationDate``/``timestamp`` in an attacker-stageable chat session). Returning
    None keeps the parser honouring its "skip on any error" contract instead of
    letting one bad file abort the whole import.
    """
    try:
        return datetime.fromtimestamp(ms / 1000.0)
    except (OSError, OverflowError, ValueError):
        return None


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
    return _IMPORTED_STATE_FILE.exists() and bool(
        _IMPORTED_STATE_FILE.read_text(encoding="utf-8").strip()
    )
