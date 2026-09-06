"""v5.34 — the whole-file cap that silently dropped large Codex rollouts was everywhere.

v5.32 fixed it for Codex after an 813 MB file was found permanently
unreadable. The same shape existed in three more collectors and none of them
warned on skip. It was not theoretical: `copilot.py` capped at 50 MB while a
135.9 MB Copilot chat sat on disk, silently skipped, with `halyard doctor`
reporting Copilot history present but unimported.

The readers stream line by line, so a whole-file cap bounds nothing about
memory — it only sets the size at which a session becomes uncapturable, and
it fails precisely where it costs most.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from halyard.collectors import (
    MAX_TRANSCRIPT_BYTES,
    MAX_TRANSCRIPT_LINE_BYTES,
    antigravity,
    claude_code,
    codex_app,
    copilot,
    iter_bounded_lines,
)


def _write(path: Path, lines: int, width: int = 100) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for i in range(lines):
            fh.write(f'{{"i":{i},"pad":"{"x" * width}"}}\n')
    return path


# --- the shared reader ------------------------------------------------


def test_a_file_past_the_old_caps_is_read(tmp_path: Path) -> None:
    """The regression: 25-50 MB used to yield nothing at all."""
    path = _write(tmp_path / "big.jsonl", 300, width=100_000)  # ~30 MB
    assert path.stat().st_size > 25 * 1024 * 1024
    assert sum(1 for _ in iter_bounded_lines(path)) == 300


def test_an_over_long_line_is_skipped_but_reading_continues(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text("first\n" + "y" * 5_000 + "\nlast\n", encoding="utf-8")
    got = [line.strip() for line in iter_bounded_lines(path, max_line_bytes=1_000)]
    assert got == ["first", "last"]


def test_over_budget_keeps_what_it_read(tmp_path: Path) -> None:
    """Truncate, don't discard — partial data beats none."""
    path = _write(tmp_path / "t.jsonl", 100)
    got = list(iter_bounded_lines(path, max_total_bytes=2_000))
    assert 0 < len(got) < 100


def test_truncation_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence is what let the Codex case run for weeks."""
    logged: list[str] = []
    monkeypatch.setattr("halyard.ai_log._log_error", lambda msg, exc: logged.append(msg))
    path = _write(tmp_path / "t.jsonl", 100)

    list(iter_bounded_lines(path, max_total_bytes=2_000, label="unit test"))

    assert logged and "unit test" in logged[0] and "t.jsonl" in logged[0]


def test_symlinks_are_refused(tmp_path: Path) -> None:
    real = _write(tmp_path / "real.jsonl", 3)
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    assert list(iter_bounded_lines(link)) == []


def test_a_missing_file_yields_nothing(tmp_path: Path) -> None:
    assert list(iter_bounded_lines(tmp_path / "nope.jsonl")) == []


def test_the_budget_is_sized_above_real_transcripts() -> None:
    """1 GiB, not 25 MB. Observed: an 813 MB Codex rollout, a 135.9 MB
    Copilot chat, and an 825 MB Gemini rollout in gemini_history."""
    assert MAX_TRANSCRIPT_BYTES >= 1024 * 1024 * 1024
    assert MAX_TRANSCRIPT_LINE_BYTES < MAX_TRANSCRIPT_BYTES


# --- no collector keeps a whole-file cap ------------------------------


@pytest.mark.parametrize("module", [copilot, claude_code, antigravity, codex_app])
def test_no_collector_rejects_a_file_on_total_size(module) -> None:
    """A whole-file `st_size >` rejection is the defect this change removes.

    Pinned as source inspection because the failure mode is a *silent*
    early return: nothing observable happens, which is exactly why four
    copies of it survived. A future collector re-adding one would look
    correct in every behavioural test.
    """
    src = inspect.getsource(module)
    assert "st_size >" not in src, (
        f"{module.__name__} re-introduced a whole-file size rejection; "
        "use iter_bounded_lines so large sessions are bounded, not dropped"
    )


@pytest.mark.parametrize("module", [copilot, claude_code, antigravity, codex_app])
def test_every_collector_streams_through_the_shared_reader(module) -> None:
    """One implementation, so the four cannot drift apart again."""
    assert "iter_bounded_lines" in inspect.getsource(module)
