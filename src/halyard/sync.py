"""Halyard sync — push local ai-sessions.log records into the org store.

Push-only: contributors decide when to sync.  The local log is never modified.
Re-syncing the same records is idempotent (deduplicated by line hash).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession
from halyard.org import normalize_session, read_org_config
from halyard.org_store import ORG_DB_FILENAME, insert_sessions, record_sync

ORG_TOML_FILENAME = "org.toml"


@dataclass
class SyncResult:
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.inserted + self.skipped


def sync_project(project_dir: Path, hub_dir: Path | None = None) -> SyncResult:
    """Sync all sessions from project_dir's ai-sessions.log into the org store.

    hub_dir defaults to project_dir when not provided (single-project setup).
    The org store (org.db) and org.toml are both expected at hub_dir.
    """
    effective_hub = hub_dir or project_dir
    result = SyncResult()

    org_config = read_org_config(effective_hub)
    if org_config is None:
        result.errors.append(
            f"org.toml not found at {effective_hub} — run `halyard org-init` to create it"
        )
        return result

    log_path = project_dir / AI_LOG_FILENAME
    if not log_path.exists():
        result.errors.append(f"No ai-sessions.log at {project_dir}")
        return result

    db_path = effective_hub / ORG_DB_FILENAME
    raw_lines, sessions = _read_log_with_lines(log_path)

    org_sessions = []
    for raw, session in zip(raw_lines, sessions, strict=False):
        try:
            org_sessions.append(normalize_session(raw, session, org_config))
        except Exception as exc:
            result.errors.append(f"Normalization error for line '{raw[:60]}': {exc}")

    inserted, skipped = insert_sessions(db_path, org_sessions)
    result.inserted = inserted
    result.skipped = skipped

    import getpass

    try:
        synced_by = getpass.getuser()
    except Exception:
        synced_by = "unknown"
    record_sync(
        db_path,
        org_id=org_config.org.id,
        synced_by=synced_by,
        inserted=inserted,
        skipped=skipped,
        source_path=str(project_dir),
    )
    return result


def sync_hub(hub_dir: Path) -> SyncResult:
    """Sync all ai-sessions.log files found under hub_dir recursively."""
    combined = SyncResult()
    for log_path in hub_dir.rglob(AI_LOG_FILENAME):
        project_dir = log_path.parent
        sub = sync_project(project_dir, hub_dir=hub_dir)
        combined.inserted += sub.inserted
        combined.skipped += sub.skipped
        combined.errors.extend(sub.errors)
    return combined


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_log_with_lines(log_path: Path) -> tuple[list[str], list[AiSession]]:
    """Read log lines and their parsed AiSession in parallel."""
    raw_lines: list[str] = []
    sessions: list[AiSession] = []
    for line in log_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        session = AiSession.from_log_line(stripped)
        if session is not None:
            raw_lines.append(stripped)
            sessions.append(session)
    return raw_lines, sessions
