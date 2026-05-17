"""In-memory session state for the Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from halyard.ai_log import AiSession, parse_amendment, parse_sessions, session_hash

TimeWindow = Literal["today", "week", "month", "all"]

# The live feed only ever displays the most recent ~50 sessions; retaining
# every session for a long-running `halyard tui` against an actively
# appended log grows unbounded and makes every refresh re-sort the lot.
_MAX_RETAINED_SESSIONS = 500


@dataclass
class SessionStore:
    """Load and tail an ai-sessions.log file."""

    log_path: Path
    sessions: list[AiSession] = field(default_factory=list)
    _offset: int = 0

    def load(self) -> None:
        """Parse the full log on startup."""
        self.sessions = _read_sessions_file(self.log_path)[:_MAX_RETAINED_SESSIONS]
        self._offset = self.log_path.stat().st_size if self.log_path.exists() else 0

    def read_new_lines(self) -> list[AiSession]:
        """Read appended lines since the last offset."""
        if not self.log_path.exists():
            return []
        size = self.log_path.stat().st_size
        if size < self._offset:
            self._offset = 0
            self.sessions = []
        with self.log_path.open() as handle:
            handle.seek(self._offset)
            lines = handle.read().splitlines()
            self._offset = handle.tell()

        parsed: list[AiSession] = []
        for line in lines:
            if line.startswith("a "):
                # `a ` (amendment) records are written routinely by
                # `outcome sync`/evidence. Apply incrementally instead
                # of forcing a full re-parse, which would defeat the
                # tail on every sync. Fall back to a full reload only
                # if the amendment targets a session not in memory
                # (rare — sync amends recent sessions).
                if not self._apply_amendment_line(line, parsed):
                    self.load()
                    return []
                continue
            session = _parse_session_line(line)
            if session is not None:
                parsed.append(session)
        if parsed:
            self.sessions = sorted(
                [*parsed, *self.sessions],
                key=lambda s: s.start,
                reverse=True,
            )[:_MAX_RETAINED_SESSIONS]
        return parsed

    def _apply_amendment_line(self, line: str, pending: list[AiSession]) -> bool:
        """Apply one `a ` record to an in-memory session.

        Returns True if applied (or the amendment was unparseable and
        can be safely ignored), False if it targets a session not in
        memory (caller should fall back to a full reload).
        """
        amendment = parse_amendment(line)
        if amendment is None:
            return True
        for session in (*pending, *self.sessions):
            if session._raw_hash == amendment.session_hash:
                session.apply_amendment(amendment)
                return True
        return False

    def filter(
        self,
        *,
        time_window: TimeWindow = "month",
        project_scope: str | None = None,
        branch: str | None = None,
        now: datetime | None = None,
    ) -> list[AiSession]:
        """Return sessions matching the active TUI filters."""
        clock = now or datetime.now()
        result = list(self.sessions)
        if time_window != "all":
            result = [s for s in result if _in_window(s.start, time_window, clock)]
        if project_scope is not None:
            result = [s for s in result if s.project == project_scope]
        if branch is not None:
            tag = f"branch:{branch}"
            result = [s for s in result if tag in s.tags]
        return result

    def branches(self, sessions: list[AiSession] | None = None) -> list[str]:
        """Return branch tags sorted by most recent session."""
        seen: dict[str, datetime] = {}
        for session in sessions or self.sessions:
            for tag in session.tags:
                if not tag.startswith("branch:"):
                    continue
                branch = tag.removeprefix("branch:")
                if branch not in seen or session.start > seen[branch]:
                    seen[branch] = session.start
        sorted_branches = sorted(seen.items(), key=lambda item: item[1], reverse=True)
        return [branch for branch, _start in sorted_branches]


def _read_sessions_file(log_path: Path) -> list[AiSession]:
    if not log_path.exists():
        return []
    return sorted(parse_sessions(log_path.parent), key=lambda s: s.start, reverse=True)


def _parse_session_line(line: str) -> AiSession | None:
    if not line or line.startswith(";"):
        return None
    session = AiSession.from_log_line(line)
    if session is not None and line.startswith("s "):
        # Tag the in-memory object with its content hash so a later
        # `a ` amendment in the same tail can be matched incrementally
        # (mirrors what parse_sessions does at the read chokepoint).
        session._raw_hash = session_hash(line)
    return session


def _in_window(start: datetime, window: TimeWindow, now: datetime) -> bool:
    if window == "today":
        return start.date() == now.date()
    if window == "week":
        return start >= now - timedelta(days=7)
    if window == "month":
        return start.year == now.year and start.month == now.month
    return True
