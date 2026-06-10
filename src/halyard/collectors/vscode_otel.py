"""VS Code Copilot OpenTelemetry mapper (v3.12).

Maps the standard OTLP/JSON stream VS Code Copilot exports (GenAI
semantic conventions) to :class:`AiSession` rows. This replaces the
brittle internal-file scrape (v3.7/v3.13) with a documented, stable,
opt-in source that does not break when Microsoft reshuffles internal
storage.

Two consumers feed this one mapper (the testable core):

* the live localhost OTLP receiver (``otel_receiver.py``), which pushes
  decoded payloads in as spans arrive, and
* the documented collector-file fallback (Option B), which can decode an
  OTLP/JSON file the user's OTel Collector wrote.

**Privacy is binding** (project non-negotiable #5). The mapper reads
only an *allowlist* of metadata attribute keys. Content-bearing
attributes (``gen_ai.prompt``, ``gen_ai.completion``, message/content
events, tool arguments, file paths) and every non-allowlisted key are
never looked up, so they can never enter an ``AiSession``. Span events
(which carry message content) are never read at all.

**Phase 0 status (deferred):** the GitHub Copilot Chat extension was not
installed in the build environment, so a real OTLP payload could not be
captured to confirm the exact attribute placement (resource vs span
``session.id``; usage on spans vs metrics; the session-end signal). The
mapper is therefore written defensively against the *documented* GenAI
semconv + OTLP/JSON encoding and probes both placements. Re-verify the
exact shape against a live capture before relying on it in production
(see ``design.md`` Phase 0). "Unavailable is not zero": any attribute the
stream does not carry stays ``None``, never a fabricated ``0``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from halyard.ai_log import AiSession
from halyard.collectors import normalise_input

# Opt-in marker written by `halyard install-vscode-otel`. The receiver
# only starts when this exists, so default users get no new listener; the
# doctor nudge keys off its absence.
MARKER_PATH = Path.home() / ".halyard" / "vscode-otel.enabled"


def otel_capture_enabled() -> bool:
    """True if the user opted into VS Code OTel capture (marker present)."""
    return MARKER_PATH.exists()


# ── Allowlist (the privacy boundary) ───────────────────────────────────
# ONLY these attribute keys are ever read off a span/metric. Anything
# else — notably any content attribute — is never looked up, so it cannot
# reach an AiSession. Keep this list minimal and metadata-only.
_SESSION_ID_KEYS = ("gen_ai.conversation.id", "session.id")
_MODEL_KEYS = ("gen_ai.response.model", "gen_ai.request.model")
_INPUT_TOKEN_KEYS = ("gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens")
_OUTPUT_TOKEN_KEYS = ("gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens")
_OPERATION_KEY = "gen_ai.operation.name"
_TOOL_NAME_KEY = "gen_ai.tool.name"  # used ONLY as a boolean signal; never stored

# Operation names that denote an LLM inference call (an assistant turn).
_CHAT_OPS = frozenset(
    {"chat", "text_completion", "generate_content", "create_message", "inference"}
)
# Operation/span names that denote a tool invocation.
_TOOL_OPS = frozenset({"execute_tool", "tool"})

_TOOL = "github-copilot"  # reuse the existing report/dashboard bucket
_TELEMETRY_SOURCE = "copilot-otel"  # distinguishes from the importer's "copilot-jsonl"
_TELEMETRY_TRUST = "observed"

# OTLP status code for an errored span (STATUS_CODE_ERROR).
_STATUS_ERROR = 2

# v5.19/B-followup: per-accumulator caps that bound memory growth from a
# single (token-less) ingest path. The session-count cap in hub_server.py
# only bounds the *number* of accumulators; without these a single accumulator
# can grow without bound:
#  * unbounded session_id length (a 1 MB session id is accepted today)
#  * unbounded model_counts cardinality (any model string OTLP carries is
#    folded into the dict)
# A real editor has session ids of <100 chars and ≤10 distinct models, so
# these ceilings are comfortably above legitimate use.
_MAX_SESSION_ID_LEN = 256
_MAX_MODEL_NAME_LEN = 128
_MAX_MODELS_PER_SESSION = 32


# ── OTLP/JSON value decoding ───────────────────────────────────────────


def _decode_value(value: Any) -> Any:
    """Decode a single OTLP/JSON ``AnyValue`` to a Python scalar.

    Per the OTLP/JSON encoding, ``intValue`` is a *string* and
    ``doubleValue``/``boolValue``/``stringValue`` are native. Returns
    ``None`` for arrays/kvlists/bytes (never metadata we want) and on any
    malformed shape.
    """
    if not isinstance(value, dict):
        return None
    if "stringValue" in value:
        sv = value["stringValue"]
        return sv if isinstance(sv, str) else None
    if "intValue" in value:
        iv = value["intValue"]
        try:
            return int(iv)
        except (TypeError, ValueError):
            return None
    if "doubleValue" in value:
        dv = value["doubleValue"]
        if isinstance(dv, bool):
            return None
        return dv if isinstance(dv, (int, float)) else None
    if "boolValue" in value:
        bv = value["boolValue"]
        return bv if isinstance(bv, bool) else None
    return None


def _get_attr(attrs: Any, key: str) -> Any:
    """Return the decoded value for ``key`` from an OTLP attribute list.

    Only the requested (allowlisted) key is decoded — non-allowlisted
    attributes are never materialised, so content can't leak through.
    """
    if not isinstance(attrs, list):
        return None
    for kv in attrs:
        if isinstance(kv, dict) and kv.get("key") == key:
            return _decode_value(kv.get("value"))
    return None


def _first_attr(attrs: Any, keys: tuple[str, ...]) -> Any:
    for key in keys:
        val = _get_attr(attrs, key)
        if val is not None:
            return val
    return None


def _as_int(val: Any) -> int | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    return None


def _unix_nano_to_dt(raw: Any) -> datetime | None:
    """OTLP unix-nanos (string or int) → local-naive datetime."""
    n = _as_int(raw if isinstance(raw, int) else None)
    if n is None and isinstance(raw, str):
        try:
            n = int(raw)
        except ValueError:
            return None
    if n is None or n <= 0:
        return None
    try:
        return datetime.fromtimestamp(n / 1_000_000_000)
    except (OverflowError, OSError, ValueError):
        return None


# ── Per-session accumulator ────────────────────────────────────────────


@dataclass
class _SessionAcc:
    """Mutable per-``session.id`` accumulator. Many spans → one row."""

    session_id: str
    start: datetime | None = None
    end: datetime | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_seen: bool = False
    chat_spans: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    api_ns: int = 0
    tool_ns: int = 0
    api_seen: bool = False
    tool_seen: bool = False
    model_counts: dict[str, int] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)

    def _bump_time(self, start: datetime | None, end: datetime | None) -> None:
        if start is not None and (self.start is None or start < self.start):
            self.start = start
        for candidate in (end, start):
            if candidate is not None and (self.end is None or candidate > self.end):
                self.end = candidate


def _classify(operation: Any, span_name: Any, has_tool_name: bool) -> str:
    """Return "tool", "chat", or "other" for a span."""
    op = operation if isinstance(operation, str) else ""
    name = span_name if isinstance(span_name, str) else ""
    if op in _TOOL_OPS or name in _TOOL_OPS or has_tool_name:
        return "tool"
    if op in _CHAT_OPS or name in _CHAT_OPS:
        return "chat"
    return "other"


def _ingest_span(
    acc_map: dict[str, _SessionAcc], span: dict[str, Any], resource_sid: str | None
) -> None:
    attrs = span.get("attributes")
    sid = _first_attr(attrs, _SESSION_ID_KEYS) or resource_sid
    if not isinstance(sid, str) or not sid:
        return  # cannot attribute a span with no session id
    # v5.19/B-followup: bound session-id length. An attacker on a shared host
    # (or a buggy emitter) could otherwise grow accumulator memory by sending
    # multi-megabyte session ids. A real session id is a short opaque token.
    if len(sid) > _MAX_SESSION_ID_LEN:
        return

    start = _unix_nano_to_dt(span.get("startTimeUnixNano"))
    end = _unix_nano_to_dt(span.get("endTimeUnixNano"))
    operation = _get_attr(attrs, _OPERATION_KEY)
    has_tool_name = _get_attr(attrs, _TOOL_NAME_KEY) is not None
    kind = _classify(operation, span.get("name"), has_tool_name)

    # A chat span may also carry usage; classify by the dominant signal but
    # always harvest usage tokens wherever they appear.
    in_tok = _as_int(_first_attr(attrs, _INPUT_TOKEN_KEYS))
    out_tok = _as_int(_first_attr(attrs, _OUTPUT_TOKEN_KEYS))
    # A span carrying usage but no recognised operation name is still an
    # inference call — count it as chat so its tokens are attributed.
    if (in_tok is not None or out_tok is not None) and kind == "other":
        kind = "chat"

    acc = acc_map.get(sid)
    if acc is None:
        acc = _SessionAcc(session_id=sid)
        acc_map[sid] = acc
    acc.last_update = datetime.now()
    acc._bump_time(start, end)

    duration_ns = 0
    if start is not None and end is not None and end > start:
        duration_ns = int((end - start).total_seconds() * 1_000_000_000)

    if in_tok is not None:
        acc.input_tokens += max(0, in_tok)
        acc.tokens_seen = True
    if out_tok is not None:
        acc.output_tokens += max(0, out_tok)
        acc.tokens_seen = True

    model = _first_attr(attrs, _MODEL_KEYS)
    # v5.19/B-followup: cap per-session model cardinality so an emitter sending
    # unique model strings (`m-0`, `m-1`, …) cannot grow the dict without
    # bound. Bump the count of an already-tracked model in any case; only
    # refuse to add new entries once the ceiling is reached.
    if (
        isinstance(model, str)
        and model
        and len(model) <= _MAX_MODEL_NAME_LEN
        and (model in acc.model_counts or len(acc.model_counts) < _MAX_MODELS_PER_SESSION)
    ):
        acc.model_counts[model] = acc.model_counts.get(model, 0) + 1

    if kind == "tool":
        acc.tool_calls += 1
        status = span.get("status")
        if isinstance(status, dict) and status.get("code") == _STATUS_ERROR:
            acc.tool_errors += 1
        if duration_ns:
            acc.tool_ns += duration_ns
            acc.tool_seen = True
    elif kind == "chat":
        acc.chat_spans += 1
        if duration_ns:
            acc.api_ns += duration_ns
            acc.api_seen = True


def accumulate_traces(acc_map: dict[str, _SessionAcc], payload: Any) -> dict[str, _SessionAcc]:
    """Fold an OTLP/JSON traces payload into ``acc_map`` (in place).

    Tolerant of partial/malformed payloads: a bad sub-tree is skipped,
    never raised. Returns the same map for chaining.
    """
    if not isinstance(payload, dict):
        return acc_map
    resource_spans = payload.get("resourceSpans")
    if not isinstance(resource_spans, list):
        return acc_map
    for rs in resource_spans:
        if not isinstance(rs, dict):
            continue
        resource = rs.get("resource")
        resource_sid = None
        if isinstance(resource, dict):
            rid = _first_attr(resource.get("attributes"), _SESSION_ID_KEYS)
            resource_sid = rid if isinstance(rid, str) and rid else None
        scope_spans = rs.get("scopeSpans")
        if not isinstance(scope_spans, list):
            continue
        for ss in scope_spans:
            if not isinstance(ss, dict):
                continue
            spans = ss.get("spans")
            if not isinstance(spans, list):
                continue
            for span in spans:
                if isinstance(span, dict):
                    _ingest_span(acc_map, span, resource_sid)
    return acc_map


def finalize(acc: _SessionAcc) -> AiSession | None:
    """Build the aggregated :class:`AiSession` for one session id.

    Returns ``None`` if there is no usable timing (no real turn). Carries
    only metadata; no content field is ever set.
    """
    if acc.start is None:
        return None
    end = acc.end if acc.end is not None and acc.end >= acc.start else acc.start

    model, breakdown = _resolve_models(acc.model_counts)

    interaction_count = acc.chat_spans + acc.tool_calls or None

    return AiSession(
        start=acc.start,
        end=end,
        tool=_TOOL,
        model=model,
        input_tokens=normalise_input(acc.input_tokens, 0, 0, cache_inclusive=False),
        output_tokens=acc.output_tokens,
        cost_usd=0.0,
        tokens_available=acc.tokens_seen,
        session_id=acc.session_id,
        job_id=f"copilot-otel:{acc.session_id}",
        tool_calls=acc.tool_calls or None,
        tool_errors=acc.tool_errors or None,
        api_seconds=round(acc.api_ns / 1_000_000_000) if acc.api_seen else None,
        tool_seconds=round(acc.tool_ns / 1_000_000_000) if acc.tool_seen else None,
        model_breakdown=breakdown,
        interaction_count=interaction_count,
        assistant_message_count=acc.chat_spans or None,
        interaction_data_available=True,
        telemetry_source=_TELEMETRY_SOURCE,
        telemetry_trust=_TELEMETRY_TRUST,
    )


def _resolve_models(counts: dict[str, int]) -> tuple[str, str | None]:
    """Return ``(primary_model, model_breakdown_or_None)``.

    Primary = the most-used model (ties broken by name for determinism).
    Breakdown is the compact ``"a:3|b:1"`` form only when >1 model.
    """
    if not counts:
        return _TOOL, None
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    primary = ordered[0][0]
    if len(ordered) == 1:
        return primary, None
    breakdown = "|".join(f"{m}:{n}" for m, n in ordered)
    return primary, breakdown


def parse_traces_to_sessions(payload: Any) -> list[AiSession]:
    """Convenience: a whole OTLP/JSON traces payload → finalized sessions.

    Used by tests and the collector-file fallback (Option B). The live
    receiver instead keeps a long-lived accumulator and flushes per
    session id on its own schedule.
    """
    acc_map: dict[str, _SessionAcc] = {}
    accumulate_traces(acc_map, payload)
    sessions = []
    for acc in acc_map.values():
        session = finalize(acc)
        if session is not None:
            sessions.append(session)
    return sessions
