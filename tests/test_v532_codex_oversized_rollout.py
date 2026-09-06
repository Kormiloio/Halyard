"""v5.32 — a whole-file cap made large Codex rollouts permanently uncapturable.

`_iter_jsonl_lines` capped reads at 25 MB of *whole file* and yielded nothing
above it, so `_parse_session_file` returned None and the caller skipped the
session — silently. The reader is a streaming generator, so that cap never
bounded memory; it only set the size at which a session fell off a cliff.
Long agentic rollouts (813 MB observed) were therefore never importable, and
re-running the importer could not help.

These tests pin the bounds. The 813 MB end-to-end evidence lives in the
proposal — it is not something a suite should try to reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halyard.collectors import codex_app


def _rollout_line(text: str) -> str:
    return json.dumps({"type": "message", "payload": {"text": text}}) + "\n"


def test_a_file_over_the_old_25mb_cap_is_read(tmp_path: Path) -> None:
    """The regression: 25 MB used to yield nothing at all."""
    path = tmp_path / "rollout.jsonl"
    chunk = _rollout_line("x" * 100_000)
    with path.open("w", encoding="utf-8") as fh:
        for _ in range(300):  # ~30 MB, comfortably past the old cap
            fh.write(chunk)

    assert path.stat().st_size > 25 * 1024 * 1024
    assert sum(1 for _ in codex_app._iter_jsonl_lines(path)) == 300


def test_an_over_long_line_is_skipped_but_the_file_keeps_reading(tmp_path: Path) -> None:
    """One pathological line must cost one line, not the whole session."""
    path = tmp_path / "rollout.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(_rollout_line("ok-before"))
        fh.write("y" * (codex_app._MAX_ROLLOUT_LINE_BYTES + 10) + "\n")
        fh.write(_rollout_line("ok-after"))

    lines = list(codex_app._iter_jsonl_lines(path))
    assert len(lines) == 2
    assert "ok-before" in lines[0]
    assert "ok-after" in lines[1]


def test_the_total_budget_truncates_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over budget stops the read — and must not do it silently.

    The silence is what let the original defect run unnoticed.
    """
    # v5.34: the implementation moved to collectors.iter_bounded_lines, so
    # the budget and the truncation notice are patched there.
    monkeypatch.setattr(codex_app, "_MAX_ROLLOUT_BYTES", 5_000)
    noted: list[str] = []
    monkeypatch.setattr(
        "halyard.collectors._note_truncated", lambda p, seen, label: noted.append(p.name)
    )

    path = tmp_path / "rollout.jsonl"
    line = _rollout_line("z" * 500)
    with path.open("w", encoding="utf-8") as fh:
        for _ in range(100):
            fh.write(line)

    lines = list(codex_app._iter_jsonl_lines(path))
    assert 0 < len(lines) < 100, "should keep what it read, not all and not nothing"
    assert noted == ["rollout.jsonl"], "truncation must be reported"


def test_truncation_reaches_the_diagnostic_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_note_truncated goes through the established _log_error channel."""
    logged: list[str] = []
    monkeypatch.setattr("halyard.ai_log._log_error", lambda msg, exc: logged.append(msg))

    from halyard.collectors import _note_truncated

    _note_truncated(tmp_path / "big.jsonl", 12_345, "codex rollout")

    assert logged and "big.jsonl" in logged[0]
    assert "12345" in logged[0]


def test_symlinks_are_still_refused(tmp_path: Path) -> None:
    """Unchanged by this change — a bounded read still rejects symlinks."""
    real = tmp_path / "real.jsonl"
    real.write_text(_rollout_line("hello"), encoding="utf-8")
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)

    assert list(codex_app._iter_jsonl_lines(link)) == []


def test_the_budget_is_sized_above_real_rollouts() -> None:
    """1 GiB, not 25 MB: real rollouts reach hundreds of MB.

    The observed file that motivated this change was 813 MB; gemini_history
    widened for an 825 MB one. A budget below those is the original bug.
    """
    assert codex_app._MAX_ROLLOUT_BYTES >= 1024 * 1024 * 1024
    assert codex_app._MAX_ROLLOUT_LINE_BYTES < codex_app._MAX_ROLLOUT_BYTES
