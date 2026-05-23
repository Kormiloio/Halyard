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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    find_project_dir,
    maybe_emit_milestones,
    maybe_show_dashboard_hint,
    parse_sessions,
    read_active_project,
    write_unattributed_session,
)
from halyard.collectors import (
    session_has_evidence,
    session_is_implausible,
    session_is_synthetic_telemetry,
)
from halyard.collectors.claude_code_surface import detect_surface
from halyard.git_context import (
    commits_in_window,
    current_branch,
    current_remote,
    head_sha,
    infer_project,
    infer_project_with_source,
    numstat_delta,
)
from halyard.hub import find_hub
from halyard.mcp_inventory import extract_mcp_server, reduce_mcp
from halyard.model_breakdown import ModelSeg
from halyard.model_breakdown import cost_of as _breakdown_cost
from halyard.model_breakdown import encode as _encode_breakdown
from halyard.model_breakdown import primary_model as _primary_model
from halyard.pricing import calculate_cost, model_is_known

_CC_SESSION_FILE = Path.home() / ".halyard" / "cc-session"


def _coerce_int(value: object, default: int = 0) -> int:
    """Tolerant int coercion for attacker-influenceable payload fields.

    A malformed token must degrade that one field, never raise out of
    a hook (defense-in-depth behind the cli_hooks backstop).
    """
    if isinstance(value, bool):  # bool is an int subclass — treat as 0/1
        return int(value)
    if isinstance(value, (int, float, str)):
        with suppress(TypeError, ValueError):
            return int(value)
    return default


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

    # Catch-up high-water mark. The live hooks (UserPromptSubmit + Stop) only
    # capture a turn when they fire in lockstep; in practice Stop is missed for
    # stretches (notably the desktop app). The old design read the transcript
    # only since *this* turn's start, so every turn in a gap was dropped with no
    # recovery. Anchor the read to the latest end already recorded for this
    # session instead — one Stop after a gap then back-fills everything since
    # the last row.
    payload_session_id = payload.get("session_id") or payload.get("sessionId")
    if payload_session_id and project_dir is not None:
        watermark = _last_recorded_end(project_dir, str(payload_session_id))
        if watermark is not None:
            start = watermark

    # Try usage from payload first (older Claude Code format)
    usage = payload.get("usage") or payload.get("message", {}).get("usage", {}) or {}
    input_tokens = _coerce_int(usage.get("input_tokens", 0))
    output_tokens = _coerce_int(usage.get("output_tokens", 0))
    cache_read = _coerce_int(usage.get("cache_read_input_tokens", 0) or usage.get("cache_read", 0))
    cache_write = _coerce_int(
        usage.get("cache_creation_input_tokens", 0) or usage.get("cache_write", 0)
    )

    model = (
        payload.get("model")
        or payload.get("stop_model")
        or (_read_model_from_settings(project_dir) if project_dir else None)
    )

    branch = current_branch(cwd)
    assistant_message_count: int | None = None
    interaction_count: int | None = None
    session_id: str | None = payload.get("session_id") or payload.get("sessionId")
    user_message_count: int | None = None
    tool_calls: int | None = None
    tool_errors: int | None = None
    rejections: int | None = None
    mcp_servers_used: int | None = None
    mcp_server_names: str | None = None
    wall_seconds: int | None = None
    model_breakdown: str | None = None

    # Read the transcript (Claude Code ≥2.x). It is the fallback for
    # tokens/model/branch AND the source of interaction metadata, so
    # parse it whenever present — not only when the payload lacked
    # usage.
    transcript_path = payload.get("transcript_path", "")
    if transcript_path:
        ts = _read_from_transcript(transcript_path, since=start)
        assistant_message_count = ts.assistant_count
        interaction_count = ts.interaction_count
        if not (input_tokens or output_tokens) and (ts.input_tokens or ts.output_tokens):
            input_tokens, output_tokens = ts.input_tokens, ts.output_tokens
            cache_read, cache_write = ts.cache_read, ts.cache_write
        if not model and ts.model:
            model = ts.model
        if not branch and ts.branch:
            branch = ts.branch
        if session_id is None and ts.session_id:
            session_id = ts.session_id
        user_message_count = ts.user_count
        tool_calls = ts.tool_calls
        tool_errors = ts.tool_errors
        rejections = ts.rejected_suggestion_count
        mcp_servers_used = ts.mcp_servers_used
        mcp_server_names = ts.mcp_server_names
        wall_seconds = ts.wall_seconds
        model_breakdown = ts.model_breakdown
        # Multi-model session: primary = highest-cost model so the
        # one-line summary stays meaningful.
        if model_breakdown and ts.primary_model:
            model = ts.primary_model

    if not model:
        model = "claude-unknown"

    tokens_available = input_tokens > 0 or output_tokens > 0
    # Multi-model: cost is Σ per-model (correct pricing per model);
    # single-model: unchanged.
    if model_breakdown:
        _bc = _breakdown_cost(model_breakdown)
        cost = (
            _bc
            if _bc is not None
            else calculate_cost(model, input_tokens, output_tokens, cache_read, cache_write)
        )
    else:
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
        _project, _rung = infer_project_with_source(cwd)
        _attr_method = _rung  # repo-map | toml | git-auto | None
        _extra_tags = ["attribution:inferred"] if _project else []

    _remote = current_remote(cwd)
    client_surface = detect_surface()

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
        client_surface=client_surface,
        commit_count=commit_count,
        code_added=code_added,
        code_removed=code_removed,
        session_id=str(session_id) if session_id else None,
        user_message_count=user_message_count,
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        rejected_suggestion_count=rejections,
        mcp_servers_used=mcp_servers_used,
        mcp_server_names=mcp_server_names,
        wall_seconds=wall_seconds,
        model_breakdown=model_breakdown,
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
    if (
        not session_has_evidence(session)
        or session_is_implausible(session)
        or session_is_synthetic_telemetry(session)
    ):
        return 0

    if can_append_project_log and project_dir is not None:
        append_session(project_dir, session)
        maybe_emit_milestones(project_dir)
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


def _last_recorded_end(project_dir: Path, session_id: str) -> datetime | None:
    """Latest end already recorded for this Claude Code session in the ledger.

    Serves as a catch-up high-water mark: each Stop captures everything since
    the last recorded row, so a missed Stop is recovered by the next one
    instead of dropping the turns in between. Returns None if nothing recorded
    yet (first turn of the session) or on any read error.
    """
    try:
        ends = [
            s.end
            for s in parse_sessions(project_dir)
            if s.tool == "claude-code" and s.session_id == session_id
        ]
    except Exception:
        return None
    return max(ends) if ends else None


def _read_session_state() -> dict[str, Any]:
    """Return {"start_dt": datetime, "sha": str|None} from the session file.

    Handles both the new JSON format (v2.24+) and the legacy plain ISO timestamp
    written by older versions of the collector.
    """
    if not _CC_SESSION_FILE.exists():
        return {}
    try:
        raw = _CC_SESSION_FILE.read_text().strip()
    except OSError:
        return {}
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


@dataclass
class _TranscriptStats:
    """Everything we can mine from a Claude Code transcript JSONL.

    "Unavailable is not zero": counts that the transcript can't yield
    stay ``None`` (e.g. no transcript) rather than a fabricated 0. A
    real 0 (transcript present, genuinely no tool calls) is truthful
    and kept as 0.
    """

    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    branch: str | None = None
    assistant_count: int = 0
    user_count: int | None = None
    tool_calls: int | None = None
    tool_errors: int | None = None
    rejected_suggestion_count: int | None = None
    interaction_count: int | None = None
    # v3.4 MCP-usage inventory (privacy-bounded via mcp_inventory.py).
    mcp_servers_used: int | None = None
    mcp_server_names: str | None = None
    session_id: str | None = None
    wall_seconds: int | None = None
    # model -> [input, output, cache_read, cache_write] (v2.61 usage form)
    model_usage: dict[str, list[int]] = field(default_factory=dict)

    def _segs(self) -> list[ModelSeg]:
        return [
            ModelSeg(m, u[0], u[1], u[2], u[3]) for m, u in sorted(self.model_usage.items()) if m
        ]

    @property
    def model_breakdown(self) -> str | None:
        segs = self._segs()
        if len(segs) < 2:
            return None
        return _encode_breakdown(segs)

    @property
    def primary_model(self) -> str | None:
        segs = self._segs()
        if len(segs) < 2:
            return None
        return _primary_model(segs)


def _transcript_ts(obj: dict[str, object], since: datetime | None) -> datetime | None:
    """Parse a transcript event's UTC timestamp to local-naive, or None."""
    ts_str = obj.get("timestamp", "")
    if not isinstance(ts_str, str) or not ts_str.endswith("Z"):
        return None
    try:
        return (
            datetime.fromisoformat(ts_str[:-1])
            .replace(tzinfo=UTC)
            .astimezone(tz=None)
            .replace(tzinfo=None)
        )
    except ValueError:
        return None


def _read_from_transcript(
    transcript_path: str,
    since: datetime | None = None,
) -> _TranscriptStats:
    """Aggregate model, tokens, branch, and interaction metadata from a
    Claude Code transcript JSONL.

    Claude Code ≥2.x passes transcript_path in the Stop payload instead
    of embedding usage. Assistant events carry model/usage; tool calls
    are ``tool_use`` content blocks on assistant messages; tool results
    come back as ``user`` events whose content blocks are
    ``tool_result`` (``is_error`` flags failures). ``since`` (local
    -naive) excludes turns from earlier sessions in the same file.
    """
    stats = _TranscriptStats()
    path = _safe_transcript_path(transcript_path)
    if path is None:
        return stats
    try:
        user_count = 0
        tool_calls = 0
        tool_errors = 0
        rejections = 0
        mcp_servers: set[str] = set()
        first_ts: datetime | None = None
        last_ts: datetime | None = None

        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                etype = obj.get("type")
                if etype not in ("assistant", "user"):
                    continue

                ts = _transcript_ts(obj, since)
                if since is not None and ts is not None and ts < since:
                    continue

                if stats.session_id is None:
                    sid = obj.get("sessionId") or obj.get("session_id")
                    if sid:
                        stats.session_id = str(sid)

                if ts is not None:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                msg = obj.get("message") or {}
                content = msg.get("content") if isinstance(msg, dict) else None

                if etype == "assistant":
                    stats.assistant_count += 1
                    cur_model: str | None = None
                    if isinstance(msg, dict) and msg.get("model"):
                        cur_model = str(msg["model"])
                        stats.model = cur_model
                    if obj.get("gitBranch") and stats.branch is None:
                        stats.branch = str(obj["gitBranch"])
                    usage = msg.get("usage") or {} if isinstance(msg, dict) else {}
                    u_in = int(usage.get("input_tokens", 0))
                    u_out = int(usage.get("output_tokens", 0))
                    u_cr = int(usage.get("cache_read_input_tokens", 0))
                    u_cw = int(usage.get("cache_creation_input_tokens", 0))
                    stats.input_tokens += u_in
                    stats.output_tokens += u_out
                    stats.cache_read += u_cr
                    stats.cache_write += u_cw
                    if cur_model:
                        acc = stats.model_usage.setdefault(cur_model, [0, 0, 0, 0])
                        acc[0] += u_in
                        acc[1] += u_out
                        acc[2] += u_cr
                        acc[3] += u_cw
                    if isinstance(content, list):
                        for b in content:
                            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                                continue
                            tool_calls += 1
                            # v3.4: an MCP tool is mcp__<server>__<tool>.
                            # Reduce to the server segment only; the raw
                            # name/args are never retained.
                            server = extract_mcp_server(b.get("name"))
                            if server is not None:
                                mcp_servers.add(server)
                else:  # user
                    blocks = content if isinstance(content, list) else []
                    results = [
                        b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"
                    ]
                    if results:
                        for b in results:
                            if bool(b.get("is_error")):
                                tool_errors += 1
                                # v3.3: distinguish explicit user rejection from tool failure
                                content_str = str(b.get("content", "")).lower()
                                if "user doesn't want to proceed" in content_str:
                                    rejections += 1
                    else:
                        user_count += 1

        had_transcript = (
            stats.assistant_count > 0 or user_count > 0 or tool_calls > 0 or tool_errors > 0
        )
        if had_transcript:
            stats.user_count = user_count
            stats.tool_calls = tool_calls
            stats.tool_errors = tool_errors
            stats.rejected_suggestion_count = rejections
            stats.interaction_count = stats.assistant_count + user_count
            stats.mcp_servers_used, stats.mcp_server_names = reduce_mcp(mcp_servers)
            if first_ts is not None and last_ts is not None and last_ts >= first_ts:
                stats.wall_seconds = int((last_ts - first_ts).total_seconds())
        return stats
    except (OSError, json.JSONDecodeError, ValueError):
        return _TranscriptStats()


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
