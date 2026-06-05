"""Regression tests for v5.18/B22 — wake-panel previous-month clamp.

BLOCKER B22 (HIGH): the Wake panel's "previous month" link called
``_shift_month(period, -1)`` with no lower bound. A request for
``?month=0001-01`` resolves the wake period to ``datetime(1, 1, 1)``; shifting
that back one month builds year 0, which ``datetime`` rejects with
``ValueError: year 0 is out of range``. The exception was unhandled and took
down the entire dashboard render (HTTP 500).

These tests pin the fix:
  (a) rendering with the minimum/extreme month no longer raises, and no
      prev link is emitted that would point below the calendar floor; and
  (b) a benign past month still produces a working prev link (guards against
      over-restriction that would break normal back-navigation).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.dashboard import render_dashboard


@pytest.fixture(autouse=True)
def _freeze_to_june_2026():
    # Pin the wall clock to mid-June so that "2026-05" reads as a past month
    # (the benign case needs a real prev link to April).
    with freeze_time("2026-06-15 12:00:00"):
        yield


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "time.timeclock").write_text("; time\n", encoding="utf-8")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")


def _prev_hrefs(html: str) -> list[str]:
    """Return the href values of every rel="prev" wake-nav anchor."""
    return re.findall(r'href="([^"]*)"[^>]*rel="prev"', html)


def test_extreme_min_month_does_not_crash_render(tmp_path: Path) -> None:
    # (a) Malicious/extreme input: the calendar floor. Before the clamp this
    # raised ValueError ("year 0 is out of range") and 500'd the whole page.
    _init_project(tmp_path)

    html = render_dashboard(tmp_path, wake_month="0001-01")

    # Render must succeed and still draw the Wake panel.
    assert "Wake ·" in html
    assert "January 0001" in html  # %B %Y label for the floor month
    # No prev link may point below the floor: there must be no month=0000-*
    # (or any sub-year-1) target. The clamp emits an empty href instead.
    assert "month=0000" not in html
    for href in _prev_hrefs(html):
        assert "month=" not in href, f"prev link below floor leaked: {href!r}"


def test_benign_past_month_still_has_working_prev_link(tmp_path: Path) -> None:
    # (b) Normal input: a real past month must still back-navigate. Guards
    # against an over-broad clamp that would suppress every prev link.
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 14, 9, 0),
            end=datetime(2026, 5, 14, 10, 0),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            project="acme:may",
        ),
    )

    html = render_dashboard(tmp_path, wake_month="2026-05")

    assert "May 2026" in html
    # Prev link must target April 2026.
    prev_hrefs = _prev_hrefs(html)
    assert prev_hrefs, 'expected a rel="prev" wake-nav link for a past month'
    assert any("month=2026-04" in href for href in prev_hrefs)
