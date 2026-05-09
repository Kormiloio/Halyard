"""Tests for src/halyard/achievements.py."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from halyard.achievements import (
    MEDALS,
    RANKS,
    _clean_watch_streak,
    _evaluate_medals,
    _evaluate_rank,
    _extract_watches,
    _Watch,
    _watch_streak,
    build_service_record,
)
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(
    *,
    start: datetime,
    project: str | None = None,
    tool: str = "claude-code",
    tokens_available: bool = True,
    attr_method: str | None = None,
    minutes: int = 30,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=minutes),
        tool=tool,
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.50,
        project=project,
        tokens_available=tokens_available,
        attr_method=attr_method,
    )


def _write_timeclock(path: Path, entries: list[tuple[datetime, datetime, str]]) -> None:
    lines = ["; Halyard timeclock"]
    for start, end, account in entries:
        lines.append(f"i {start:%Y-%m-%d %H:%M:%S} {account}")
        lines.append(f"o {end:%Y-%m-%d %H:%M:%S}")
    path.write_text("\n".join(lines) + "\n")


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Rank catalog sanity
# ---------------------------------------------------------------------------


def test_ranks_sorted_by_level() -> None:
    for i, rank in enumerate(RANKS):
        assert rank.level == i


def test_ranks_sessions_required_non_decreasing() -> None:
    reqs = [r.sessions_required for r in RANKS]
    assert reqs == sorted(reqs)


def test_medals_have_unique_keys() -> None:
    keys = [m.key for m in MEDALS]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# _evaluate_rank
# ---------------------------------------------------------------------------


def test_rank_civilian_at_zero() -> None:
    rank, next_rank, _ = _evaluate_rank(0)
    assert rank.name == "Civilian"
    assert next_rank is not None
    assert next_rank.name == "Deckhand"


def test_rank_deckhand_at_one() -> None:
    rank, next_rank, to_next = _evaluate_rank(1)
    assert rank.name == "Deckhand"
    assert next_rank is not None
    assert to_next == next_rank.sessions_required - 1


def test_rank_commodore_at_max() -> None:
    rank, next_rank, to_next = _evaluate_rank(1000)
    assert rank.name == "Commodore"
    assert next_rank is None
    assert to_next == 0


def test_rank_boundary_exact() -> None:
    # Exactly at Navigator threshold
    rank, _, _ = _evaluate_rank(100)
    assert rank.name == "Navigator"


def test_rank_just_below_boundary() -> None:
    rank, next_rank, _ = _evaluate_rank(99)
    assert rank.name == "Quartermaster"
    assert next_rank is not None and next_rank.name == "Navigator"


# ---------------------------------------------------------------------------
# _watch_streak
# ---------------------------------------------------------------------------


def _watch(day: date, slug: str = "acme:auth") -> _Watch:
    start = datetime(day.year, day.month, day.day, 10, 0)
    return _Watch(slug=slug, start=start, end=start + timedelta(hours=1), duration_minutes=60)


def test_streak_no_watches() -> None:
    assert _watch_streak([], as_of=date(2026, 5, 9)) == 0


def test_streak_single_day_today() -> None:
    today = date(2026, 5, 9)
    assert _watch_streak([_watch(today)], as_of=today) == 1


def test_streak_consecutive_days() -> None:
    today = date(2026, 5, 9)
    watches = [_watch(today - timedelta(days=i)) for i in range(5)]
    assert _watch_streak(watches, as_of=today) == 5


def test_streak_breaks_on_gap() -> None:
    today = date(2026, 5, 9)
    watches = [_watch(today), _watch(today - timedelta(days=2))]  # gap on day 1
    assert _watch_streak(watches, as_of=today) == 1


def test_streak_only_yesterday() -> None:
    today = date(2026, 5, 9)
    watches = [_watch(today - timedelta(days=1))]
    assert _watch_streak(watches, as_of=today) == 0


# ---------------------------------------------------------------------------
# _clean_watch_streak
# ---------------------------------------------------------------------------


def test_clean_watch_streak_empty() -> None:
    assert _clean_watch_streak(set(), as_of=date(2026, 5, 9)) == 0


def test_clean_watch_streak_counts_consecutive() -> None:
    today = date(2026, 5, 9)
    clean_days = {today - timedelta(days=i) for i in range(7)}
    assert _clean_watch_streak(clean_days, as_of=today) == 7


# ---------------------------------------------------------------------------
# _extract_watches
# ---------------------------------------------------------------------------


def test_extract_watches_empty_timeclock(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    watches = _extract_watches(tmp_path)
    assert watches == []


def test_extract_watches_parses_entries(tmp_path: Path) -> None:
    _make_project(tmp_path)
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 11, 30)
    _write_timeclock(tmp_path / "time.timeclock", [(t0, t1, "acme:auth")])
    watches = _extract_watches(tmp_path)
    assert len(watches) == 1
    assert watches[0].duration_minutes == 90.0


# ---------------------------------------------------------------------------
# _evaluate_medals
# ---------------------------------------------------------------------------


def test_eight_bells_earned_with_watch(tmp_path: Path) -> None:
    watch = _watch(date(2026, 5, 8))
    medals = _evaluate_medals(tmp_path, [], [watch], set())
    keys = {m.key for m in medals}
    assert "eight_bells" in keys


def test_eight_bells_not_earned_without_watch(tmp_path: Path) -> None:
    medals = _evaluate_medals(tmp_path, [], [], set())
    keys = {m.key for m in medals}
    assert "eight_bells" not in keys


def test_full_sail_requires_90min_watch(tmp_path: Path) -> None:
    short = _Watch("x", datetime(2026, 5, 8, 9, 0), datetime(2026, 5, 8, 10, 0), 60)
    long_ = _Watch("x", datetime(2026, 5, 8, 9, 0), datetime(2026, 5, 8, 10, 31), 91)

    keys_short = {m.key for m in _evaluate_medals(tmp_path, [], [short], set())}
    keys_long = {m.key for m in _evaluate_medals(tmp_path, [], [long_], set())}
    assert "full_sail" not in keys_short
    assert "full_sail" in keys_long


def test_clean_manifest_medal(tmp_path: Path) -> None:
    medals = _evaluate_medals(tmp_path, [], [], {date(2026, 5, 8)})
    assert any(m.key == "clean_manifest" for m in medals)


def test_lighthouse_medal_requires_backfill(tmp_path: Path) -> None:
    s = _session(start=datetime(2026, 5, 8, 10, 0), project="acme:auth", attr_method="backfill")
    medals = _evaluate_medals(tmp_path, [s], [], set())
    assert any(m.key == "lighthouse" for m in medals)


def test_signal_master_requires_three_tools(tmp_path: Path) -> None:
    sessions = [
        _session(start=datetime(2026, 5, 8, 10, 0), tool="claude-code"),
        _session(start=datetime(2026, 5, 8, 11, 0), tool="cursor"),
    ]
    no_medal = _evaluate_medals(tmp_path, sessions, [], set())
    assert not any(m.key == "signal_master" for m in no_medal)

    sessions.append(_session(start=datetime(2026, 5, 8, 12, 0), tool="gemini-cli"))
    with_medal = _evaluate_medals(tmp_path, sessions, [], set())
    assert any(m.key == "signal_master" for m in with_medal)


def test_harbor_master_medal_with_invoice(tmp_path: Path) -> None:
    invoices = tmp_path / "invoices"
    invoices.mkdir()
    (invoices / "invoice-2026-04.md").write_text("# Invoice")
    medals = _evaluate_medals(tmp_path, [], [], set())
    assert any(m.key == "harbor_master" for m in medals)


def test_harbor_master_not_earned_without_invoice(tmp_path: Path) -> None:
    medals = _evaluate_medals(tmp_path, [], [], set())
    assert not any(m.key == "harbor_master" for m in medals)


# ---------------------------------------------------------------------------
# build_service_record integration
# ---------------------------------------------------------------------------


def test_service_record_civilian_no_data(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    record = build_service_record(tmp_path, [])
    assert record.rank.name == "Civilian"
    assert record.total_sessions == 0
    assert record.proof_score == 0  # no sessions → no proof
    assert record.earned_medals == []


def test_service_record_deckhand_after_one_session(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    s = _session(start=datetime(2026, 5, 8, 10, 0), project="acme:auth")
    append_session(tmp_path, s)
    sessions = [s]
    record = build_service_record(tmp_path, sessions)
    assert record.rank.name == "Deckhand"
    assert record.attributed_sessions == 1


def test_service_record_watch_streak_computed(tmp_path: Path) -> None:
    _make_project(tmp_path)
    today = date(2026, 5, 9)
    entries = [
        (datetime(2026, 5, 9, 9, 0), datetime(2026, 5, 9, 10, 0), "acme:auth"),
        (datetime(2026, 5, 8, 9, 0), datetime(2026, 5, 8, 10, 0), "acme:auth"),
        (datetime(2026, 5, 7, 9, 0), datetime(2026, 5, 7, 10, 0), "acme:auth"),
    ]
    _write_timeclock(tmp_path / "time.timeclock", entries)
    record = build_service_record(tmp_path, [], as_of=today)
    assert record.watch_streak == 3


def test_service_record_proof_score_all_attributed(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    sessions = [
        _session(start=datetime(2026, 5, 8, 10, i * 10), project="acme:auth") for i in range(5)
    ]
    record = build_service_record(tmp_path, sessions)
    assert record.proof_score == 100


def test_service_record_proof_score_mixed(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    # 5 attributed + tokens, 5 unattributed + no tokens
    sessions = [
        _session(start=datetime(2026, 5, 8, 10, i), project="acme:auth") for i in range(5)
    ] + [_session(start=datetime(2026, 5, 8, 11, i), tokens_available=False) for i in range(5)]
    record = build_service_record(tmp_path, sessions)
    # 5/10 attr * 0.6 + 5/10 tokens * 0.4 = 0.3 + 0.2 = 0.5 → 50%
    assert record.proof_score == 50


def test_service_record_gold_stripe_not_earned_below_30(tmp_path: Path) -> None:
    _make_project(tmp_path)
    today = date(2026, 5, 9)
    entries = [
        (datetime(2026, 5, 9 - i, 9, 0), datetime(2026, 5, 9 - i, 10, 0), "acme:auth")
        if i < 9
        else None  # skipped
        for i in range(29)
    ]
    _write_timeclock(tmp_path / "time.timeclock", [e for e in entries if e])  # type: ignore[arg-type]
    record = build_service_record(tmp_path, [], as_of=today)
    assert not record.gold_stripe_earned


def test_service_record_next_rank_none_at_commodore(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    sessions = [
        _session(start=datetime(2026, 5, 1, 10, 0) + timedelta(hours=i), project="acme:auth")
        for i in range(1000)
    ]
    record = build_service_record(tmp_path, sessions)
    assert record.rank.name == "Commodore"
    assert record.next_rank is None
    assert record.sessions_toward_next == 0


# ---------------------------------------------------------------------------
# Passport
# ---------------------------------------------------------------------------


def test_passport_empty_when_no_sessions(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    record = build_service_record(tmp_path, [])
    assert record.passport == []


def test_passport_single_known_tool(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    sessions = [_session(start=datetime(2026, 5, 1, 10, 0), tool="claude-code")]
    record = build_service_record(tmp_path, sessions)
    assert len(record.passport) == 1
    stamp = record.passport[0]
    assert stamp.tool == "claude-code"
    assert stamp.name == "Claude Code"
    assert stamp.icon == "🤖"


def test_passport_deduplicates_same_tool(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    sessions = [
        _session(start=datetime(2026, 5, 1, 10, 0) + timedelta(hours=i), tool="cursor")
        for i in range(5)
    ]
    record = build_service_record(tmp_path, sessions)
    assert len(record.passport) == 1
    assert record.passport[0].tool == "cursor"


def test_passport_multiple_tools(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    sessions = [
        _session(start=datetime(2026, 5, 1, 10, 0), tool="claude-code"),
        _session(start=datetime(2026, 5, 1, 11, 0), tool="cursor"),
        _session(start=datetime(2026, 5, 1, 12, 0), tool="gemini-cli"),
    ]
    record = build_service_record(tmp_path, sessions)
    tools = {s.tool for s in record.passport}
    assert tools == {"claude-code", "cursor", "gemini-cli"}


def test_passport_unknown_tool_gets_default_icon(tmp_path: Path) -> None:
    _make_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("; empty\n")
    sessions = [_session(start=datetime(2026, 5, 1, 10, 0), tool="some-new-tool")]
    record = build_service_record(tmp_path, sessions)
    assert len(record.passport) == 1
    stamp = record.passport[0]
    assert stamp.tool == "some-new-tool"
    assert stamp.icon == "🔧"
