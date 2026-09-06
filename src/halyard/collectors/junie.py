"""Junie (JetBrains) CLI session collector.

Junie ships as a standalone CLI at ``~/.local/bin/junie``, not only as the
JetBrains IDE plugin, so nothing appears under
``~/Library/Application Support/JetBrains`` and the tool was entirely
invisible to Halyard.

Its on-disk layout is unusually good for capture:

- ``~/.junie/sessions/index.jsonl`` — one line per session with
  ``sessionId``, ``createdAt``/``updatedAt`` (epoch ms), ``projectDir``
  and ``taskName``. ``projectDir`` is *better* attribution than Codex
  offers, which records only a working directory that may since have moved.
- ``~/.junie/sessions/<id>/events.jsonl`` — per-event records; those with
  ``event.agentEvent.kind == "LlmResponseMetadataEvent"`` carry a
  ``modelUsage`` list of ``{model, cost, inputTokens, outputTokens,
  cacheInputTokens, cacheCreateTokens}``.

Import model, not a live hook: Junie writes these files as it works, so a
session still in progress is re-imported as it grows, using the size-keyed
state introduced for Codex in v5.2.

**Local models.** Junie can run on-device (an observed machine used
``Qwen3.6-27B-MLX-4bit`` exclusively, 23.1M tokens at $0.00). Those rows are
recorded with ``billing="local"`` so the tokens count toward usage while the
spend is excluded from money totals — ``sum_spend`` already filters on
``billing == "api"``. Reporting local inference as $0.00 *api* spend would
understate nothing, but it would blur real compute into the billable series;
reporting it as unknown would be worse still, because the cost genuinely is
zero.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from halyard.ai_log import AiSession, append_session, find_project_dir
from halyard.collectors import iter_bounded_lines, session_has_evidence
from halyard.git_context import infer_project
from halyard.hub import find_hub

_JUNIE_DIR = Path.home() / ".junie"
_SESSIONS_DIR = _JUNIE_DIR / "sessions"
_INDEX_FILE = _SESSIONS_DIR / "index.jsonl"
_IMPORTED_STATE_FILE = Path.home() / ".halyard" / "junie-imported"

_TOOL = "junie"
_LOCAL_MODEL_MARKERS = ("-mlx", "mlx-", "-gguf", "local/")


def junie_history_present() -> bool:
    """True if Junie session history exists on disk."""
    return _INDEX_FILE.exists()


def junie_imported_any() -> bool:
    """True if any Junie session has been imported already."""
    return _IMPORTED_STATE_FILE.exists() and bool(
        _IMPORTED_STATE_FILE.read_text(encoding="utf-8").strip()
    )


def _is_local_model(model: str) -> bool:
    """Heuristic: an on-device model, so its zero cost is real, not missing.

    Junie reports ``cost`` per model-usage entry and it is genuinely 0.0 for
    local inference. The marker check exists so a *hosted* model that
    happens to report 0.0 — a free tier, a billing outage — is not silently
    reclassified as local and dropped from spend.
    """
    lower = model.lower()
    return any(marker in lower for marker in _LOCAL_MODEL_MARKERS)


def _epoch_ms(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000)
    except (OverflowError, OSError, ValueError):
        return None


def discover_sessions() -> list[dict[str, Any]]:
    """Read the session index. A malformed line is skipped, never fatal."""
    if not _INDEX_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in iter_bounded_lines(_INDEX_FILE, label="junie index"):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("sessionId"):
            out.append(entry)
    return out


def _events_path(session_id: str) -> Path:
    return _SESSIONS_DIR / session_id / "events.jsonl"


def _events_size(session_id: str) -> int:
    try:
        return _events_path(session_id).stat().st_size
    except OSError:
        return 0


def _aggregate_usage(session_id: str) -> tuple[int, int, int, float, str | None, datetime | None]:
    """Sum token usage across a session's events.

    Returns ``(input, output, cache, cost, model, last_event_time)``. The
    model reported is the one with the most tokens — a session may use
    several, and one label has to stand for the row.
    """
    path = _events_path(session_id)
    if not path.exists():
        return 0, 0, 0, 0.0, None, None

    per_model: dict[str, int] = {}
    total_in = total_out = total_cache = 0
    cost = 0.0
    last_ts: datetime | None = None

    for raw in iter_bounded_lines(path, label="junie events"):
        if "modelUsage" not in raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ts = _epoch_ms(event.get("timestampMs"))
        if ts is not None and (last_ts is None or ts > last_ts):
            last_ts = ts
        agent_event = (event.get("event") or {}).get("agentEvent") or {}
        usages = agent_event.get("modelUsage")
        if not isinstance(usages, list):
            continue
        for usage in usages:
            if not isinstance(usage, dict):
                continue
            model_name = str(usage.get("model") or "")
            tin = _safe_int(usage.get("inputTokens"))
            tout = _safe_int(usage.get("outputTokens"))
            tcache = _safe_int(usage.get("cacheInputTokens")) + _safe_int(
                usage.get("cacheCreateTokens")
            )
            total_in += tin
            total_out += tout
            total_cache += tcache
            value = usage.get("cost")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cost += float(value)
            if model_name:
                per_model[model_name] = per_model.get(model_name, 0) + tin + tout

    top_model = max(per_model, key=lambda m: per_model[m]) if per_model else None
    return total_in, total_out, total_cache, cost, top_model, last_ts


def _safe_int(value: Any) -> int:
    """Coerce a token field to int, treating anything malformed as 0.

    Matches the v5.16/B08 contract used by the other collectors: these files
    are untrusted input, and one crafted value must not abort an import.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return 0


def _build_session(entry: dict[str, Any]) -> AiSession | None:
    session_id = str(entry.get("sessionId") or "")
    if not session_id:
        return None

    start = _epoch_ms(entry.get("createdAt"))
    end = _epoch_ms(entry.get("updatedAt"))
    if start is None:
        return None

    tin, tout, tcache, cost, model, last_ts = _aggregate_usage(session_id)
    # Prefer the last event's timestamp over the index's updatedAt: the
    # index is rewritten on session close, the events are written as work
    # happens, so the event stream is the tighter bound on real activity.
    if last_ts is not None and (end is None or last_ts > end):
        end = last_ts
    if end is None or end < start:
        end = start

    project_dir = entry.get("projectDir")
    project = infer_project(Path(project_dir)) if isinstance(project_dir, str) else None
    local = bool(model) and _is_local_model(model or "")

    return AiSession(
        start=start,
        end=end,
        tool=_TOOL,
        model=model or "junie",
        input_tokens=tin,
        output_tokens=tout,
        cache_read=tcache or None,
        cost_usd=0.0 if local else round(cost, 6),
        project=project,
        job_id=f"junie:{session_id}",
        billing="local" if local else "api",
        # v5.39: keep the recorded directory even when it yields no project,
        # so `halyard link-path` can resolve it later.
        source_path=project_dir if isinstance(project_dir, str) else None,
    )


def import_junie_sessions(
    project_dir: Path | None = None,
    *,
    dry_run: bool = False,
    all_projects: bool = False,
) -> list[AiSession]:
    """Import new or grown Junie sessions.

    Re-imports a session whose ``events.jsonl`` has grown since the last run
    — Junie writes continuously, so a session captured mid-write would
    otherwise be frozen at a partial snapshot. Same size-keyed state as the
    Codex importer (v5.2) and for the same reason.
    """
    entries = discover_sessions()
    if not entries:
        return []

    already = _load_imported_state()
    present: set[str] = set()
    imported: list[AiSession] = []
    newly: dict[str, int] = {}

    target = project_dir or find_project_dir() or find_hub()

    for entry in entries:
        session_id = str(entry.get("sessionId") or "")
        if not session_id:
            continue
        present.add(session_id)
        size = _events_size(session_id)
        prior = already.get(session_id)
        if prior is not None and prior == size:
            continue

        try:
            session = _build_session(entry)
        except (OSError, ValueError, TypeError, OverflowError):
            continue
        if session is None:
            continue
        # Deliberately *not* gated on session_is_implausible. Junie keeps a
        # session open across days — two observed here span 143 h and 75 h —
        # and the 12 h plausibility cap would drop them entirely, losing
        # their tokens. That cap exists to stop a multi-day row corrupting
        # *duration* reporting, which the codebase already handles at the
        # right layer: v5.33 excludes over-cap sessions from timeclock
        # reconciliation and v5.35 from the coverage denominator. Recording
        # the row and bounding what it may claim beats discarding the work.
        if not session_has_evidence(session):
            continue

        imported.append(session)
        newly[session_id] = size
        if not dry_run and target is not None:
            append_session(target, session)

    if not dry_run:
        carried = {sid: sz for sid, sz in already.items() if sid in present}
        carried.update(newly)
        _save_imported_state(carried)

    return imported


def _load_imported_state() -> dict[str, int | None]:
    """Map session id → events.jsonl size recorded at import (codex v5.2 format)."""
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
        sid, _, size = line.partition("\t")
        try:
            state[sid] = int(size) if size else None
        except ValueError:
            state[sid] = None
    return state


def _save_imported_state(state: dict[str, int | None]) -> None:
    _IMPORTED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{sid}\t{size}" if size is not None else sid for sid, size in sorted(state.items())]
    _IMPORTED_STATE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
