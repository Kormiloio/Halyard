"""Tests for halyard.voyages — voyage lifecycle and sea creature assignment."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from halyard.ai_log import AiSession
from halyard.voyages import (
    STAGE_LABELS,
    VoyageEntry,
    VoyageSummary,
    assign_creature,
    build_voyage_summaries,
    check_auto_complete,
    compute_stage,
    read_voyages,
    voyage_for_slug,
    write_voyages,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(
    project: str = "proj",
    tool: str = "claude-code",
    start: datetime | None = None,
    end: datetime | None = None,
    attr_method: str = "",
) -> AiSession:
    s = start or datetime(2026, 1, 15, 10, 0, 0)
    e = end or s + timedelta(hours=1)
    return AiSession(
        start=s,
        end=e,
        project=project,
        tool=tool,
        model="claude-3-5-sonnet",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.01,
        tokens_available=True,
        attr_method=attr_method,
    )


# ---------------------------------------------------------------------------
# Stage computation
# ---------------------------------------------------------------------------


def test_compute_stage_not_started() -> None:
    assert compute_stage(0, 20) == "not_started"


def test_compute_stage_anchors_aweigh() -> None:
    assert compute_stage(1, 20) == "anchors_aweigh"
    assert compute_stage(4, 20) == "anchors_aweigh"


def test_compute_stage_making_headway() -> None:
    assert compute_stage(5, 20) == "making_headway"
    assert compute_stage(9, 20) == "making_headway"


def test_compute_stage_rounding_the_mark() -> None:
    assert compute_stage(10, 20) == "rounding_the_mark"
    assert compute_stage(14, 20) == "rounding_the_mark"


def test_compute_stage_flying_colors() -> None:
    assert compute_stage(15, 20) == "flying_colors"
    assert compute_stage(19, 20) == "flying_colors"


def test_compute_stage_moored() -> None:
    assert compute_stage(20, 20) == "moored"
    assert compute_stage(25, 20) == "moored"


def test_compute_stage_zero_target() -> None:
    # target=0 guarded by max(target, 1) — session_count=1 → moored
    assert compute_stage(1, 0) == "moored"


# ---------------------------------------------------------------------------
# Stage labels
# ---------------------------------------------------------------------------


def test_stage_labels_all_present() -> None:
    expected = {
        "not_started",
        "anchors_aweigh",
        "making_headway",
        "rounding_the_mark",
        "flying_colors",
        "moored",
    }
    assert set(STAGE_LABELS.keys()) == expected


# ---------------------------------------------------------------------------
# Creature assignment
# ---------------------------------------------------------------------------


def test_assign_creature_whale_highest_count() -> None:
    sessions = [_session() for _ in range(10)]
    all_counts = {"other": 5}
    emoji, trait = assign_creature("myproj", sessions, all_counts)
    assert emoji == "🐋"
    assert trait == "Massive project"


def test_assign_creature_turtle_long_voyage() -> None:
    # spans 3+ months (90+ days)
    s1 = _session(start=datetime(2025, 1, 1, 10, 0), end=datetime(2025, 1, 1, 11, 0))
    s2 = _session(start=datetime(2025, 4, 15, 10, 0), end=datetime(2025, 4, 15, 11, 0))
    sessions = [s1, s2]
    # Don't let whale rule fire: use a higher count for others
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts)
    assert emoji == "🐢"
    assert trait == "Long voyage"


def test_assign_creature_dolphin_clean_run() -> None:
    # >15 sessions, all attributed → dolphin
    sessions = [_session(project="proj") for _ in range(16)]
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts)
    assert emoji == "🐬"
    assert trait == "Clean run"


def test_assign_creature_octopus_multi_tool() -> None:
    # 3 distinct tools, some unattributed
    sessions = [
        _session(tool="claude-code", project=""),
        _session(tool="cursor", project=""),
        _session(tool="gemini-cli", project=""),
    ]
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts)
    assert emoji == "🦑"
    assert trait == "Multi-tool"


def test_assign_creature_clownfish_small_complete() -> None:
    # ≤15 sessions, all attributed → clownfish (dolphin requires >15)
    sessions = [_session() for _ in range(5)]
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts)
    assert emoji == "🐠"
    assert trait == "Small but complete"


def test_assign_creature_shark_intense_sprint() -> None:
    # 5+ sessions in a single day, not all attributed
    day = datetime(2026, 3, 10, 9, 0)
    sessions = [
        _session(
            project="",
            start=day + timedelta(hours=i),
            end=day + timedelta(hours=i, minutes=30),
        )
        for i in range(6)
    ]
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts)
    assert emoji == "🦈"
    assert trait == "Intense sprint"


def test_assign_creature_coral_reef() -> None:
    sessions = [_session(project="") for _ in range(3)]
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts, coral_reef=True)
    assert emoji == "🪸"
    assert trait == "Ecosystem builder"


def test_assign_creature_seal_fallback() -> None:
    sessions = [_session(project="") for _ in range(3)]
    all_counts = {"other": 999}
    emoji, trait = assign_creature("myproj", sessions, all_counts, coral_reef=False)
    assert emoji == "🦭"
    assert trait == "Playful"


def test_assign_creature_no_sessions() -> None:
    # Whale rule guards total > 0, so falls through to seal
    emoji, _trait = assign_creature("myproj", [], {"other": 0})
    assert emoji == "🦭"


# ---------------------------------------------------------------------------
# read_voyages / write_voyages round-trip
# ---------------------------------------------------------------------------


def test_write_read_roundtrip(tmp_path: Path) -> None:
    entries = [
        VoyageEntry(
            slug="alpha",
            target_sessions=30,
            inactivity_days=7,
            stage="making_headway",
            started_at="2026-01-01",
            completed_at="",
            creature="",
            creature_trait="",
        ),
        VoyageEntry(
            slug="beta",
            target_sessions=20,
            inactivity_days=14,
            stage="moored",
            started_at="2025-11-01",
            completed_at="2025-12-31",
            creature="🐋",
            creature_trait="Massive project",
        ),
    ]
    write_voyages(tmp_path, entries)
    result = read_voyages(tmp_path)
    assert len(result) == 2
    a = next(e for e in result if e.slug == "alpha")
    b = next(e for e in result if e.slug == "beta")
    assert a.target_sessions == 30
    assert a.stage == "making_headway"
    assert b.creature == "🐋"
    assert b.completed_at == "2025-12-31"


def test_read_voyages_missing_file(tmp_path: Path) -> None:
    assert read_voyages(tmp_path) == []


def test_read_voyages_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "voyages.toml").write_text("not valid toml ][")
    assert read_voyages(tmp_path) == []


# ---------------------------------------------------------------------------
# voyage_for_slug
# ---------------------------------------------------------------------------


def test_voyage_for_slug_found() -> None:
    entries = [VoyageEntry(slug="proj"), VoyageEntry(slug="other")]
    result = voyage_for_slug(entries, "proj")
    assert result.slug == "proj"


def test_voyage_for_slug_not_found_returns_default() -> None:
    result = voyage_for_slug([], "missing")
    assert result.slug == "missing"
    assert result.stage == "not_started"


# ---------------------------------------------------------------------------
# check_auto_complete — target trigger
# ---------------------------------------------------------------------------


def test_check_auto_complete_target_hit(tmp_path: Path) -> None:
    write_voyages(tmp_path, [VoyageEntry(slug="proj", target_sessions=3)])
    sessions = [_session() for _ in range(3)]
    newly = check_auto_complete(tmp_path, {"proj": sessions}, now=date(2026, 5, 1))
    assert "proj" in newly
    updated = read_voyages(tmp_path)
    entry = voyage_for_slug(updated, "proj")
    assert entry.stage == "moored"
    assert entry.completed_at == "2026-05-01"
    assert entry.creature != ""


def test_check_auto_complete_not_enough_sessions(tmp_path: Path) -> None:
    write_voyages(tmp_path, [VoyageEntry(slug="proj", target_sessions=10, inactivity_days=14)])
    # Sessions recent enough to avoid inactivity trigger (now = 5 days after last session)
    last = datetime(2026, 5, 1, 10, 0)
    sessions = [_session(start=last, end=last + timedelta(hours=1)) for _ in range(3)]
    newly = check_auto_complete(tmp_path, {"proj": sessions}, now=date(2026, 5, 6))
    assert "proj" not in newly


# ---------------------------------------------------------------------------
# check_auto_complete — inactivity trigger
# ---------------------------------------------------------------------------


def test_check_auto_complete_inactivity_trigger(tmp_path: Path) -> None:
    write_voyages(tmp_path, [VoyageEntry(slug="proj", target_sessions=50, inactivity_days=14)])
    last_active = datetime(2026, 4, 1, 10, 0)
    sessions = [_session(start=last_active, end=last_active + timedelta(hours=1))]
    # 20 days after last session → inactivity fires
    newly = check_auto_complete(tmp_path, {"proj": sessions}, now=date(2026, 4, 21))
    assert "proj" in newly


def test_check_auto_complete_inactivity_not_yet(tmp_path: Path) -> None:
    write_voyages(tmp_path, [VoyageEntry(slug="proj", target_sessions=50, inactivity_days=14)])
    last_active = datetime(2026, 4, 10, 10, 0)
    sessions = [_session(start=last_active, end=last_active + timedelta(hours=1))]
    # Only 5 days since last session
    newly = check_auto_complete(tmp_path, {"proj": sessions}, now=date(2026, 4, 15))
    assert "proj" not in newly


def test_check_auto_complete_already_moored(tmp_path: Path) -> None:
    write_voyages(
        tmp_path,
        [VoyageEntry(slug="proj", stage="moored", completed_at="2026-01-01", creature="🐋")],
    )
    sessions = [_session() for _ in range(100)]
    newly = check_auto_complete(tmp_path, {"proj": sessions}, now=date(2026, 5, 1))
    assert "proj" not in newly


# ---------------------------------------------------------------------------
# check_auto_complete — stage progression
# ---------------------------------------------------------------------------


def test_check_auto_complete_stage_progression(tmp_path: Path) -> None:
    write_voyages(tmp_path, [VoyageEntry(slug="proj", target_sessions=20, inactivity_days=14)])
    # 7 sessions = 35% → making_headway; use recent date to avoid inactivity trigger
    last = datetime(2026, 5, 1, 10, 0)
    sessions = [_session(start=last, end=last + timedelta(hours=1)) for _ in range(7)]
    check_auto_complete(tmp_path, {"proj": sessions}, now=date(2026, 5, 4))
    updated = read_voyages(tmp_path)
    entry = voyage_for_slug(updated, "proj")
    assert entry.stage == "making_headway"


# ---------------------------------------------------------------------------
# VoyageSummary.progress_pct
# ---------------------------------------------------------------------------


def test_voyage_summary_progress_pct() -> None:
    v = VoyageSummary(
        slug="proj",
        stage="making_headway",
        stage_label="Making Headway",
        session_count=10,
        target_sessions=20,
        creature="",
        creature_trait="",
        completed_at="",
    )
    assert v.progress_pct == 50


def test_voyage_summary_progress_pct_capped() -> None:
    v = VoyageSummary(
        slug="proj",
        stage="moored",
        stage_label="Shipshape · Moored",
        session_count=100,
        target_sessions=20,
        creature="🐋",
        creature_trait="Massive project",
        completed_at="2026-05-01",
    )
    assert v.progress_pct == 100


# ---------------------------------------------------------------------------
# build_voyage_summaries
# ---------------------------------------------------------------------------


def test_build_voyage_summaries_includes_all_slugs(tmp_path: Path) -> None:
    write_voyages(tmp_path, [VoyageEntry(slug="alpha", target_sessions=20)])
    sessions_by_project = {
        "alpha": [_session()],
        "beta": [_session()],
    }
    summaries = build_voyage_summaries(tmp_path, sessions_by_project)
    slugs = {s.slug for s in summaries}
    assert "alpha" in slugs
    assert "beta" in slugs


def test_build_voyage_summaries_moored_stage_preserved(tmp_path: Path) -> None:
    write_voyages(
        tmp_path,
        [VoyageEntry(slug="proj", stage="moored", creature="🐋", creature_trait="Massive project")],
    )
    summaries = build_voyage_summaries(tmp_path, {"proj": [_session() for _ in range(100)]})
    proj = next(s for s in summaries if s.slug == "proj")
    assert proj.stage == "moored"
    assert proj.creature == "🐋"


# ---------------------------------------------------------------------------
# TOML injection safety — slugs with hostile characters round-trip cleanly
# ---------------------------------------------------------------------------


def test_write_voyages_slug_with_quotes_roundtrips(tmp_path: Path) -> None:
    """A slug containing quotes must not corrupt the TOML file."""
    hostile_slug = 'my-proj"injected = true\n[evil]'
    entry = VoyageEntry(slug=hostile_slug, stage="departing")
    write_voyages(tmp_path, [entry])
    loaded = read_voyages(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].slug == hostile_slug


def test_write_voyages_slug_with_backslash_roundtrips(tmp_path: Path) -> None:
    """A slug with backslashes round-trips without TOML parse error."""
    hostile_slug = "proj\\ninjected"
    entry = VoyageEntry(slug=hostile_slug, stage="departing")
    write_voyages(tmp_path, [entry])
    loaded = read_voyages(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].slug == hostile_slug
