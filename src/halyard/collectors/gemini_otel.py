"""Gemini CLI OpenTelemetry outfile reader (v2.67).

Capture-only: reads true, measured api-/tool-call ``duration_ms`` from
the user's opt-in ``telemetry.outfile`` and returns per-session
``(api_seconds, tool_seconds)``. Never reads prompt/response/tool-arg
content even when ``logPrompts:true`` put it in the file.

Verified against gemini-cli 0.41.1 (see the v2.67 design.md Phase 0
contract): the file is a stream of **concatenated pretty-printed**
JSON objects (``JSON.stringify(rec, null, 2) + "\\n"``, append mode) —
NOT line-delimited — and ``session.id`` is a **resource** attribute,
not a per-record attribute. The reader is bounded and fail-closed
(v2.39 pattern): any problem ⇒ ``(None, None)``; unavailable is never
``0``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_MAX_OTEL_BYTES = 25 * 1024 * 1024  # 25 MB — bounded untrusted read

_API_EVENT = "gemini_cli.api_response"
_TOOL_EVENT = "gemini_cli.tool_call"


def _safe_path(raw: str | os.PathLike[str]) -> Path | None:
    try:
        if os.path.islink(os.path.expanduser(os.fspath(raw))):
            return None
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            return None
        if path.stat().st_size > _MAX_OTEL_BYTES:
            return None
    except OSError:
        return None
    return path


def _iter_json_objects(text: str) -> Iterator[dict[str, Any]]:
    """Yield each top-level JSON object from a buffer of concatenated
    (pretty-printed, whitespace-separated) objects. Malformed regions
    are skipped rather than raising."""
    decoder = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except ValueError:
            nxt = text.find("{", i + 1)
            if nxt == -1:
                break
            i = nxt
            continue
        if isinstance(obj, dict):
            yield obj
        i = end


def _resource_session_id(obj: dict[str, Any]) -> str | None:
    """session.id is a resource attribute; probe the SDK-internal
    container variants defensively (not a documented contract)."""
    res = obj.get("resource")
    if not isinstance(res, dict):
        return None
    for key in ("attributes", "_attributes", "_rawAttributes"):
        attrs = res.get(key)
        if isinstance(attrs, dict):
            val = attrs.get("session.id")
            if isinstance(val, str):
                return val
        elif isinstance(attrs, list):  # OTLP keyValue list form
            for kv in attrs:
                if isinstance(kv, dict) and kv.get("key") == "session.id":
                    v = kv.get("value")
                    if isinstance(v, dict):
                        sv = v.get("stringValue")
                        if isinstance(sv, str):
                            return sv
                    elif isinstance(v, str):
                        return v
    return None


def _event_name(obj: dict[str, Any]) -> str | None:
    for key in ("body", "eventName"):
        v = obj.get(key)
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            sv = v.get("stringValue")
            if isinstance(sv, str):
                return sv
    attrs = obj.get("attributes")
    if isinstance(attrs, dict):
        v = attrs.get("event.name")
        if isinstance(v, str):
            return v
    return None


def _duration_ms(obj: dict[str, Any]) -> float | None:
    attrs = obj.get("attributes")
    if not isinstance(attrs, dict):
        return None
    raw = attrs.get("duration_ms")
    if isinstance(raw, bool):  # guard: bool is an int subclass
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _outfile_from_settings(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tel = data.get("telemetry") if isinstance(data, dict) else None
    if not isinstance(tel, dict):
        return None
    if tel.get("enabled") is False:
        return None
    out = tel.get("outfile")
    return out if isinstance(out, str) and out else None


def resolve_telemetry_outfile(cwd: Path) -> str | None:
    """Resolve Gemini's telemetry outfile with Gemini's own precedence:
    ``GEMINI_TELEMETRY_OUTFILE`` env, then workspace
    ``.gemini/settings.json``, then ``~/.gemini/settings.json``. None
    if telemetry is disabled or no outfile is configured.
    """
    env = os.environ.get("GEMINI_TELEMETRY_OUTFILE")
    if env:
        return env
    for settings in (cwd / ".gemini" / "settings.json", Path.home() / ".gemini" / "settings.json"):
        out = _outfile_from_settings(settings)
        if out is not None:
            return out
    return None


def read_otel_durations(
    outfile: str | os.PathLike[str], session_id: str
) -> tuple[int | None, int | None]:
    """Return ``(api_seconds, tool_seconds)`` summed from the outfile
    for ``session_id``. A kind with no matching records stays ``None``
    (unavailable is not zero). Any failure ⇒ ``(None, None)``.
    """
    if not session_id:
        return (None, None)
    path = _safe_path(outfile)
    if path is None:
        return (None, None)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(_MAX_OTEL_BYTES)
    except OSError:
        return (None, None)

    api_ms = 0.0
    tool_ms = 0.0
    api_seen = False
    tool_seen = False
    for obj in _iter_json_objects(text):
        if _resource_session_id(obj) != session_id:
            continue
        name = _event_name(obj)
        if name == _API_EVENT:
            ms = _duration_ms(obj)
            if ms is not None:
                api_ms += ms
                api_seen = True
        elif name == _TOOL_EVENT:
            ms = _duration_ms(obj)
            if ms is not None:
                tool_ms += ms
                tool_seen = True

    api_seconds = round(api_ms / 1000) if api_seen else None
    tool_seconds = round(tool_ms / 1000) if tool_seen else None
    return (api_seconds, tool_seconds)
