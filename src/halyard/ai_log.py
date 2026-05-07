"""AI session log — writer, parser, and project discovery for ai-sessions.log."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SPEC_URL = "https://halyard.dev/spec/ai-sessions/v1"
HEADER = (
    f"; Halyard AI session log — spec: {SPEC_URL}\n"
    "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd> [key=value ...]\n"
)
AI_LOG_FILENAME = "ai-sessions.log"


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

    @classmethod
    def from_log_line(cls, line: str) -> AiSession | None:
        """Parse and validate one session line, quarantining malformed records."""
        parsed, error = _parse_line_result(line)
        if error is not None:
            _write_quarantine(line, error)
        return parsed

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
            self.tool,
            self.model,
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
        if self.tags:
            kvs.append(f"tags={','.join(self.tags)}")
        if self.note:
            kvs.append(f"note={self.note.replace(' ', '_')}")
        return " ".join(parts + kvs)


def append_session(project_dir: Path, session: AiSession) -> None:
    log_path = project_dir / AI_LOG_FILENAME
    with log_path.open("a") as f:
        f.write(session.to_log_line() + "\n")


def parse_sessions(project_dir: Path) -> list[AiSession]:
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        return []
    sessions = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parsed = AiSession.from_log_line(line)
        if parsed is not None:
            sessions.append(parsed)
    return sessions


def assign_unattributed_sessions(project_dir: Path, project: str) -> int:
    """Assign all session lines missing `project=` to a project slug."""
    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        return 0

    changed = 0
    lines = []
    for line in log_path.read_text().splitlines():
        if _is_assignable_session_line(line):
            lines.append(f"{line} project={project}")
            changed += 1
        else:
            lines.append(line)

    if changed:
        log_path.write_text("\n".join(lines) + "\n")

    return changed


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
            case "tags":
                session.tags = v.split(",")
            case "note":
                session.note = v.replace("_", " ")

    return session, None


def _is_assignable_session_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("s ") and " project=" not in stripped


def write_unattributed_session(session: AiSession) -> Path:
    """Append a recoverable session to the per-user unattributed log."""
    path = unattributed_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
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


def _write_quarantine(original_line: str, error: str) -> Path:
    path = Path.home() / ".halyard" / "quarantine.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"; error={error}\n")
        f.write(original_line.rstrip("\n") + "\n")
    return path
