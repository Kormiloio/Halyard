"""Gemini CLI history file parser.

Reads ~/.gemini/tmp/{slug}/chats/session-*.json (legacy single-object
checkpoint) and session-*.jsonl (current line-delimited rollout) to extract
per-model token counts, tool call stats, and accurate multi-model cost for a
completed session.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from halyard.collectors import normalise_input
from halyard.pricing import calculate_cost

_GEMINI_TMP = Path.home() / ".gemini" / "tmp"
_GEMINI_HISTORY = Path.home() / ".gemini" / "history"


@dataclass
class GeminiModelStats:
    model: str
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    thinking_tokens: int = 0
    tool_calls: int = 0
    tool_errors: int = 0


@dataclass
class GeminiSessionSummary:
    session_id: str
    start: datetime
    end: datetime
    model_stats: list[GeminiModelStats] = field(default_factory=list)

    # Derived — populated by _derive()
    dominant_model: str = ""
    total_input: int = 0
    total_output: int = 0
    total_cache: int = 0
    total_tool_calls: int = 0
    total_tool_errors: int = 0
    cost_usd: float = 0.0
    code_added: int | None = None
    code_removed: int | None = None
    resume_command: str | None = None
    interaction_count: int | None = None
    user_message_count: int | None = None
    assistant_message_count: int | None = None
    prompt_count: int | None = None

    def _derive(self) -> None:
        if not self.model_stats:
            return
        dominant = max(self.model_stats, key=lambda s: s.output_tokens)
        self.dominant_model = dominant.model
        self.total_input = sum(s.input_tokens for s in self.model_stats)
        self.total_output = sum(s.output_tokens for s in self.model_stats)
        self.total_cache = sum(s.cache_tokens for s in self.model_stats)
        self.total_tool_calls = sum(s.tool_calls for s in self.model_stats)
        self.total_tool_errors = sum(s.tool_errors for s in self.model_stats)
        self.cost_usd = sum(
            calculate_cost(
                s.model,
                # thinking tokens billed as input
                input_tokens=s.input_tokens + s.thinking_tokens,
                output_tokens=s.output_tokens,
                cache_read=s.cache_tokens,
            )
            for s in self.model_stats
        )


_MAX_HISTORY_BYTES = 25 * 1024 * 1024  # 25 MB, whole-file cap for .json checkpoints

# .jsonl rollouts are streamed line by line, so memory is bounded by the
# longest line, not the file. The observed real max line is ~0.8 MB; anything
# past _MAX_ROLLOUT_LINE_BYTES is treated as corrupt/hostile and skipped.
_MAX_ROLLOUT_LINE_BYTES = 16 * 1024 * 1024  # 16 MiB per line
# Default total budget for a single parse. Generous so the importer can fully
# read a long session (one observed rollout was 825 MB of inline tool output).
_DEFAULT_ROLLOUT_BYTES = 1024 * 1024 * 1024  # 1 GiB
# The live AfterAgent hook re-parses the growing rollout every turn; a tight
# budget makes it fall back to the gc-session accumulator on huge files instead
# of stalling the host tool.
_HOOK_ROLLOUT_BYTES = 64 * 1024 * 1024  # 64 MiB


def _safe_int(value: object) -> int:
    """Coerce a token field to int, treating any malformed value as 0.

    v5.16/B08: token fields in attacker-stageable history files are not
    guaranteed numeric (e.g. ``tokens:{"input":"abc"}``). A bare ``int()``
    would raise on the ``.jsonl`` rollout path, which only guards ``OSError``,
    so one crafted line would abort the whole import. Honour the documented
    "return None/skip on any error" contract by degrading a bad field to 0.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        result: int = int(value)
    except (ValueError, TypeError, OverflowError):
        return 0
    return result


def _extract_gemini_stats(msg: dict[str, object]) -> GeminiModelStats:
    """Pull one ``type=="gemini"`` message into a single-request stats record.

    Shared by the legacy ``.json`` checkpoint and the ``.jsonl`` rollout — the
    per-event ``model``/``tokens``/``toolCalls`` schema is identical between the
    two formats.
    """
    model = str(msg.get("model") or "unknown")
    tokens = msg.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}
    tool_calls_raw = msg.get("toolCalls") or []
    if not isinstance(tool_calls_raw, list):
        tool_calls_raw = []
    tool_calls = 0
    tool_errors = 0
    for tc in tool_calls_raw:
        if not isinstance(tc, dict):
            continue
        tool_calls += 1
        if tc.get("status") == "error":
            tool_errors += 1
    inp = _safe_int(tokens.get("input"))
    cached = _safe_int(tokens.get("cached"))
    return GeminiModelStats(
        model=model,
        requests=1,
        # Gemini reports gross input (cached subset included).
        input_tokens=normalise_input(inp, cached, 0, cache_inclusive=True),
        output_tokens=_safe_int(tokens.get("output")),
        cache_tokens=cached,
        thinking_tokens=_safe_int(tokens.get("thoughts")),
        tool_calls=tool_calls,
        tool_errors=tool_errors,
    )


def _add_stats(stats_by_model: dict[str, GeminiModelStats], rec: GeminiModelStats) -> None:
    """Merge a single-message stats record into the per-model accumulator."""
    s = stats_by_model.get(rec.model)
    if s is None:
        s = GeminiModelStats(model=rec.model)
        stats_by_model[rec.model] = s
    s.requests += rec.requests
    s.input_tokens += rec.input_tokens
    s.output_tokens += rec.output_tokens
    s.cache_tokens += rec.cache_tokens
    s.thinking_tokens += rec.thinking_tokens
    s.tool_calls += rec.tool_calls
    s.tool_errors += rec.tool_errors


def _total_tokens(msg: dict[str, object]) -> int:
    """The message's reported ``tokens.total`` (used to pick the final emission)."""
    tokens = msg.get("tokens") or {}
    return _safe_int(tokens.get("total")) if isinstance(tokens, dict) else 0


def _read_capped(path: Path) -> str | None:
    """Read a history file, refusing oversized ones.

    `~/.gemini/tmp/.../session-*.json` is writable by any local process;
    an attacker-staged multi-GB file would OOM the importer/hook. Treat
    an oversized (or unreadable) file as absent.
    """
    try:
        if os.path.islink(path):
            return None
        if path.stat().st_size > _MAX_HISTORY_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _finalize_summary(
    *,
    session_id: str,
    start: datetime,
    end: datetime,
    stats_by_model: dict[str, GeminiModelStats],
    user_message_count: int,
    assistant_message_count: int,
    code_added: int | None = None,
    code_removed: int | None = None,
) -> GeminiSessionSummary:
    """Build a derived summary shared by both the checkpoint and rollout paths."""
    summary = GeminiSessionSummary(
        session_id=session_id,
        start=start,
        end=end,
        model_stats=list(stats_by_model.values()),
    )
    summary.user_message_count = user_message_count
    summary.assistant_message_count = assistant_message_count
    summary.interaction_count = user_message_count + assistant_message_count
    summary.prompt_count = user_message_count
    summary._derive()
    summary.code_added = code_added
    summary.code_removed = code_removed
    # Resume command — session_id only; safe to record
    if session_id:
        summary.resume_command = f"gemini --resume {session_id}"
    return summary


def parse_session_file(
    path: Path, *, max_bytes: int = _DEFAULT_ROLLOUT_BYTES
) -> GeminiSessionSummary | None:
    """Parse a Gemini CLI history file. Returns None on any error.

    Dispatches on extension: ``.jsonl`` is the newer line-delimited rollout
    log (streamed, bounded by ``max_bytes``); anything else is the legacy
    single-object checkpoint.
    """
    if path.suffix == ".jsonl":
        return _parse_jsonl_rollout(path, max_bytes=max_bytes)
    return _parse_json_checkpoint(path)


def _parse_json_checkpoint(path: Path) -> GeminiSessionSummary | None:
    """Parse the legacy single-object ``session-*.json`` checkpoint."""
    text = _read_capped(path)
    if text is None:
        return None
    try:
        data: dict[str, object] = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    try:
        session_id = str(data.get("sessionId") or "")
        start_raw = data.get("startTime") or ""
        end_raw = data.get("lastUpdated") or ""
        messages = data.get("messages") or []

        if not session_id or not isinstance(messages, list):
            return None

        start = _parse_iso(str(start_raw))
        end = _parse_iso(str(end_raw))
        if start is None or end is None:
            return None

        stats_by_model: dict[str, GeminiModelStats] = {}
        user_message_count = 0
        assistant_message_count = 0
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            msg_type = str(msg.get("type") or "")
            if msg_type == "user":
                user_message_count += 1
            elif msg_type == "gemini":
                assistant_message_count += 1
                _add_stats(stats_by_model, _extract_gemini_stats(msg))

        # Code delta — session-level field, graceful fallback if absent
        code_added: int | None = None
        code_removed: int | None = None
        code_stats = data.get("codeStats") or data.get("codeChanges") or {}
        if isinstance(code_stats, dict):
            with suppress(Exception):
                added = code_stats.get("added") or code_stats.get("linesAdded")
                if added is not None:
                    code_added = int(added)
            with suppress(Exception):
                removed = code_stats.get("removed") or code_stats.get("linesRemoved")
                if removed is not None:
                    code_removed = int(removed)

        return _finalize_summary(
            session_id=session_id,
            start=start,
            end=end,
            stats_by_model=stats_by_model,
            user_message_count=user_message_count,
            assistant_message_count=assistant_message_count,
            code_added=code_added,
            code_removed=code_removed,
        )

    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _parse_jsonl_rollout(path: Path, *, max_bytes: int) -> GeminiSessionSummary | None:
    """Parse a line-delimited ``session-*.jsonl`` rollout by streaming.

    The header line carries ``sessionId``/``startTime``; ``type=="gemini"``
    event lines carry per-model tokens and tool calls; ``$set`` patches and
    event timestamps advance the end time. Memory is bounded by the longest
    line; a line over ``_MAX_ROLLOUT_LINE_BYTES`` is skipped, and cumulative
    bytes past ``max_bytes`` abort the parse (returns None).

    Critical: the rollout re-emits the **same** ``gemini`` message many times
    as it streams (one ``id`` was observed 53 times), so events are deduped by
    ``id`` — keeping the emission with the largest ``tokens.total`` (the final,
    complete state). Summing every emission would inflate tokens ~30x. After
    dedup the totals match Gemini's own ``/quit`` report to within ~3% (the
    residual gap is API sub-requests Gemini counts but the rollout folds into a
    single message id).
    """
    if os.path.islink(path):
        return None

    session_id = ""
    start: datetime | None = None
    end: datetime | None = None
    # Dedup by message id, keeping the emission with the largest token total.
    gemini_by_id: dict[str, tuple[int, GeminiModelStats]] = {}
    gemini_no_id: list[GeminiModelStats] = []
    user_ids: set[str] = set()
    user_no_id = 0
    seen = 0

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                seen += len(raw.encode("utf-8", errors="ignore"))
                if seen > max_bytes:
                    return None
                if len(raw) > _MAX_ROLLOUT_LINE_BYTES:
                    continue  # pathological/corrupt line — skip, keep going
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(obj, dict):
                    continue

                # Header line — first object carrying sessionId.
                if not session_id and obj.get("sessionId"):
                    session_id = str(obj.get("sessionId") or "")
                    start = _parse_iso(str(obj.get("startTime") or "")) or start
                    end = _parse_iso(str(obj.get("lastUpdated") or "")) or end
                    continue

                # `$set` patch line — advances lastUpdated.
                patch = obj.get("$set")
                if isinstance(patch, dict):
                    if patch.get("lastUpdated"):
                        end = _parse_iso(str(patch.get("lastUpdated"))) or end
                    continue

                msg_type = str(obj.get("type") or "")
                msg_id = str(obj.get("id") or "")
                if msg_type == "user":
                    if msg_id:
                        user_ids.add(msg_id)
                    else:
                        user_no_id += 1
                elif msg_type == "gemini":
                    rec = _extract_gemini_stats(obj)
                    total = _total_tokens(obj)
                    if msg_id:
                        prev = gemini_by_id.get(msg_id)
                        if prev is None or total >= prev[0]:
                            gemini_by_id[msg_id] = (total, rec)
                    else:
                        gemini_no_id.append(rec)

                # Advance end from the event timestamp (a rollout may lack $set).
                ts = _parse_iso(str(obj.get("timestamp") or ""))
                if ts is not None and (end is None or ts > end):
                    end = ts
    # v5.16/B08: honour the documented "return None on any error" contract —
    # a single crafted rollout line must never escape and abort the import loop.
    except (OSError, ValueError, TypeError, OverflowError):
        return None

    if not session_id or start is None:
        return None
    if end is None:
        end = start

    stats_by_model: dict[str, GeminiModelStats] = {}
    for _total, rec in gemini_by_id.values():
        _add_stats(stats_by_model, rec)
    for rec in gemini_no_id:
        _add_stats(stats_by_model, rec)

    return _finalize_summary(
        session_id=session_id,
        start=start,
        end=end,
        stats_by_model=stats_by_model,
        user_message_count=len(user_ids) + user_no_id,
        assistant_message_count=len(gemini_by_id) + len(gemini_no_id),
    )


# Gemini session IDs are UUID-like (hex + hyphens). Reject anything else so
# the value can never inject glob metacharacters into the pattern below.
_SESSION_ID_RE = re.compile(r"^[0-9A-Za-z-]{8,}$")


def _session_id_of(path: Path) -> str:
    """Read just the session id from a history file. Empty string on any error.

    For ``.jsonl`` rollouts the id lives on the header line, so only the first
    line is read (cheap even for an 825 MB file); ``.json`` checkpoints are read
    whole through the size cap.
    """
    try:
        if os.path.islink(path):
            return ""
        if path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                first = fh.readline(_MAX_ROLLOUT_LINE_BYTES)
            data = json.loads(first)
            return str(data.get("sessionId") or "") if isinstance(data, dict) else ""
        text = _read_capped(path)
        if text is None:
            return ""
        data = json.loads(text)
        return str(data.get("sessionId") or "") if isinstance(data, dict) else ""
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ""


def find_session_file(session_id: str) -> Path | None:
    """Find the history file for a session by its ID.

    Globs both the legacy ``.json`` checkpoint and the newer ``.jsonl`` rollout
    whose name ends in the 8-char prefix of *session_id*, then confirms the full
    ``sessionId`` matches exactly. This prevents false-positive matches when two
    sessions share the same 8-char prefix (Gap-7 collision scenario).
    """
    if not _SESSION_ID_RE.match(session_id):
        return None
    prefix = session_id[:8]
    matches: list[Path] = []
    for ext in ("json", "jsonl"):
        matches.extend(_GEMINI_TMP.glob(f"*/chats/session-*-{prefix}.{ext}"))
    if not matches:
        return None
    # Verify every prefix candidate against the full session ID.  A prefix-only
    # match is not enough: stale or crafted files can share the same first eight
    # characters and would otherwise contaminate token/cost attribution.
    exact = [path for path in matches if _session_id_of(path) == session_id]
    if exact:
        return max(exact, key=_safe_mtime)
    return None


def _safe_mtime(path: Path) -> float:
    """mtime, or -1 if the file vanished mid-scan (racing unlink)."""
    try:
        return path.stat().st_mtime
    except OSError:
        return -1.0


def find_all_session_files() -> list[Path]:
    """Return all session history files across all project slugs.

    Covers both the legacy ``.json`` checkpoint and the newer ``.jsonl``
    rollout written by current Gemini CLI versions.
    """
    files = list(_GEMINI_TMP.glob("*/chats/session-*.json"))
    files.extend(_GEMINI_TMP.glob("*/chats/session-*.jsonl"))
    return files


def project_dir_for_slug(slug: str) -> Path | None:
    """Read ~/.gemini/history/{slug}/.project_root. Returns None if absent."""
    pointer = _GEMINI_HISTORY / slug / ".project_root"
    if not pointer.exists():
        return None
    try:
        return Path(pointer.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeDecodeError):
        return None


def _parse_iso(s: str) -> datetime | None:
    """Parse ISO 8601 string with or without trailing Z."""
    try:
        return (
            datetime.fromisoformat(s.replace("Z", "+00:00"))
            .astimezone(tz=None)
            .replace(tzinfo=None)
        )
    except (TypeError, ValueError):
        return None
