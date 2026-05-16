"""Claude Code hook collector.

Two entry points, wired up by `halyard install-hook`:

  UserPromptSubmit  →  record_session_start()  (halyard cc-session)
  Stop              →  handle_stop_hook()       (halyard cc-hook)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    find_project_dir,
    maybe_show_dashboard_hint,
    read_active_project,
    write_unattributed_session,
)
from halyard.collectors import session_has_evidence, session_is_implausible
from halyard.git_context import (
    commits_in_window,
    current_branch,
    current_remote,
    head_sha,
    infer_project,
    numstat_delta,
)
from halyard.hub import find_hub
from halyard.pricing import calculate_cost, model_is_known

_CC_SESSION_FILE = Path.home() / ".halyard" / "cc-session"


def record_session_start() -> int:
    """Called by UserPromptSubmit hook. Records start timestamp once per session."""
    if _CC_SESSION_FILE.exists():
        return 0  # already tracking this session — budget already checked

    # Budget check fires once per session, before the session file is written
    active = read_active_project()
    if active:
        cwd = Path.cwd()
        project_dir = find_project_dir(start=cwd) or find_hub()
        if project_dir:
            from halyard.budget import check_budget

            warning = check_budget(active, project_dir)
            if warning:
                print(warning)  # budget warning: hooks write to stdout for tool pickup

    cwd = Path.cwd()
    _CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "start": datetime.now().isoformat(timespec="seconds"),
        "sha_at_start": head_sha(cwd),
    }
    _CC_SESSION_FILE.write_text(json.dumps(state))

    # Auto human timer — close stale window, then open/refresh for this session
    try:
        from halyard.auto_timer import auto_timer_activity, auto_timer_close_if_stale

        auto_timer_close_if_stale()
        at_project_dir = find_project_dir(start=cwd) or find_hub()
        if at_project_dir and (at_project_dir / "time.timeclock").exists():
            at_project = read_active_project() or infer_project(cwd) or "unattributed"
            auto_timer_activity(at_project, at_project_dir / "time.timeclock")
    except Exception:  # auto-timer must never crash a hook
        pass

    # Late-night easter egg — fires once per session start between midnight and 5am
    try:
        from halyard.easter_eggs import is_late_night, late_night_message

        if is_late_night():
            print(f"[halyard] {late_night_message()}", file=sys.stderr)
    except Exception:  # easter eggs must never crash a hook
        pass

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
    session_state = _read_session_state()
    start = session_state.get("start_dt") or now
    sha_at_start: str | None = session_state.get("sha")
    _clear_session_start()

    # Try usage from payload first (older Claude Code format)
    usage = payload.get("usage") or payload.get("message", {}).get("usage", {}) or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    cache_read = int(usage.get("cache_read_input_tokens", 0) or usage.get("cache_read", 0))
    cache_write = int(usage.get("cache_creation_input_tokens", 0) or usage.get("cache_write", 0))

    model = (
        payload.get("model")
        or payload.get("stop_model")
        or (_read_model_from_settings(project_dir) if project_dir else None)
    )

    branch = current_branch(cwd)
    assistant_message_count: int | None = None
    interaction_count: int | None = None

    # Fallback: read model + tokens from transcript (Claude Code ≥2.x format)
    if not (input_tokens or output_tokens):
        transcript_path = payload.get("transcript_path", "")
        if transcript_path:
            t_model, t_in, t_out, t_cr, t_cw, t_branch, t_assistant_count = _read_from_transcript(
                transcript_path, since=start
            )
            if t_in or t_out:
                input_tokens, output_tokens = t_in, t_out
                cache_read, cache_write = t_cr, t_cw
            if t_assistant_count:
                assistant_message_count = t_assistant_count
                interaction_count = t_assistant_count
            if not model and t_model:
                model = t_model
            if not branch and t_branch:
                branch = t_branch

    if not model:
        model = "claude-unknown"

    tokens_available = input_tokens > 0 or output_tokens > 0
    cost = calculate_cost(model, input_tokens, output_tokens, cache_read, cache_write)

    # v2.24: commit count and code delta
    commit_count = commits_in_window(cwd, start, now)
    code_added: int | None = None
    code_removed: int | None = None
    if sha_at_start:
        delta = numstat_delta(cwd, sha_at_start)
        if delta is not None:
            code_added, code_removed = delta

    # D-1: resolve attribution source so provenance is recorded in the log.
    _active = read_active_project()
    _project: str | None
    _attr_method: str | None
    _extra_tags: list[str]
    if _active:
        _project = _active
        _attr_method = "timer"
        _extra_tags = []
    else:
        _project = infer_project(cwd)
        _attr_method = "git" if _project else None
        _extra_tags = ["attribution:inferred"] if _project else []

    _remote = current_remote(cwd)

    session = AiSession(
        start=start,
        end=now,
        tool="claude-code",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        project=_project,
        cache_read=cache_read or None,
        cache_write=cache_write or None,
        tokens_available=tokens_available,
        source="hook",
        attr_method=_attr_method,
        tags=_extra_tags,
        branch=branch,
        remote=_remote,
        commit_count=commit_count,
        code_added=code_added,
        code_removed=code_removed,
        interaction_count=interaction_count,
        assistant_message_count=assistant_message_count,
        interaction_data_available=assistant_message_count is not None,
        telemetry_source="claude-code-transcript"
        if assistant_message_count is not None
        else "claude-code-hook",
        telemetry_trust="observed",
    )

    # A Stop fire with no evidence of a real turn (transcript/token
    # resolution failed AND no interactions/tools/code/real model) is
    # not a session — don't write a claude-unknown 0/0 $0 stub.
    if not session_has_evidence(session) or session_is_implausible(session):
        return 0

    if can_append_project_log and project_dir is not None:
        append_session(project_dir, session)
    else:
        path = write_unattributed_session(session)
        # stderr: hooks communicate back to the tool via stderr, not stdout
        print(
            f"[halyard] session saved to {path} — run 'halyard adopt' in this directory.",
            file=sys.stderr,
        )

    # Auto human timer — keep last_activity fresh on every stop
    try:
        from halyard.auto_timer import auto_timer_update_activity

        auto_timer_update_activity()
    except Exception:  # auto-timer must never crash a hook
        pass

    maybe_show_dashboard_hint()
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


def _read_session_state() -> dict[str, Any]:
    """Return {"start_dt": datetime, "sha": str|None} from the session file.

    Handles both the new JSON format (v2.24+) and the legacy plain ISO timestamp
    written by older versions of the collector.
    """
    if not _CC_SESSION_FILE.exists():
        return {}
    raw = _CC_SESSION_FILE.read_text().strip()
    try:
        data = json.loads(raw)
        start_dt: datetime | None = None
        raw_start = data.get("start", "")
        with suppress(ValueError, TypeError):
            if raw_start.endswith("Z"):
                # Legacy UTC timestamp — convert to local naive for consistency
                start_dt = (
                    datetime.fromisoformat(raw_start[:-1])
                    .replace(tzinfo=UTC)
                    .astimezone(tz=None)
                    .replace(tzinfo=None)
                )
            elif raw_start:
                # Current format: plain local ISO string
                start_dt = datetime.fromisoformat(raw_start)
        return {"start_dt": start_dt, "sha": data.get("sha_at_start")}
    except (json.JSONDecodeError, ValueError):
        # Legacy format: plain ISO timestamp string
        with suppress(ValueError):
            return {"start_dt": datetime.fromisoformat(raw), "sha": None}
        return {}


def _clear_session_start() -> None:
    _CC_SESSION_FILE.unlink(missing_ok=True)


_MAX_TRANSCRIPT_BYTES = 25 * 1024 * 1024  # 25 MB


def _transcript_roots() -> list[Path]:
    """Directories a legitimate transcript may live under.

    Claude Code writes transcripts under the user's home (~/.claude/...);
    tests and some setups use the system temp dir or the project tree.
    Restricting to these blocks /etc, /proc, /sys, /dev, and other users'
    files while not breaking any real layout.
    """
    roots = [Path.home(), Path(tempfile.gettempdir())]
    with suppress(OSError):
        roots.append(Path.cwd())
    out: list[Path] = []
    for r in roots:
        with suppress(OSError):
            out.append(r.resolve())
    return out


def _safe_transcript_path(raw: str) -> Path | None:
    """Validate an untrusted Stop-hook ``transcript_path``.

    The Stop payload is attacker-influenceable (a hostile process can pipe
    a crafted payload to ``halyard cc-hook``). Only accept a real,
    non-symlink, size-bounded file under an allowlisted root. Anything
    else returns None and transcript enrichment is skipped.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        if os.path.islink(os.path.expanduser(raw)):
            return None
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            return None
        if not any(root == path or root in path.parents for root in _transcript_roots()):
            return None
        if path.stat().st_size > _MAX_TRANSCRIPT_BYTES:
            return None
    except OSError:
        return None
    return path


def _read_from_transcript(
    transcript_path: str,
    since: datetime | None = None,
) -> tuple[str | None, int, int, int, int, str | None, int]:
    """Aggregate model, token totals, and branch from a Claude Code transcript JSONL.

    Claude Code ≥2.x passes transcript_path in the Stop payload instead of
    embedding usage directly. Each assistant event looks like:
      {"type":"assistant","timestamp":"...Z","message":{"model":"...","usage":{...}},"gitBranch":"..."}

    `since` is a local-naive datetime; messages timestamped before it are skipped so
    that accumulated turns from earlier sessions in the same conversation file are
    excluded from the current session's totals.

    Returns (model, input_tokens, output_tokens, cache_read, cache_write, branch,
    assistant_message_count).
    """
    path = _safe_transcript_path(transcript_path)
    if path is None:
        return None, 0, 0, 0, 0, None, 0
    try:
        model: str | None = None
        branch: str | None = None
        total_in = total_out = total_cr = total_cw = 0
        assistant_count = 0

        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if obj.get("type") != "assistant":
                    continue

                # Skip turns from before this session started
                if since is not None:
                    ts_str = obj.get("timestamp", "")
                    if ts_str.endswith("Z"):
                        with suppress(ValueError):
                            # Transcript timestamps are UTC — convert to local naive
                            ts = (
                                datetime.fromisoformat(ts_str[:-1])
                                .replace(tzinfo=UTC)
                                .astimezone(tz=None)
                                .replace(tzinfo=None)
                            )
                            if ts < since:
                                continue

                assistant_count += 1
                msg = obj.get("message") or {}
                if msg.get("model"):
                    model = str(msg["model"])
                if obj.get("gitBranch") and branch is None:
                    branch = str(obj["gitBranch"])

                usage = msg.get("usage") or {}
                total_in += int(usage.get("input_tokens", 0))
                total_out += int(usage.get("output_tokens", 0))
                total_cr += int(usage.get("cache_read_input_tokens", 0))
                total_cw += int(usage.get("cache_creation_input_tokens", 0))

        return model, total_in, total_out, total_cr, total_cw, branch, assistant_count
    except (OSError, json.JSONDecodeError, ValueError):
        return None, 0, 0, 0, 0, None, 0


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
            except (OSError, json.JSONDecodeError):
                continue
    return None
