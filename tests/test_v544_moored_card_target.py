"""v5.44 — a moored card never said what it was moored against.

The user asked why their most active project read `Shipshape · Moored`.
The badge is `sessions >= target`, and with no `voyages.toml` every
project silently uses `_DEFAULT_TARGET = 20`. Their project was at 107
sessions — 535% of a target nobody set — and "Moored" reads as finished.

The target has always been configurable (`halyard voyage set <slug>
--sessions <n>`). What was missing: active cards render their
denominator, and the moored branch — the one state whose cause is least
obvious — was the only one that did not.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from halyard.ai_log import AiSession
from halyard.dashboard import _friends_panel
from halyard.voyages import VoyageEntry, build_voyage_summaries, write_voyages


def _sessions(n: int, slug: str = "a:b") -> dict[str, list[AiSession]]:
    return {
        slug: [
            AiSession(
                start=datetime(2026, 9, 1, 9),
                end=datetime(2026, 9, 1, 10),
                tool="codex",
                model="m",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                project=slug,
            )
            for _ in range(n)
        ]
    }


def _panel(tmp_path: Path, n: int) -> str:
    flat = [s for group in _sessions(n).values() for s in group]
    return _friends_panel(tmp_path, flat)


# --- the count is on the card -----------------------------------------


def test_a_moored_card_shows_sessions_over_target(tmp_path: Path) -> None:
    """107 of a default 20 is the case that prompted this."""
    html = _panel(tmp_path, 107)

    assert "Moored" in html, "107 >= the default 20"
    assert "107 / 20" in html, "the numbers that explain the badge"


def test_an_active_card_still_shows_its_count(tmp_path: Path) -> None:
    """Unchanged — this branch was already right."""
    html = _panel(tmp_path, 4)

    assert "Anchors Aweigh" in html
    assert "4" in html and "20" in html


def test_a_trait_is_kept_alongside_the_count(tmp_path: Path) -> None:
    """An earned creature trait must not be replaced by the count."""
    write_voyages(
        tmp_path,
        [VoyageEntry(slug="a:b", stage="moored", creature="🐋", creature_trait="Massive project")],
    )
    html = _panel(tmp_path, 107)

    assert "Massive project" in html
    assert "107 /" in html


# --- the target is what drives it -------------------------------------


def test_raising_the_target_un_moors_the_project(tmp_path: Path) -> None:
    """The knob the card now points at. 107/500 is not moored."""
    write_voyages(tmp_path, [VoyageEntry(slug="a:b", target_sessions=500)])
    summary = build_voyage_summaries(tmp_path, _sessions(107))[0]

    assert summary.stage != "moored"
    assert summary.target_sessions == 500


def test_the_default_target_is_what_moors_it(tmp_path: Path) -> None:
    """No voyages.toml: every project silently uses 20."""
    summary = build_voyage_summaries(tmp_path, _sessions(107))[0]

    assert summary.target_sessions == 20
    assert summary.stage == "moored"


def test_a_project_just_over_target_reads_the_same_as_one_far_over(tmp_path: Path) -> None:
    """Past 100% the stage carries no information — which is exactly why
    the count has to be visible rather than hidden behind the label."""
    just_over = build_voyage_summaries(tmp_path, _sessions(21))[0]
    far_over = build_voyage_summaries(tmp_path, _sessions(107))[0]

    assert just_over.stage == far_over.stage == "moored"
    assert "21 / 20" in _panel(tmp_path, 21)
    assert "107 / 20" in _panel(tmp_path, 107)
