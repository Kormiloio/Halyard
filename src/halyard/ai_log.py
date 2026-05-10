"""AI session log — writer, parser, and project discovery for ai-sessions.log."""

from __future__ import annotations

import fcntl
import hashlib
import re
import threading
import traceback
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

SPEC_URL = "https://halyard.dev/spec/ai-sessions/v1"
HEADER = (
    f"; Halyard AI session log — spec: {SPEC_URL}\n"
    "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]\n"
)
AI_LOG_FILENAME = "ai-sessions.log"
_HALYARD_LOG = Path.home() / ".halyard" / "halyard.log"

# Regex matching characters that would break the space-delimited log line format.
# Used to sanitize positional fields (tool, model) before writing.
_UNSAFE_FIELD_RE = re.compile(r"[\s=]")
_PATH_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


# ---------------------------------------------------------------------------
# v2.17 Section 6.1: Error visibility helper
# ---------------------------------------------------------------------------


def _log_error(msg: str, exc: Exception) -> None:
    """Append a timestamped traceback entry to ~/.halyard/halyard.log.

    Never raises — if the log write itself fails the error is silently dropped
    (we cannot log the logger failure).
    """
    try:
        _HALYARD_LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=UTC).isoformat(timespec="seconds")
        tb = traceback.format_exc()
        entry = f"[{ts}] {msg}: {type(exc).__name__}: {exc}\n{tb}\n"
        with _HALYARD_LOG.open("a") as fh:
            fh.write(entry)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# v2.17 task 1.1-1.2: File locking primitive
# ---------------------------------------------------------------------------


@contextmanager
def locked_file(path: Path, mode: str) -> Generator[IO[str], None, None]:
    """Open *path* in *mode* with an exclusive flock held for the duration.

    The parent directory is created if absent.  flock is advisory but
    cooperative — all Halyard writers use this helper, so it is sufficient to
    prevent concurrent appends from interleaving writes.

    Read paths do not lock: ``parse_sessions`` is allowed to see any consistent
    prefix of the file; the next refresh picks up any session that landed
    mid-read.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        thread_lock = _PATH_LOCKS.setdefault(lock_key, threading.RLock())
    with thread_lock, open(path, mode) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# v2.17 task 2.1-2.3: Amendment record support
# ---------------------------------------------------------------------------


def session_hash(line: str) -> str:
    """Return the first 12 hex chars of SHA-256(stripped line).

    The hash is computed on the raw ``s`` line *before* any amendments so
    ``a`` records always reference the original session, even if amendments
    later change its semantic meaning.
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
    code_added: int | None = None
    code_removed: int | None = None
    model_breakdown: str | None = None  # compact: "model-a:3|model-b:1"
    resume_command: str | None = None
    # v2.24 outcome metadata
    branch: str | None = None  # git branch at session close; trust: captured
    commit_count: int | None = None  # commits in session window; trust: captured
    pr_ref: str | None = None  # e.g. "owner/repo#42"; written by outcome sync
    pr_state: str | None = None  # merged | closed | open | none
    outcome_resolved_at: str | None = None  # ISO timestamp when pr_ref was resolved

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
                self.note = value.replace("_", " ")
            elif key == "pr_ref":
                self.pr_ref = value
            elif key == "pr_state":
                self.pr_state = value
            elif key == "outcome_resolved_at":
                self.outcome_resolved_at = value

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
        if self.project:
            kvs.append(f"project={self.project}")
        if self.user:
            kvs.append(f"user={self.user}")
        if self.cache_read is not None:
            kvs.append(f"cache_read={self.cache_read}")
        if self.cache_write is not None:
            kvs.append(f"cache_write={self.cache_write}")
        if not self.tokens_available:
            kvs.append("tokens_available=false")
        if self.billing != "api":
            kvs.append(f"billing={self.billing}")
        if self.credits is not None:
            kvs.append(f"credits={self.credits:.4f}")
        if self.job_id:
            kvs.append(f"job_id={self.job_id}")
        if self.source:
            kvs.append(f"source={self.source}")
        if self.attr_method:
            kvs.append(f"attr_method={self.attr_method}")
        if self.tags:
            kvs.append(f"tags={','.join(self.tags)}")
        if self.note:
            # M-2 encoding contract: spaces→underscores, CR/LF/tab stripped.
            # Limitation: literal underscores in the original note are
            # indistinguishable from encoded spaces after round-trip.
            # Future format versions should use percent-encoding.
            note_safe = (
                self.note.replace("\n", " ").replace("\r", "").replace("\t", " ").replace(" ", "_")
            )
            kvs.append(f"note={note_safe}")
        if self.session_id:
            safe_sid = self.session_id.replace(" ", "")
            kvs.append(f"session_id={safe_sid}")
        if self.tool_calls is not None:
            kvs.append(f"tool_calls={self.tool_calls}")
        if self.tool_errors is not None:
            kvs.append(f"tool_errors={self.tool_errors}")
        if self.wall_seconds is not None:
            kvs.append(f"wall_seconds={self.wall_seconds}")
        if self.agent_active_seconds is not None:
            kvs.append(f"agent_active_seconds={self.agent_active_seconds}")
        if self.code_added is not None:
            kvs.append(f"code_added={self.code_added}")
        if self.code_removed is not None:
            kvs.append(f"code_removed={self.code_removed}")
        if self.model_breakdown:
            kvs.append(f"model_breakdown={self.model_breakdown}")
        if self.resume_command:
            # M-2 encoding contract: spaces→underscores, CR/LF stripped.
            # Same underscore ambiguity as note — see comment above.
            safe_cmd = self.resume_command.replace(" ", "_").replace("\n", "").replace("\r", "")
            kvs.append(f"resume_command={safe_cmd}")
        if self.branch:
            kvs.append(f"branch={self.branch}")
        if self.commit_count is not None:
            kvs.append(f"commit_count={self.commit_count}")
        if self.pr_ref:
            kvs.append(f"pr_ref={self.pr_ref}")
        if self.pr_state:
            kvs.append(f"pr_state={self.pr_state}")
        if self.outcome_resolved_at:
            kvs.append(f"outcome_resolved_at={self.outcome_resolved_at}")
        return " ".join(parts + kvs)


def append_session(project_dir: Path, session: AiSession) -> None:
    # v2.17 task 4.1: use locked_file so concurrent appenders never interleave
    log_path = project_dir / AI_LOG_FILENAME
    with locked_file(log_path, "a") as f:
        f.write(session.to_log_line() + "\n")


def parse_sessions(project_dir: Path) -> list[AiSession]:
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
    amendments_by_hash: dict[str, list[Amendment]] = defaultdict(list)

    for raw_line in log_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("s "):
            parsed = AiSession.from_log_line(line)
            if parsed is not None:
                h = session_hash(line)
                if h not in sessions_by_hash:
                    sessions_by_hash[h] = parsed
                sessions.append(parsed)
        elif line.startswith("a "):
            amendment = parse_amendment(line)
            if amendment is not None:
                amendments_by_hash[amendment.session_hash].append(amendment)

    # Apply amendments in file order; last-write-wins per key.
    # Only the first-occurrence object per hash is amended.
    for h, session in sessions_by_hash.items():
        for amendment in amendments_by_hash.get(h, []):
            session.apply_amendment(amendment)

    return sessions


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


def _parse_line_result(line: str) -> tuple[AiSession | None, str | None]:
    parts = line.split()
    if len(parts) < 8 or parts[0] != "s":
        return None, "expected session line: s <start> <end> <tool> <model> <input> <output> <cost>"

    try:
        start = datetime.fromisoformat(parts[1])
    except ValueError:
        return None, f"invalid start timestamp: {parts[1]}"

    try:
        end = datetime.fromisoformat(parts[2])
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
    if cost_usd < 0:
        return None, f"cost_usd must be non-negative: {cost_usd}"

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
        match k:
            case "project":
                session.project = v
            case "user":
                session.user = v
            case "cache_read":
                with suppress(ValueError):
                    session.cache_read = int(v)
            case "cache_write":
                with suppress(ValueError):
                    session.cache_write = int(v)
            case "tokens_available":
                session.tokens_available = v.lower() != "false"
            case "billing":
                session.billing = v
            case "credits":
                with suppress(ValueError):
                    session.credits = float(v)
            case "job_id":
                session.job_id = v
            case "source":
                session.source = v
            case "attr_method":
                session.attr_method = v
            case "tags":
                session.tags = v.split(",")
            case "note":
                session.note = v.replace("_", " ")
            case "session_id":
                session.session_id = v
            case "tool_calls":
                with suppress(ValueError):
                    session.tool_calls = int(v)
            case "tool_errors":
                with suppress(ValueError):
                    session.tool_errors = int(v)
            case "wall_seconds":
                with suppress(ValueError):
                    session.wall_seconds = int(v)
            case "agent_active_seconds":
                with suppress(ValueError):
                    session.agent_active_seconds = int(v)
            case "code_added":
                with suppress(ValueError):
                    session.code_added = int(v)
            case "code_removed":
                with suppress(ValueError):
                    session.code_removed = int(v)
            case "model_breakdown":
                session.model_breakdown = v
            case "resume_command":
                session.resume_command = v.replace("_", " ")
            case "branch":
                session.branch = v
            case "commit_count":
                with suppress(ValueError):
                    session.commit_count = int(v)
            case "pr_ref":
                session.pr_ref = v
            case "pr_state":
                session.pr_state = v
            case "outcome_resolved_at":
                session.outcome_resolved_at = v

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
            session = _parse_line(line)
            if session is not None:
                entries.append((line, session_hash(line), session))
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
    return f"a {h} project={project} attr_method={attr_method}"


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
    """Return the active project slug from ~/.halyard/active, or None if not set.

    This is the single canonical implementation.  All three collectors import
    this function so that the read logic is never duplicated.  The file is
    written atomically by the dashboard (tmp-then-rename), so a partial read
    will simply find no ``slug=`` line and return None — a safe degradation.
    """
    active = Path.home() / ".halyard" / "active"
    if not active.exists():
        return None
    for line in active.read_text().splitlines():
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
    return sum(1 for line in path.read_text().splitlines() if line.strip().startswith("s "))


def maybe_show_dashboard_hint() -> None:
    """Print a one-time hint to open the dashboard after the first captured session."""
    import sys

    flag = Path.home() / ".halyard" / ".dashboard-hint-shown"
    if flag.exists():
        return
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()
    print(
        "[halyard] First session captured! View it live: halyard dashboard --open",
        file=sys.stderr,
    )


def _write_quarantine(original_line: str, error: str) -> Path:
    path = Path.home() / ".halyard" / "quarantine.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    # M-5: strip newlines from the error string so a crafted log line cannot
    # inject additional "; error=..." header lines into quarantine.log.
    safe_error = error.replace("\n", " ").replace("\r", "")
    with path.open("a") as f:
        f.write(f"; error={safe_error}\n")
        f.write(original_line.rstrip("\n") + "\n")
    return path
