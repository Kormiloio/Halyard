"""v3.11 — scheduled importer (LaunchAgent) plist generation + dedup."""

from __future__ import annotations

import plistlib
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from halyard import import_timer
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.cli_importers import run_gemini_import


def test_plist_runs_import_all_on_interval() -> None:
    xml = import_timer._plist("/abs/path/halyard", 1800)
    data = plistlib.loads(xml.encode())
    assert data["Label"] == "io.kormilo.halyard.import"
    assert data["ProgramArguments"] == ["/abs/path/halyard", "import-all"]
    assert data["StartInterval"] == 1800
    assert data["RunAtLoad"] is True


def test_plist_escapes_executable_path() -> None:
    xml = import_timer._plist("/weird/<path> & co/halyard", 600)
    data = plistlib.loads(xml.encode())  # must remain valid XML
    assert data["ProgramArguments"][0] == "/weird/<path> & co/halyard"
    assert data["StartInterval"] == 600


class _Summary:
    """Minimal stand-in for GeminiSessionSummary."""

    def __init__(self, sid: str) -> None:
        self.session_id = sid
        now = datetime.now()
        self.start = now - timedelta(minutes=5)
        self.end = now
        self.dominant_model = "gemini-3-flash-preview"
        self.total_input = 100
        self.total_output = 50
        self.total_cache = 0
        self.total_tool_calls = 0
        self.total_tool_errors = 0


def test_gemini_import_dedup_is_cwd_independent(tmp_path: Path) -> None:
    """Regression: a session already recorded in its TARGET project log must be
    skipped even when the importer runs from an unrelated cwd (the launchd bug
    that re-imported on every scheduled run, creating duplicates)."""
    sid = "feed0001-0000-0000-0000-000000000000"

    target = tmp_path / "projA"
    target.mkdir()
    (target / "halyard.toml").write_text("[business]\n")
    (target / AI_LOG_FILENAME).write_text(HEADER)
    # Already imported into the target log.
    append_session(
        target,
        AiSession(
            start=datetime.now() - timedelta(minutes=5),
            end=datetime.now(),
            tool="gemini-cli",
            model="gemini-3-flash-preview",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0,
            source="import",
            job_id=f"gemini:{sid}",
        ),
    )

    unrelated = tmp_path / "projB"  # simulates a different working directory
    unrelated.mkdir()
    fake = tmp_path / "gemtmp" / "projA-slug" / "chats" / "session-x.jsonl"

    with (
        patch("halyard.collectors.gemini_history.find_all_session_files", return_value=[fake]),
        patch("halyard.collectors.gemini_history.parse_session_file", return_value=_Summary(sid)),
        patch("halyard.collectors.gemini_history.project_dir_for_slug", return_value=target),
        patch("halyard.hub.find_hub", return_value=None),
        patch("halyard.ai_log.find_project_dir", return_value=unrelated),
    ):
        n = run_gemini_import(dry_run=False, all_projects=True, quiet=True)

    assert n == 0  # already imported → skipped, not re-added
    rows = [s for s in parse_sessions(target) if s.job_id == f"gemini:{sid}"]
    assert len(rows) == 1  # no duplicate created
