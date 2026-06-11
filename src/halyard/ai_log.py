"""AI session log — writer, parser, and project discovery for ai-sessions.log.

File locking is cross-platform: ``fcntl.flock`` on POSIX,
``msvcrt.locking`` on Windows, and a thread-only fallback elsewhere
(with a one-time warning). See ``_acquire_lock`` / ``_release_lock``.

Serialization of optional AiSession fields (the key=value tail) is
managed by a declarative registry (_FIELDS). To add a new field, add
one FieldSpec to that registry; the writer and parser will stay
automatically symmetric.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import warnings
from collections import defaultdict
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import IO

# Lock backend dispatch — selected once at import time.
_LOCK_LENGTH = 0x7FFFFFFF  # ~2 GiB; covers any plausible log size on Windows.

_acquire_lock: Callable[[int], None]
_release_lock: Callable[[int], None]

if sys.platform == "win32":
    import msvcrt as _msvcrt

    def _acquire_lock(fd: int) -> None:
        _msvcrt.locking(fd, _msvcrt.LK_LOCK, _LOCK_LENGTH)

    def _acquire_read_lock(fd: int) -> None:
        # Windows _msvcrt.locking does not have a direct shared lock;
        # LK_NBKCK is 'non-blocking' which isn't what we want.
        # Actually, Windows locking is always exclusive.
        # For now, readers on Windows will just not lock (same as before)
        # to avoid blocking multiple readers, OR we can use exclusive lock
        # which effectively serializes readers.
        # Given the goal of "shared" lock, we skip it on Windows if not supported
        # by msvcrt.locking.
        pass

    def _release_read_lock(fd: int) -> None:
        # Symmetric with the no-op _acquire_read_lock: must NOT call LK_UNLCK on
        # a region that was never locked (that raises OSError on Windows).
        pass

    def _release_lock(fd: int) -> None:
        _msvcrt.locking(fd, _msvcrt.LK_UNLCK, _LOCK_LENGTH)

else:
    try:
        import fcntl as _fcntl

        def _acquire_lock(fd: int) -> None:
            _fcntl.flock(fd, _fcntl.LOCK_EX)

        def _acquire_read_lock(fd: int) -> None:
            _fcntl.flock(fd, _fcntl.LOCK_SH)

        def _release_read_lock(fd: int) -> None:
            _fcntl.flock(fd, _fcntl.LOCK_UN)

        def _release_lock(fd: int) -> None:
            _fcntl.flock(fd, _fcntl.LOCK_UN)

    except ImportError:
        _LOCK_WARNED = False

        def _acquire_lock(fd: int) -> None:
            global _LOCK_WARNED
            if not _LOCK_WARNED:
                warnings.warn(
                    "Halyard: no OS-level file locking available on this platform; "
                    "concurrent writes from multiple processes are unsafe.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                _LOCK_WARNED = True

        def _acquire_read_lock(fd: int) -> None:
            pass

        def _release_read_lock(fd: int) -> None:
            pass

        def _release_lock(fd: int) -> None:
            pass


def atomic_replace(src: Path | str, dst: Path | str, *, attempts: int = 6) -> None:
    """``os.replace`` with a Windows-aware retry on sharing violations.

    On Windows, ``os.replace`` raises ``PermissionError`` (WinError 5) when
    another process has the destination file open — a routine occurrence under
    concurrent readers. Retry with exponential backoff (5, 10, 20, 40, 80 ms;
    ~155 ms total) to absorb the transient sharing violation. POSIX never hits
    the retry path: ``os.replace`` is atomic and always succeeds there.
    """
    delay = 0.005
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


SPEC_URL = "https://halyard.dev/spec/ai-sessions/v1"
HEADER = (
    f"; Halyard AI session log — spec: {SPEC_URL}\n"
    "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]\n"
)
AI_LOG_FILENAME = "ai-sessions.log"
_HALYARD_AUDIT_LOG = Path.home() / ".halyard" / "halyard.log"
_HALYARD_DIAG_LOG = Path.home() / ".halyard" / "diagnostic.log"

# Regex matching characters that would break the space-delimited log line format.
# Used to sanitize positional fields (tool, model) before writing.
_UNSAFE_FIELD_RE = re.compile(r"[\s=]")
# v2.75: well-formed key shape for unknown-token (`extra`) passthrough.
# Matches the existing token-key style (alnum + _.-), so a corrupt or
# adversarial line can't turn `extra` into a junk sink.
_EXTRA_KEY_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9_.-]*\Z")
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


class FieldKind(Enum):
    """Codec families for AiSession optional fields."""

    SAFE_FIELD = auto()  # string with _safe_field sanitize
    INT = auto()  # int | None
    FLOAT_4 = auto()  # float | None, 4 decimal places
    BOOL_LOWER = auto()  # bool | None -> "true"/"false"
    TOKENS_AVAILABLE = auto()  # bool: false -> "tokens_available=false", true -> omitted
    BILLING = auto()  # str: not "api" -> "billing=value", "api" -> omitted
    TAGS = auto()  # list[str] -> "tags=a,b,c" (percent-encoded)
    FREE_TEXT = auto()  # str -> "key=value" (percent-encoded)
    BREAKDOWN = auto()  # str -> "model_breakdown=v" (special breakdown sanitize)


@dataclass(frozen=True)
class FieldSpec:
    """Registry entry for one optional AiSession wire field."""

    attr: str  # AiSession attribute name
    key: str  # On-wire key name
    kind: FieldKind


_FIELDS = (
    FieldSpec("project", "project", FieldKind.SAFE_FIELD),
    FieldSpec("user", "user", FieldKind.SAFE_FIELD),
    FieldSpec("cache_read", "cache_read", FieldKind.INT),
    FieldSpec("cache_write", "cache_write", FieldKind.INT),
    FieldSpec("tokens_available", "tokens_available", FieldKind.TOKENS_AVAILABLE),
    FieldSpec("billing", "billing", FieldKind.BILLING),
    FieldSpec("credits", "credits", FieldKind.FLOAT_4),
    FieldSpec("job_id", "job_id", FieldKind.SAFE_FIELD),
    FieldSpec("source", "source", FieldKind.SAFE_FIELD),
    FieldSpec("attr_method", "attr_method", FieldKind.SAFE_FIELD),
    FieldSpec("tags", "tags", FieldKind.TAGS),
    FieldSpec("note", "note", FieldKind.FREE_TEXT),
    FieldSpec("session_id", "session_id", FieldKind.SAFE_FIELD),
    FieldSpec("tool_calls", "tool_calls", FieldKind.INT),
    FieldSpec("tool_errors", "tool_errors", FieldKind.INT),
    FieldSpec("wall_seconds", "wall_seconds", FieldKind.INT),
    FieldSpec("agent_active_seconds", "agent_active_seconds", FieldKind.INT),
    FieldSpec("api_seconds", "api_seconds", FieldKind.INT),
    FieldSpec("tool_seconds", "tool_seconds", FieldKind.INT),
    FieldSpec("code_added", "code_added", FieldKind.INT),
    FieldSpec("code_removed", "code_removed", FieldKind.INT),
    FieldSpec("model_breakdown", "model_breakdown", FieldKind.BREAKDOWN),
    FieldSpec("resume_command", "resume_command", FieldKind.FREE_TEXT),
    FieldSpec("branch", "branch", FieldKind.SAFE_FIELD),
    FieldSpec("remote", "remote", FieldKind.SAFE_FIELD),
    FieldSpec("client_surface", "client_surface", FieldKind.SAFE_FIELD),
    FieldSpec("commit_count", "commit_count", FieldKind.INT),
    FieldSpec("pr_ref", "pr_ref", FieldKind.SAFE_FIELD),
    FieldSpec("pr_state", "pr_state", FieldKind.SAFE_FIELD),
    FieldSpec("outcome_resolved_at", "outcome_resolved_at", FieldKind.SAFE_FIELD),
    FieldSpec("review_comments", "review_comments", FieldKind.INT),
    FieldSpec("review_rounds", "review_rounds", FieldKind.INT),
    FieldSpec("time_to_merge_s", "time_to_merge_s", FieldKind.INT),
    FieldSpec("review_decision", "review_decision", FieldKind.SAFE_FIELD),
    FieldSpec("mcp_servers_used", "mcp_servers_used", FieldKind.INT),
    FieldSpec("mcp_server_names", "mcp_server_names", FieldKind.SAFE_FIELD),
    FieldSpec("interaction_count", "interaction_count", FieldKind.INT),
    FieldSpec("user_message_count", "user_message_count", FieldKind.INT),
    FieldSpec("assistant_message_count", "assistant_message_count", FieldKind.INT),
    FieldSpec("prompt_count", "prompt_count", FieldKind.INT),
    FieldSpec("accepted_suggestion_count", "accepted_suggestion_count", FieldKind.INT),
    FieldSpec("rejected_suggestion_count", "rejected_suggestion_count", FieldKind.INT),
    FieldSpec("files_touched_count", "files_touched_count", FieldKind.INT),
    FieldSpec("test_run_count", "test_run_count", FieldKind.INT),
    FieldSpec("test_status", "test_status", FieldKind.SAFE_FIELD),
    FieldSpec("build_status", "build_status", FieldKind.SAFE_FIELD),
    FieldSpec("human_active_seconds", "human_active_seconds", FieldKind.INT),
    FieldSpec("idle_seconds", "idle_seconds", FieldKind.INT),
    FieldSpec("interaction_data_available", "interaction_data_available", FieldKind.BOOL_LOWER),
    FieldSpec("outcome_data_available", "outcome_data_available", FieldKind.BOOL_LOWER),
    FieldSpec("telemetry_source", "telemetry_source", FieldKind.SAFE_FIELD),
    FieldSpec("telemetry_trust", "telemetry_trust", FieldKind.SAFE_FIELD),
)

_FIELDS_BY_KEY = {f.key: f for f in _FIELDS}


# ---------------------------------------------------------------------------
# v2.17 Section 6.1: Error visibility helper
# ---------------------------------------------------------------------------


def _log_error(msg: str, exc: Exception) -> None:
    """Append a timestamped traceback entry to ~/.halyard/halyard.log.

    Never raises — if the log write itself fails the error is silently dropped
    (we cannot log the logger failure).
    """
    try:
        _HALYARD_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=UTC).isoformat(timespec="seconds")
        tb = traceback.format_exc()
        entry = f"[{ts}] {msg}: {type(exc).__name__}: {exc}\n{tb}\n"
        with _HALYARD_AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass


def log_diagnostic(msg: str, *, tool: str | None = None, project: str | None = None) -> None:
    """Append a one-line diagnostic entry to ~/.halyard/diagnostic.log.

    Used for silent fallbacks (Hub timeout, git failure) that would
    otherwise be invisible to the user but are valuable for support.
    """

    def _flat(value: str) -> str:
        # Keep one diagnostic event on exactly one physical line: a newline in
        # msg/tool/project would otherwise split it into several entries and
        # corrupt downstream line-by-line parsing.
        return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    try:
        _HALYARD_DIAG_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=UTC).isoformat(timespec="seconds")
        prefix = f"[{ts}]"
        if tool:
            prefix += f" [{_flat(tool)}]"
        if project:
            prefix += f" [{_flat(project)}]"
        with _HALYARD_DIAG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{prefix} {_flat(msg)}\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# v2.17 task 1.1-1.2: File locking primitive
# ---------------------------------------------------------------------------


@contextmanager
def locked_file(path: Path, mode: str) -> Generator[IO[str], None, None]:
    """Open *path* in *mode* with an exclusive lock held for the duration.

    The parent directory is created if absent.  The lock is advisory but
    cooperative — all Halyard writers use this helper, so it is sufficient to
    prevent concurrent appends from interleaving writes. The backend
    (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows) is selected
    once at import time.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        thread_lock = _PATH_LOCKS.setdefault(lock_key, threading.RLock())
    # newline="" keeps Halyard's plain-text files LF-only on every OS — Windows
    # text mode would otherwise translate \n → \r\n on write, breaking byte-level
    # diffs and hash checks across platforms.
    with thread_lock, open(path, mode, encoding="utf-8", newline="") as f:
        fd = f.fileno()
        _acquire_lock(fd)
        try:
            yield f
        finally:
            _release_lock(fd)


@contextmanager
def read_locked_file(path: Path) -> Generator[IO[str], None, None]:
    """Open *path* for reading with a shared (read) lock held for the duration.

    Ensures the reader never sees a 'torn read' (partial line) mid-write by
    an exclusive writer. On platforms without shared locking (Windows),
    this is a no-op that yields the file handle normally.
    """
    lock_key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        thread_lock = _PATH_LOCKS.setdefault(lock_key, threading.RLock())
    with thread_lock, open(path, encoding="utf-8") as f:
        fd = f.fileno()
        _acquire_read_lock(fd)
        try:
            yield f
        finally:
            _release_read_lock(fd)


# ---------------------------------------------------------------------------
# v2.17 task 2.1-2.3: Amendment record support
# ---------------------------------------------------------------------------


def session_hash(line: str) -> str:
    """Return the first 12 hex chars of SHA-256(stripped line).

    The hash is computed on the raw ``s`` line *before* any amendments so
    ``a`` records always reference the original session, even if amendments
    later change its semantic meaning.

    12 hex chars = 48 bits. The birthday bound puts a ~50% collision at
    ~2^24 (≈16M) distinct session lines — orders of magnitude beyond any
    realistic local/team ledger over its lifetime. The width is *not*
    cheaply changeable: this value is the join key between ``s`` and
    ``a`` records in every existing on-disk log, so widening it would
    orphan all existing amendments. Instead, ``parse_sessions`` detects
    a genuine collision (same prefix, different raw line) and quarantines
    rather than silently mis-folding an amendment.
    """
    return hashlib.sha256(line.strip().encode()).hexdigest()[:12]


@dataclass
class Amendment:
    """A parsed ``a <hash> key=value ...`` correction record."""

    session_hash: str
    kvs: dict[str, str]


def parse_amendment(line: str) -> Amendment | None:
    """Parse an ``a <hash> key=value ...`` line; return None on malformed input."""
    parts = line.split()
    if len(parts) < 2 or parts[0] != "a":
        return None
    h = parts[1]
    kvs: dict[str, str] = {}
    for token in parts[2:]:
        if "=" in token:
            k, v = token.split("=", 1)
            kvs[k] = v
    return Amendment(session_hash=h, kvs=kvs)


def _safe_field(value: str) -> str:
    """Sanitize a positional log field (tool, model) for safe embedding in a log line.

    Replaces whitespace and '=' characters with '_' and caps the result at 128
    characters.  Whitespace would split the space-delimited record into extra
    tokens; '=' would be mis-parsed as a key=value pair by the parser.
    """
    return _UNSAFE_FIELD_RE.sub("_", value)[:128]


def _safe_breakdown(value: str) -> str:
    """Sanitize the model_breakdown token *without* the 128-char cap.

    The v2.61 usage-form grammar (`model:in/out/cr/cw|...`) for a 3-4
    model session can exceed 128 chars; capping would truncate a
    segment and force a (safe but lossy) fall back to single-model
    attribution. The grammar contains no whitespace/`=`, so only the
    record-splitting characters are neutralised; length is preserved so
    multi-model cost stays correct.
    """
    return _UNSAFE_FIELD_RE.sub("_", value)


def _encode_free_text(value: str) -> str:
    """Percent-encode a free-text value for safe storage in a key=value log token.

    Uses ``urllib.parse.quote(value, safe="")`` so every byte that would
    break the space-delimited format (spaces, control chars, '=', '%') is
    escaped. The output is round-trippable through ``_decode_free_text``
    and preserves literal underscores in the input — unlike the legacy
    underscore-substitution scheme.
    """
    return urllib.parse.quote(value, safe="")


def _decode_free_text(value: str) -> str:
    """Decode a free-text value from a log line, accepting both encodings.

    If the stored value contains any ``%`` escape, it is decoded via
    ``urllib.parse.unquote`` (the new percent-encoded form). Otherwise the
    legacy rule is applied — underscores are turned back into spaces — so
    pre-existing log lines continue to parse correctly.
    """
    if "%" in value:
        return urllib.parse.unquote(value)
    return value.replace("_", " ")


def _decode_tag(token: str) -> str:
    """Decode one tag element.

    New form is percent-encoded (``_encode_free_text``); legacy form is
    the raw ``_safe_field`` output (whitespace/`=`→`_`, no percent
    escapes). A token with a ``%`` is unquoted; otherwise it is the
    legacy raw value verbatim — crucially NOT underscore→space (legacy
    tags never used that substitution, unlike other free-text fields).
    """
    if "%" in token:
        return urllib.parse.unquote(token)
    return token


@dataclass
class AiSession:
    start: datetime
    end: datetime
    tool: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    project: str | None = None
    user: str | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    tokens_available: bool = True
    billing: str = "api"
    credits: float | None = None
    job_id: str | None = None
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    note: str | None = None
    # D-1: attribution provenance — how the project was determined.
    # Values: "timer" (active timer running), "ws_root" (Cursor workspace root),
    # "git" (git-remote inference), "backfill" (assign-unattributed / backfill-window),
    # "manual" (explicit CLI flag).  None means unknown / pre-D-1 log line.
    attr_method: str | None = None
    # Rich session telemetry (v2.6 — optional, all surfaces backward-compatible)
    session_id: str | None = None
    tool_calls: int | None = None
    tool_errors: int | None = None
    wall_seconds: int | None = None
    agent_active_seconds: int | None = None
    # v2.67 — Gemini OTLP-measured api/tool time (independent optionals;
    # agent_active_seconds is left untouched). None = unavailable, not 0.
    api_seconds: int | None = None
    tool_seconds: int | None = None
    code_added: int | None = None
    code_removed: int | None = None
    model_breakdown: str | None = None  # compact: "model-a:3|model-b:1"
    resume_command: str | None = None
    # v2.24 outcome metadata
    branch: str | None = None  # git branch at session close; trust: captured
    remote: str | None = None  # normalized git remote (host/owner/repo); trust: captured
    client_surface: str | None = None  # cli | desktop | ide | unknown
    commit_count: int | None = None  # commits in session window; trust: captured
    pr_ref: str | None = None  # e.g. "owner/repo#42"; written by outcome sync
    pr_state: str | None = None  # merged | closed | open | none
    outcome_resolved_at: str | None = None  # ISO timestamp when pr_ref was resolved
    # v3.1 review-friction signals — written by `halyard outcome sync`.
    # Counts/enum only: NEVER review text, PR title, branch, or author.
    review_comments: int | None = None  # issue + inline review comments; trust: captured
    review_rounds: int | None = None  # count of CHANGES_REQUESTED reviews; trust: captured
    time_to_merge_s: int | None = None  # createdAt→mergedAt secs, merged only; captured
    review_decision: str | None = None  # APPROVED | CHANGES_REQUESTED | REVIEW_REQUIRED
    # v3.4 MCP-server usage inventory — privacy-bounded (mcp_inventory.py).
    # Count is always safe; names are allowlisted-only. NEVER the raw
    # mcp__*__* string, tool segment, args, server command/URL/env.
    mcp_servers_used: int | None = None  # distinct MCP servers whose tools were used
    mcp_server_names: str | None = None  # sorted CSV, allowlisted server names only
    # v2.32 privacy-safe interaction and outcome metadata.
    # These fields intentionally store counts/statuses only. They must never
    # contain prompts, code, chat text, file names, or file contents.
    interaction_count: int | None = None
    user_message_count: int | None = None
    assistant_message_count: int | None = None
    prompt_count: int | None = None
    accepted_suggestion_count: int | None = None
    rejected_suggestion_count: int | None = None
    files_touched_count: int | None = None
    test_run_count: int | None = None
    test_status: str | None = None
    build_status: str | None = None
    human_active_seconds: int | None = None
    idle_seconds: int | None = None
    interaction_data_available: bool | None = None
    outcome_data_available: bool | None = None
    telemetry_source: str | None = None
    telemetry_trust: str | None = None
    # v2.75: forward-compat passthrough. Unrecognized `s `-line
    # key=value tokens (from a newer Halyard, or an extending consumer
    # such as Halyard-Enterprise: cost_center=, roi_ref=, …) are
    # preserved verbatim and re-emitted, so the line format is
    # extensible without forking the parser. OSS NEVER interprets
    # these. compare=False: must not affect equality or the
    # content-addressed session id / hash (cache + amendment join keys
    # stay derived from immutable identity fields only).
    extra: dict[str, str] = field(default_factory=dict, compare=False)
    # v2.29: hash of the original raw `s` line, set at parse time before amendment
    # folding. Excluded from serialization and equality checks. Used by outcome sync
    # to produce amendment records that reference the correct log-line hash.
    _raw_hash: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_log_line(cls, line: str) -> AiSession | None:
        """Parse and validate one session line, quarantining malformed records."""
        parsed, error = _parse_line_result(line)
        if error is not None:
            _write_quarantine(line, error)
        return parsed

    def apply_amendment(self, amendment: Amendment) -> None:
        """Mutate this session in-memory according to an amendment record.

        Only the keys listed in the v2.17 amendment spec are honoured:
        ``project``, ``source``, ``confirmed_at``, ``note``, plus
        ``attr_method`` from v2.21 attribution provenance. Unknown keys are
        silently ignored so future amendment keys don't break older parsers.
        """
        for key, value in amendment.kvs.items():
            if key == "project":
                self.project = value
            elif key == "source":
                self.source = value
            elif key == "attr_method":
                self.attr_method = value
            elif key == "confirmed_at":
                # Store as note-style string; callers can parse as ISO if needed
                pass  # confirmed_at is metadata; no AiSession field for it yet
            elif key == "note":
                self.note = _decode_free_text(value)
            elif key == "pr_ref":
                self.pr_ref = value
            elif key == "pr_state":
                self.pr_state = value
            elif key == "outcome_resolved_at":
                self.outcome_resolved_at = value
            elif key == "review_comments":
                with suppress(ValueError):
                    self.review_comments = int(value)
            elif key == "review_rounds":
                with suppress(ValueError):
                    self.review_rounds = int(value)
            elif key == "time_to_merge_s":
                with suppress(ValueError):
                    self.time_to_merge_s = int(value)
            elif key == "review_decision":
                self.review_decision = value

    @classmethod
    def log_line_error(cls, line: str) -> str | None:
        """Return the validation error for a line without writing quarantine."""
        _parsed, error = _parse_line_result(line)
        return error

    def to_log_line(self) -> str:
        parts = [
            "s",
            self.start.strftime("%Y-%m-%dT%H:%M:%S"),
            self.end.strftime("%Y-%m-%dT%H:%M:%S"),
            _safe_field(self.tool),  # M-1: sanitize whitespace/= injection
            _safe_field(self.model),  # M-1: sanitize whitespace/= injection
            str(self.input_tokens),
            str(self.output_tokens),
            f"{self.cost_usd:.4f}",
        ]
        kvs: list[str] = []
        for spec in _FIELDS:
            val = getattr(self, spec.attr)
            if val is None:
                continue

            match spec.kind:
                case FieldKind.SAFE_FIELD:
                    if val:
                        kvs.append(f"{spec.key}={_safe_field(val)}")
                case FieldKind.INT:
                    kvs.append(f"{spec.key}={val}")
                case FieldKind.FLOAT_4:
                    kvs.append(f"{spec.key}={val:.4f}")
                case FieldKind.BOOL_LOWER:
                    kvs.append(f"{spec.key}={str(val).lower()}")
                case FieldKind.TOKENS_AVAILABLE:
                    if not val:
                        kvs.append(f"{spec.key}=false")
                case FieldKind.BILLING:
                    if val != "api":
                        kvs.append(f"{spec.key}={_safe_field(val)}")
                case FieldKind.TAGS:
                    if val:
                        kvs.append(f"{spec.key}={','.join(_encode_free_text(t) for t in val)}")
                case FieldKind.FREE_TEXT:
                    if val:
                        kvs.append(f"{spec.key}={_encode_free_text(val)}")
                case FieldKind.BREAKDOWN:
                    if val:
                        kvs.append(f"{spec.key}={_safe_breakdown(val)}")

        # v2.75: re-emit forward-compat passthrough tokens last,
        # sorted for byte-stable output, percent-encoded so a value
        # with spaces/`=`/`%` can never forge a record delimiter or a
        # second token (same injection guard as every free-text
        # field). Empty `extra` ⇒ output byte-identical to pre-v2.75.
        for ek in sorted(self.extra):
            kvs.append(f"{ek}={_encode_free_text(self.extra[ek])}")
        return " ".join(parts + kvs)


def append_session(project_dir: Path, session: AiSession, *, direct: bool = False) -> None:
    # v4.0: Hub-first ingestion. If the Halyard Hub is running on localhost,
    # emit the session as a JSON payload instead of writing directly. This
    # eliminates file-locking latency in the tool's execution path.
    if not direct and _try_append_to_hub(session):
        return

    # Fallback to direct local write (v1-v3 behavior)
    log_path = project_dir / AI_LOG_FILENAME
    with locked_file(log_path, "a") as f:
        f.write(session.to_log_line() + "\n")


def _try_append_to_hub(session: AiSession) -> bool:
    """Attempt to send the session to the Hub; return True on success.

    Routes through hub_client so HALYARD_DISABLE_HUB and the configured
    host/port are honored consistently with the rest of the codebase.
    """
    from halyard.hub_client import ingest_line

    return ingest_line(session.to_log_line())


def maybe_emit_milestones(project_dir: Path) -> None:
    """Emit milestone easter-egg lines to stderr (best-effort).

    Called once by interactive stop-hook collectors after appending —
    NOT in the per-append path, so bulk imports stay O(n).
    """
    import sys

    try:
        from halyard.easter_eggs import check_milestones

        sessions = parse_sessions(project_dir)
        total_cost = sum(s.cost_usd for s in sessions)
        for msg in check_milestones(len(sessions), total_cost):
            print(f"[halyard] {msg}", file=sys.stderr)
    except Exception:  # easter eggs must never interrupt session logging
        pass


def _iter_log_lines(fh: IO[str]) -> Generator[str, None, None]:
    """Yield stripped, non-comment, non-empty lines from a log file handle.

    Streaming reader: memory is bounded by the longest single line, not by
    total file size. Comment and blank lines are filtered here so callers
    don't have to repeat the check.
    """
    for raw_line in fh:
        line = raw_line.strip()
        if line and not line.startswith(";"):
            yield line


def api_plus_tool_seconds(session: AiSession) -> int | None:
    """Display-only sum of OTLP api + tool time, or None if either part
    is unavailable. Deliberately a module function, not an AiSession
    property, so it can never be mistaken for stored state.
    """
    if session.api_seconds is None or session.tool_seconds is None:
        return None
    return session.api_seconds + session.tool_seconds


def parse_sessions(project_dir: Path, *, now: datetime | None = None) -> list[AiSession]:
    # v2.17 task 2.4: fold ``a`` amendment records in file order (last-write-wins per key).
    #
    # Design note: sessions are stored as a list to preserve all ``s`` lines,
    # including duplicate lines (same raw content → same hash).  Amendment
    # folding uses ``sessions_by_hash`` which maps each hash to the *first*
    # AiSession object with that hash; any amendments are applied to that
    # object.  Duplicate ``s`` lines with the same hash receive no amendments
    # (edge case: real logs have unique timestamps so duplicates do not arise
    # in normal use).
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        return []

    sessions: list[AiSession] = []
    sessions_by_hash: dict[str, AiSession] = {}  # first occurrence per hash for amendment lookup
    raw_by_hash: dict[str, str] = {}  # stripped raw line per hash, to detect true collisions
    amendments_by_hash: dict[str, list[Amendment]] = defaultdict(list)

    # Read the lines under the shared lock, then release before parsing: a
    # large read no longer blocks a concurrent writer (Hub append) for the whole
    # parse, while torn-read safety (no partial line) is still guaranteed.
    with read_locked_file(log_path) as fh:
        raw_lines = list(_iter_log_lines(fh))
    for line in raw_lines:
        if line.startswith("s "):
            parsed, error = _parse_line_result(line)
            if parsed is not None:
                h = session_hash(line)
                stripped = line.strip()
                prior = raw_by_hash.get(h)
                if prior is not None and prior != stripped:
                    # Two *different* `s` lines produced the same 48-bit
                    # session_hash prefix. Folding `a` amendments by hash
                    # would mis-apply one session's correction to the
                    # other — silent cross-attribution. Astronomically
                    # rare (~2^24 distinct sessions for 50%), but the
                    # failure is silent corruption, so quarantine the
                    # colliding line and drop it rather than fold blindly.
                    _write_quarantine(
                        line, f"session_hash collision with a different session ({h})"
                    )
                    continue
                raw_by_hash.setdefault(h, stripped)
                parsed._raw_hash = h
                if h not in sessions_by_hash:
                    sessions_by_hash[h] = parsed
                sessions.append(parsed)
            elif error is not None:
                _write_quarantine(line, error)
        elif line.startswith("a "):
            amendment = parse_amendment(line)
            if amendment is not None:
                amendments_by_hash[amendment.session_hash].append(amendment)

    # Apply amendments in file order; last-write-wins per key.
    # Only the first-occurrence object per hash is amended.
    for h, session in sessions_by_hash.items():
        for amendment in amendments_by_hash.get(h, []):
            session.apply_amendment(amendment)

    # Durable synthetic-telemetry guard (v2.53): an external writer
    # (claude-mem daemon) appends canned rows directly to the log,
    # bypassing every collector write guard. Exclude them at the read
    # chokepoint so no surface ever sees them. The raw lines remain in
    # the file (immutable, auditable); they are simply not surfaced.
    # Also drop future-dated rows: a genuine turn cannot start in the
    # future, and an external writer can append any timestamp (observed:
    # rows dated days ahead, polluting the top of every newest-first
    # view). Narrow on purpose — only the future check, so long-but-real
    # historical sessions are never retroactively hidden.
    # Local import: collectors imports ai_log (cycle otherwise).
    from halyard.collectors import session_is_synthetic_telemetry, session_starts_in_future

    surfaced = [
        s
        for s in sessions
        if not session_is_synthetic_telemetry(s) and not session_starts_in_future(s, now=now)
    ]
    # v5.8: canonicalize project slugs at the read boundary so every surface
    # groups one logical project under one slug. User-defined map; the log is
    # never rewritten. Local import — attribution imports ai_log.
    from halyard.attribution import canonical_project, load_project_aliases

    aliases = load_project_aliases(project_dir)
    if aliases:
        for s in surfaced:
            if s.project:
                s.project = canonical_project(s.project, aliases)
    # v3.14: collapse redundant Gemini rows for the same session (the live
    # hook writes the whole-session cumulative total every turn and the
    # importer writes one more whole-session row). Read-time only — the raw
    # lines stay in the file.
    return collapse_gemini_sessions(surfaced)


_GEMINI_JOB_PREFIX = "gemini:"
_CODEX_JOB_PREFIX = "codex:"
_CLAUDE_JOB_PREFIX = "claude:"
_COPILOT_JOB_PREFIX = "copilot:"


def _gemini_session_key(session: AiSession) -> str | None:
    """A stable id for the Gemini CLI session a row belongs to, else None.

    Both capture paths derive from the same whole-session history file:
    the live hook tags rows with ``session_id=<id>``; the importer tags
    them with ``job_id=gemini:<id>``. Either resolves to the same key, so
    rows already in the log collapse too. Returns None for non-Gemini
    rows and for Gemini rows with no resolvable id (left untouched).
    """
    if session.tool != "gemini-cli":
        return None
    if session.session_id:
        return session.session_id
    if session.job_id and session.job_id.startswith(_GEMINI_JOB_PREFIX):
        return session.job_id[len(_GEMINI_JOB_PREFIX) :]
    return None


def _codex_session_key(session: AiSession) -> str | None:
    """A stable id for the Codex session a row belongs to, else None.

    The Codex importer tags each row with ``job_id=codex:<uuid>``. A session
    still being written is imported more than once (once per importer run while
    its rollout file grows), so those rows must collapse to one. Returns None
    for non-Codex rows and Codex rows with no resolvable id.
    """
    if session.tool != "codex":
        return None
    if session.job_id and session.job_id.startswith(_CODEX_JOB_PREFIX):
        return session.job_id[len(_CODEX_JOB_PREFIX) :]
    return None


def _claude_session_key(session: AiSession) -> str | None:
    """A stable id for a Claude Code *import* row, else None.

    The v5.21 transcript importer tags rows with ``job_id=claude:<id>``; a
    live transcript imported mid-session re-imports as it grows (codex
    pattern), so those rows must collapse to one. Deliberately narrower than
    the Gemini key: there is NO ``session_id`` fallback, because the Stop
    hook's rows are per-turn deltas — collapsing them by session id would
    destroy real turns. Only importer-tagged rows participate.
    """
    if session.tool != "claude-code":
        return None
    if session.job_id and session.job_id.startswith(_CLAUDE_JOB_PREFIX):
        return session.job_id[len(_CLAUDE_JOB_PREFIX) :]
    return None


def _copilot_session_key(session: AiSession) -> str | None:
    """A stable id for a Copilot *import* row, else None.

    The v5.22 importer tags rows with ``job_id=copilot:<id>``; a chat
    session imported mid-flight re-imports as its file grows (codex
    pattern), so those rows must collapse to one. Same deliberately-narrow
    shape as ``_claude_session_key``: NO ``session_id`` fallback — OTel
    -sourced rows (``copilot-otel:<id>``, which does not match this prefix)
    and pre-v5.22 import rows carry ``session_id`` without this job prefix
    and must never collapse.
    """
    if session.tool != "github-copilot":
        return None
    if session.job_id and session.job_id.startswith(_COPILOT_JOB_PREFIX):
        return session.job_id[len(_COPILOT_JOB_PREFIX) :]
    return None


def _redundant_session_key(session: AiSession) -> str | None:
    """Namespaced collapse key spanning every tool with multi-row sessions.

    Returns ``"<tool>:<id>"`` so keys never collide across tools, or None when
    the row is not part of a known multi-row family (left untouched).
    """
    gemini = _gemini_session_key(session)
    if gemini is not None:
        return f"{_GEMINI_JOB_PREFIX}{gemini}"
    codex = _codex_session_key(session)
    if codex is not None:
        return f"{_CODEX_JOB_PREFIX}{codex}"
    claude = _claude_session_key(session)
    if claude is not None:
        return f"{_CLAUDE_JOB_PREFIX}{claude}"
    copilot = _copilot_session_key(session)
    if copilot is not None:
        return f"{_COPILOT_JOB_PREFIX}{copilot}"
    return None


def _canonical_gemini_row(rows: list[AiSession]) -> AiSession:
    """Pick the single canonical row for one Gemini session.

    Most complete wins (max input+output — the hook's final cumulative
    snapshot and the importer's whole-session row both reach the true
    total). Ties prefer the better-attributed row (one with a ``project``),
    then the wider [start, end] window, then larger cache_read — so the
    attributed hook row is kept over an unattributed importer duplicate.
    """
    if len(rows) == 1:
        return rows[0]

    def rank(s: AiSession) -> tuple[int, int, float, int]:
        return (
            s.input_tokens + s.output_tokens,
            1 if s.project else 0,
            (s.end - s.start).total_seconds(),
            s.cache_read or 0,
        )

    return max(rows, key=rank)


def collapse_gemini_sessions(sessions: list[AiSession]) -> list[AiSession]:
    """Collapse rows that redundantly describe the same imported session.

    Some tools yield more than one row for a single session: a Gemini CLI
    session is read by both the per-turn hook (cumulative each turn) and the
    importer; a Codex session still being written is re-imported once per run
    as its rollout file grows (v5.2). Keep exactly one canonical row per
    resolvable session id (Gemini or Codex); pass everything else (other tools,
    rows without an id, distinct sessions) through untouched and in order.
    Idempotent. Read-time only — callers must not write the result back to the
    log. (Name retained for its existing callers; now tool-agnostic.)
    """
    groups: dict[str, list[AiSession]] = {}
    order: list[tuple[str | None, AiSession]] = []
    for s in sessions:
        key = _redundant_session_key(s)
        if key is None:
            order.append((None, s))
            continue
        if key not in groups:
            groups[key] = []
            order.append((key, s))  # reserve this position for the group
        groups[key].append(s)

    out: list[AiSession] = []
    emitted: set[str] = set()
    for key, s in order:
        if key is None:
            out.append(s)
        elif key not in emitted:
            emitted.add(key)
            out.append(_canonical_gemini_row(groups[key]))
    return out


def assign_unattributed_sessions(project_dir: Path, project: str) -> int:
    """Assign all effectively unattributed sessions to a project slug.

    The original ``s`` records remain immutable. Corrections are appended as
    ``a`` amendment records and folded by ``parse_sessions``.
    """
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        return 0

    with locked_file(log_path, "a+") as f:
        f.seek(0)
        content = f.read()
        amendment_lines = [
            _amendment_line(raw_line, project=project, attr_method="backfill")
            for raw_line, session in _effective_session_lines(content.splitlines())
            if session.project is None
        ]
        _append_lines(f, amendment_lines, content)
        return len(amendment_lines)


def find_project_dir(start: Path | None = None) -> Path | None:
    """Walk up from start (default CWD) to find a directory containing halyard.toml."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "halyard.toml").exists():
            return directory
    return None


def _parse_line(line: str) -> AiSession | None:
    parsed, _error = _parse_line_result(line)
    return parsed


def _to_naive_local(dt: datetime) -> datetime:
    """Normalise a parsed timestamp to naive local time.

    Logs are normally written with naive local timestamps, but a row
    may carry a tz offset (e.g. ``2026-…+00:00``) — from another tool
    or an older writer. The rest of Halyard compares against naive
    ``datetime.now()``; mixing aware/naive raises TypeError and would
    crash ``parse_sessions`` (every read path). Convert aware values to
    local wall-clock and drop tzinfo so all downstream math is uniform.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)


def _parse_line_result(line: str) -> tuple[AiSession | None, str | None]:
    parts = line.split()
    if len(parts) < 8 or parts[0] != "s":
        return None, "expected session line: s <start> <end> <tool> <model> <input> <output> <cost>"

    try:
        start = _to_naive_local(datetime.fromisoformat(parts[1]))
    except ValueError:
        return None, f"invalid start timestamp: {parts[1]}"

    try:
        end = _to_naive_local(datetime.fromisoformat(parts[2]))
    except ValueError:
        return None, f"invalid end timestamp: {parts[2]}"

    tool = parts[3]
    model = parts[4]
    if not tool:
        return None, "missing tool"
    if not model:
        return None, "missing model"

    try:
        input_tokens = int(parts[5])
    except ValueError:
        return None, f"invalid input_tokens: {parts[5]}"
    try:
        output_tokens = int(parts[6])
    except ValueError:
        return None, f"invalid output_tokens: {parts[6]}"
    try:
        cost_usd = float(parts[7])
    except ValueError:
        return None, f"invalid cost_usd: {parts[7]}"

    if input_tokens < 0:
        return None, f"input_tokens must be non-negative: {input_tokens}"
    if output_tokens < 0:
        return None, f"output_tokens must be non-negative: {output_tokens}"
    # v5.16/B1: ``float("inf")`` and ``float("nan")`` both parse cleanly and
    # both satisfy ``< 0 == False``, so a bare non-negativity check admits
    # them. A non-finite cost later raises ``decimal.InvalidOperation`` (inf)
    # or silently poisons every total to NaN in ``usage.sum_spend``. Reject
    # the whole line — a session with a non-finite cost is not trustworthy.
    if not math.isfinite(cost_usd) or cost_usd < 0:
        return None, f"cost_usd must be a finite non-negative number: {cost_usd}"

    session = AiSession(
        start=start,
        end=end,
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )

    for kv in parts[8:]:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        if spec := _FIELDS_BY_KEY.get(k):
            match spec.kind:
                case FieldKind.SAFE_FIELD | FieldKind.BILLING | FieldKind.BREAKDOWN:
                    setattr(session, spec.attr, v)
                case FieldKind.INT:
                    with suppress(ValueError):
                        setattr(session, spec.attr, int(v))
                case FieldKind.FLOAT_4:
                    with suppress(ValueError):
                        fv = float(v)
                        # v5.16/B1: skip non-finite (inf/nan) — keep the field
                        # at its default rather than admitting a poison value.
                        if math.isfinite(fv):
                            setattr(session, spec.attr, fv)
                case FieldKind.BOOL_LOWER:
                    setattr(session, spec.attr, v.lower() == "true")
                case FieldKind.TOKENS_AVAILABLE:
                    session.tokens_available = v.lower() != "false"
                case FieldKind.TAGS:
                    session.tags = [_decode_tag(t) for t in v.split(",") if t]
                case FieldKind.FREE_TEXT:
                    setattr(session, spec.attr, _decode_free_text(v))
        else:
            # v2.75: forward-compat passthrough. An unrecognized
            # token (newer Halyard / extending consumer) is
            # preserved verbatim instead of silently dropped, so
            # the line round-trips losslessly. Known keys are all
            # matched above, so this can never shadow a real
            # field. Only well-formed keys are kept so a corrupt
            # line can't turn `extra` into a junk sink.
            if _EXTRA_KEY_RE.match(k):
                session.extra[k] = _decode_free_text(v) if "%" in v else v

    # v2.24 backward-compat: promote legacy "branch:<name>" tag to branch field
    if session.branch is None and session.tags:
        for tag in session.tags:
            if tag.startswith("branch:"):
                session.branch = tag[len("branch:") :]
                break

    return session, None


def confirm_session_attributions(
    project_dir: Path,
    confirmations: list[tuple[str, str]],
) -> int:
    """Write confirmed project attributions into ai-sessions.log.

    Each entry in confirmations is (original_line, project_slug). The matching
    line receives an appended ``a`` amendment record.
    Returns the number of lines updated.
    """
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists() or not confirmations:
        return 0

    confirm_map = {line.rstrip(): project for line, project in confirmations}
    with locked_file(log_path, "a+") as f:
        f.seek(0)
        content = f.read()
        amendment_lines = []
        for raw_line, _session in _effective_session_lines(content.splitlines()):
            stripped = raw_line.rstrip()
            if stripped in confirm_map:
                amendment_lines.append(
                    _amendment_line(
                        stripped,
                        project=confirm_map[stripped],
                        attr_method="manual",
                    )
                )
        _append_lines(f, amendment_lines, content)
        return len(amendment_lines)


def backfill_window(
    project_dir: Path,
    start: datetime,
    end: datetime,
    project: str,
    *,
    dry_run: bool = False,
) -> int:
    """Attribute unattributed sessions in [start, end) to project.

    Sanctioned attribution correction — only project= metadata is added,
    no captured data is discarded. Returns the number of sessions attributed
    (or that would be, in dry_run mode).
    """
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        return 0

    with locked_file(log_path, "a+") as f:
        f.seek(0)
        content = f.read()
        amendment_lines = [
            _amendment_line(raw_line, project=project, attr_method="backfill")
            for raw_line, session in _effective_session_lines(content.splitlines())
            if session.project is None and start <= session.start < end
        ]
        if not dry_run:
            _append_lines(f, amendment_lines, content)
        return len(amendment_lines)


def _effective_session_lines(lines: list[str]) -> list[tuple[str, AiSession]]:
    """Return raw ``s`` lines paired with sessions after folded amendments."""
    entries: list[tuple[str, str, AiSession]] = []
    amendments_by_hash: dict[str, list[Amendment]] = defaultdict(list)
    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("s "):
            session, error = _parse_line_result(line)
            if session is not None:
                entries.append((line, session_hash(line), session))
            elif error is not None:
                _write_quarantine(line, error)
        elif line.startswith("a "):
            amendment = parse_amendment(line)
            if amendment is not None:
                amendments_by_hash[amendment.session_hash].append(amendment)

    result: list[tuple[str, AiSession]] = []
    for raw_line, h, session in entries:
        for amendment in amendments_by_hash.get(h, []):
            session.apply_amendment(amendment)
        result.append((raw_line, session))
    return result


def _amendment_line(raw_session_line: str, *, project: str, attr_method: str) -> str:
    h = session_hash(raw_session_line)
    # Defence in depth: even though callers validate the slug, the
    # amendment record is space- and key=value-delimited, so a stray
    # space/'=' in project would forge extra tokens. _safe_field
    # neutralises whitespace and '='.
    return f"a {h} project={_safe_field(project)} attr_method={_safe_field(attr_method)}"


def _append_lines(f: IO[str], lines: list[str], existing_content: str) -> None:
    if not lines:
        return
    if existing_content and not existing_content.endswith("\n"):
        f.write("\n")
    for line in lines:
        f.write(line + "\n")


def _is_assignable_session_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("s ") and " project=" not in stripped


def read_active_project() -> str | None:
    """Return the active project slug from the Hub or ~/.halyard/active.

    This is the single canonical implementation.  All three collectors import
    this function so that the read logic is never duplicated.  The file is
    written atomically by the dashboard (tmp-then-rename), so a partial read
    will simply find no ``slug=`` line and return None — a safe degradation.

    Goes through :func:`halyard.state_integrity.read_global_trusted_state`
    so a pre-existing sidecar is honored even when the resolved mode is
    ``off`` — without this, a tampered ``~/.halyard/active`` would be
    silently accepted in the default runtime. On IntegrityError the
    function logs and returns None rather than crashing every collector
    hook.
    """
    from halyard.state_integrity import IntegrityError, read_global_trusted_state

    try:
        from halyard.hub_client import read_state

        state = read_state()
        if state is not None:
            project = state.get("project")
            return project if isinstance(project, str) and project else None
    except Exception as exc:
        _log_error("read_active_project: hub state read failed", exc)

    active = Path.home() / ".halyard" / "active"
    try:
        content = read_global_trusted_state(active)
    except IntegrityError as exc:
        _log_error("read_active_project: integrity verification failed", exc)
        return None
    if content is None:
        return None
    for line in content.splitlines():
        if line.startswith("slug="):
            return line[5:]
    return None


def write_unattributed_session(session: AiSession) -> Path:
    """Append a recoverable session to the per-user unattributed log."""
    path = unattributed_log_path()
    with locked_file(path, "a") as f:
        f.write(session.to_log_line() + "\n")
    return path


def unattributed_log_path() -> Path:
    """Return the per-user unattributed session log path."""
    return Path.home() / ".halyard" / "unattributed.log"


def unattributed_log_count() -> int:
    """Return the number of session records in ~/.halyard/unattributed.log."""
    path = unattributed_log_path()
    if not path.exists():
        return 0
    count = 0
    with read_locked_file(path) as fh:
        for raw_line in fh:
            if raw_line.strip().startswith("s "):
                count += 1
    return count


def maybe_show_dashboard_hint() -> None:
    """Print a one-time hint to open the dashboard after the first captured session."""
    import sys

    flag = Path.home() / ".halyard" / ".dashboard-hint-shown"
    if flag.exists():
        # Pirate day easter egg — greet on every stop on September 19
        try:
            from halyard.easter_eggs import is_pirate_day

            if is_pirate_day():
                print(
                    "[halyard] Arrr! The captain's log be updated. Sail on, ye code-slinger!",
                    file=sys.stderr,
                )
        except Exception:  # easter eggs must never suppress the dashboard hint
            pass
        return
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()
    hint = "[halyard] First session captured! View it live: halyard dashboard --open"
    try:
        from halyard.easter_eggs import is_pirate_day

        if is_pirate_day():
            hint = "[halyard] First watch logged, matey! Chart yer course: halyard dashboard --open"
    except Exception:  # easter eggs must never suppress the first-session hint
        pass
    print(hint, file=sys.stderr)


def _write_quarantine(original_line: str, error: str) -> Path:
    path = Path.home() / ".halyard" / "quarantine.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    # M-5: strip newlines from the error string so a crafted log line cannot
    # inject additional "; error=..." header lines into quarantine.log.
    safe_error = error.replace("\n", " ").replace("\r", "")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"; error={safe_error}\n")
        f.write(original_line.rstrip("\n") + "\n")
    return path
