"""Gap 9: read_sessions tool limit parameter performance and memory safety.

_execute_tool("read_sessions", {"limit": N}, ...) must handle large limit values
without hanging or allocating memory exponentially.  The slicing logic in
_execute_tool is O(n) on the session count; these tests guard against
accidental quadratic or unbounded allocation.
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from halyard.log_agent import _execute_tool

_NOW = datetime(2026, 5, 8, 12, 0, 0)

# One valid session log line (minimal fields)
_SESSION_LINE = (
    "s 2026-05-08T10:00:00 2026-05-08T10:30:00 claude-code claude-sonnet-4-5 200 80 0.0040\n"
)

_SESSION_COUNT = 10_000
_TIME_LIMIT_SECONDS = 2.0
# 256 MB ceiling — parse + list comprehension should stay well under this
_MEMORY_CEILING_BYTES = 256 * 1024 * 1024


def _build_large_log(project_dir: Path, n: int = _SESSION_COUNT) -> None:
    """Write a session log with n valid session lines."""
    log = project_dir / "ai-sessions.log"
    header = (
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n"
    )
    log.write_text(header + _SESSION_LINE * n, encoding="utf-8")


# ---------------------------------------------------------------------------
# test_large_limit_completes_in_time
# ---------------------------------------------------------------------------


def test_large_limit_completes_in_time(
    tmp_path: Path, perf_ceiling: Callable[[float], float]
) -> None:
    """read_sessions with limit >> session_count completes within budget."""
    _build_large_log(tmp_path)

    t0 = time.monotonic()
    result = _execute_tool(
        "read_sessions",
        {"limit": 1_000_000},  # far larger than the 10 000-line log
        project_dir=tmp_path,
        now=_NOW,
    )
    elapsed = time.monotonic() - t0

    # Returns a list (not an error dict)
    assert isinstance(result, list), f"Expected list, got {type(result)}: {result}"
    # All sessions should be returned since limit > session count
    assert len(result) == _SESSION_COUNT
    # Tracing-aware ceiling (coverage/profiler inflate wall-clock);
    # see conftest._perf_ceiling. Still catches an O(n^2) regression
    # (orders of magnitude on 10k lines), never flakes on instrumentation.
    ceiling = perf_ceiling(_TIME_LIMIT_SECONDS)
    assert elapsed < ceiling, f"read_sessions took {elapsed:.2f}s — exceeds {ceiling:.1f}s ceiling"


# ---------------------------------------------------------------------------
# test_large_limit_no_oom
# ---------------------------------------------------------------------------


def test_large_limit_no_oom(tmp_path: Path) -> None:
    """read_sessions with a large limit stays within a reasonable memory envelope."""
    _build_large_log(tmp_path)

    tracemalloc.start()
    _execute_tool(
        "read_sessions",
        {"limit": 1_000_000},
        project_dir=tmp_path,
        now=_NOW,
    )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert peak < _MEMORY_CEILING_BYTES, (
        f"Peak allocation {peak / 1024 / 1024:.1f} MB exceeds "
        f"{_MEMORY_CEILING_BYTES / 1024 / 1024:.0f} MB ceiling"
    )
