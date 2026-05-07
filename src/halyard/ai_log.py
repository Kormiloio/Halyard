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
        parsed = _parse_line(line)
        if parsed is not None:
            sessions.append(parsed)
    return sessions


def find_project_dir(start: Path | None = None) -> Path | None:
    """Walk up from start (default CWD) to find a directory containing halyard.toml."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "halyard.toml").exists():
            return directory
    return None


def _parse_line(line: str) -> AiSession | None:
    parts = line.split()
    if len(parts) < 8 or parts[0] != "s":
        return None
    try:
        start = datetime.fromisoformat(parts[1])
        end = datetime.fromisoformat(parts[2])
        tool = parts[3]
        model = parts[4]
        input_tokens = int(parts[5])
        output_tokens = int(parts[6])
        cost_usd = float(parts[7])
    except (ValueError, IndexError):
        return None

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

    return session
