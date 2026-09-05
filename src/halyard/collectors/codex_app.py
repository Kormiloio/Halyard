"""Codex Desktop session importer.

Reads JSONL session files from ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl,
extracts token usage and timing, and appends records to the Halyard project's
ai-sessions.log.

State is maintained in ~/.halyard/codex-imported (one session UUID per line)
so repeated runs don't duplicate entries.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession, append_session, find_project_dir
from halyard.collectors import normalise_input
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
    newly_imported: dict[str, int] = {}

    for path in session_files:
        session_id = _extract_uuid(path)
        if session_id is None:
            continue

        # v5.2: re-import a session whose rollout file has grown since the last
        # import. The old importer skipped any UUID it had seen once, which
        # froze sessions captured mid-write at a partial snapshot. Skip only
        # when the UUID is known and its recorded size matches the file now; a
        # grown file, an unknown UUID, or a legacy size-less entry re-imports.
        current_size = _file_size(path)
        if session_id in already_imported:
            prior_size = already_imported[session_id]
            if prior_size is not None and prior_size == current_size:
                continue

        # v5.16/B08: one malformed rollout must skip-and-continue, never abort
        # the batch (which would silently drop every later session). The parser
        # honours its own contract, but a defence-in-depth guard ensures a novel
        # coercion error in a single file can't take down the whole import.
        try:
            parsed = _parse_session_file(path)
        except (OSError, ValueError, TypeError, OverflowError):
            continue
        if parsed is None:
            continue

        session, cwd = parsed
        # Tag the row so redundant re-imports of a growing session collapse to
        # one canonical row at read time (see ai_log.collapse_gemini_sessions).
        session.job_id = f"codex:{session_id}"

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
        newly_imported[session_id] = current_size

    if not dry_run and newly_imported:
        # Prune ids whose rollout file no longer exists: codex rotates old
        # rollouts away, so a missing file can never be re-imported. This
        # bounds the dedup state to the rollouts actually on disk instead
        # of growing forever. Carry forward the recorded size for unchanged
        # sessions; update it for the ones (re)imported this run.
        present_ids = {
            uuid for uuid in (_extract_uuid(p) for p in session_files) if uuid is not None
        }
        updated: dict[str, int | None] = {
            uuid: size for uuid, size in already_imported.items() if uuid in present_ids
        }
        updated.update(newly_imported)
        _save_imported_state(updated)

    return imported


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------


# .jsonl rollouts are streamed line by line, so memory is bounded by the
# longest line, not the file. Anything past _MAX_ROLLOUT_LINE_BYTES is treated
# as corrupt/hostile and skipped.
_MAX_ROLLOUT_LINE_BYTES = 16 * 1024 * 1024  # 16 MiB per line
# Total budget for a single parse. Generous so the importer can fully read a
# long session: real Codex rollouts reach hundreds of MB of inline tool output
# (813 MB observed). This mirrors gemini_history._DEFAULT_ROLLOUT_BYTES, which
# was widened for the same reason.
_MAX_ROLLOUT_BYTES = 1024 * 1024 * 1024  # 1 GiB


def _iter_jsonl_lines(path: Path) -> Iterator[str]:
    """Yield lines from a rollout file without loading it all into memory.

    Bounded untrusted read: reject symlinks, skip any single line over
    ``_MAX_ROLLOUT_LINE_BYTES``, and abandon the file once cumulative bytes
    pass ``_MAX_ROLLOUT_BYTES``.

    v5.32: the bound used to be a 25 MB *whole-file* cap, which silently
    yielded nothing for anything larger. Because the read is a streaming
    generator, that cap never bounded memory — only how large a session was
    allowed to be before it became permanently uncapturable. Long agentic
    Codex sessions blow past 25 MB routinely (one observed rollout was
    813 MB of inline tool output), so the cap silently dropped exactly the
    sessions that matter most for token accounting, and no amount of
    re-running the importer could recover them. Memory is bounded by the
    longest line, so the per-line cap is the bound that was actually
    wanted — the same shape ``gemini_history`` already uses, which was
    widened for the same reason after an observed 825 MB rollout.
    """
    try:
        if os.path.islink(path):
            return
        seen = 0
        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                seen += len(raw.encode("utf-8", errors="ignore"))
                if seen > _MAX_ROLLOUT_BYTES:
                    _note_truncated(path, seen)
                    return
                if len(raw) > _MAX_ROLLOUT_LINE_BYTES:
                    continue  # pathological/corrupt line — skip, keep going
                yield raw
    except OSError:
        return


def _note_truncated(path: Path, seen: int) -> None:
    """Record that a rollout was abandoned part-way through.

    v5.32: the previous whole-file cap dropped oversized rollouts in
    silence — no log line, no doctor signal — so a user whose largest
    session stopped being captured had no way to find out, and `halyard
    doctor` went on advising `halyard import-codex`, a command that could
    not fix it. Losing data quietly is worse than losing it loudly.
    """
    from halyard.ai_log import _log_error

    _log_error(
        f"codex importer: rollout {path.name} exceeded the "
        f"{_MAX_ROLLOUT_BYTES} byte budget after {seen} bytes — "
        "session captured only up to that point",
        RuntimeError("rollout budget exceeded"),
    )


def _parse_session_file(path: Path) -> tuple[AiSession, str | None] | None:
    """Parse one rollout JSONL file. Returns (AiSession, cwd) or None to skip."""
    session_start: datetime | None = None
    session_end: datetime | None = None
    cwd: str | None = None
    model: str = "codex"
    last_token_usage: dict | None = None  # type: ignore[type-arg]
    user_message_count = 0
    assistant_message_count = 0
    tool_calls = 0
    tool_errors = 0
    rejections = 0

    for raw in _iter_jsonl_lines(path):
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
                # v3.3: detect rejection marker in agent messages (e.g. from an observer)
                if "user doesn't want to proceed" in str(payload.get("message", "")).lower():
                    rejections += 1
            elif msg_type in {"exec_command_begin", "apply_patch_begin", "tool_call_begin"}:
                tool_calls += 1
            elif msg_type in {"exec_command_end", "apply_patch_end", "tool_call_end"}:
                if _payload_failed(payload):
                    tool_errors += 1
                    # v3.3: distinguish explicit user rejection from tool failure
                    out_agg = str(payload.get("aggregated_output", ""))
                    out_std = str(payload.get("stdout", ""))
                    if "user doesn't want to proceed" in (out_agg or out_std).lower():
                        rejections += 1
            elif msg_type in {"custom_tool_call_output", "function_call_output"}:
                # v3.3: detect rejection marker in tool outputs
                if "user doesn't want to proceed" in str(payload.get("output", "")).lower():
                    rejections += 1

    if session_start is None or session_end is None:
        return None

    # Extract token counts from last cumulative snapshot.
    # Newer o-series Codex sessions report total_tokens only (input/output = 0).
    total_input = 0
    cached_input = 0
    output_tokens = 0
    total_tokens = 0

    if last_token_usage:
        # v5.16/B08: token fields in an attacker-stageable rollout are not
        # guaranteed numeric (e.g. total_token_usage:{"output_tokens":"x"}); a
        # bare int() would raise ValueError and abort the whole import batch.
        total_input = _safe_int(last_token_usage.get("input_tokens"))
        cached_input = _safe_int(last_token_usage.get("cached_input_tokens"))
        output_tokens = _safe_int(last_token_usage.get("output_tokens"))
        total_tokens = _safe_int(last_token_usage.get("total_tokens"))

    # Skip sessions with no real work.
    if output_tokens == 0 and total_tokens == 0:
        return None

    # o-series fallback: use total_tokens as net_input proxy, mark breakdown unavailable.
    tokens_available = output_tokens > 0
    if tokens_available:
        # Codex reports gross input (cached subset included).
        net_input = normalise_input(total_input, cached_input, 0, cache_inclusive=True)
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
        tool_errors=tool_errors if tool_calls else None,
        rejected_suggestion_count=rejections if (tool_calls or rejections) else None,
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


def _load_imported_state() -> dict[str, int | None]:
    """Map each imported rollout UUID to the file size recorded at import.

    Lines are ``"<uuid>\\t<size>"`` (v5.2). Legacy bare-UUID lines parse to
    ``None``, which forces a one-time re-check so any session frozen mid-write
    under the old importer gets backfilled.
    """
    if not _IMPORTED_STATE_FILE.exists():
        return {}
    state: dict[str, int | None] = {}
    for raw in _IMPORTED_STATE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        uuid, _, size_str = line.partition("\t")
        uuid = uuid.strip()
        if not uuid:
            continue
        try:
            state[uuid] = int(size_str) if size_str else None
        except ValueError:
            state[uuid] = None
    return state


def _save_imported_state(state: dict[str, int | None]) -> None:
    _IMPORTED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{uuid}\t{size}" if size is not None else uuid for uuid, size in sorted(state.items())
    ]
    _IMPORTED_STATE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _file_size(path: Path) -> int:
    """Current byte size of ``path``, or -1 if it can't be stat'd."""
    try:
        return path.stat().st_size
    except OSError:
        return -1


def codex_history_present() -> bool:
    """True if Codex Desktop has on-disk session rollouts available to import.

    Recomputes the path from ``Path.home()`` (not the import-time
    constant) so it stays correct under a relocated home in tests.
    Read-only: never imports or mutates anything.
    """
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.exists():
        return False
    return next(sessions_dir.rglob("rollout-*.jsonl"), None) is not None


def codex_imported_any() -> bool:
    """True if at least one Codex session has already been imported."""
    state = Path.home() / ".halyard" / "codex-imported"
    if not state.exists():
        return False
    try:
        return any(line.strip() for line in state.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_uuid(path: Path) -> str | None:
    m = _UUID_RE.search(path.name)
    return m.group(1) if m else None


def _safe_int(value: object) -> int:
    """Coerce a token field to int, treating any malformed value as 0.

    v5.16/B08: degrade a non-numeric/out-of-range token field to 0 rather than
    letting int() raise and escape the parser (which documents returning None).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        result: int = int(value)
    except (ValueError, TypeError, OverflowError):
        return 0
    return result


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
