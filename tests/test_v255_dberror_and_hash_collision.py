"""v2.55 — DbError (not SystemExit) + session_hash collision quarantine."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard import ai_log, cli
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.db import DbError, get_db

# --- #2: DbError is catchable, not SystemExit ------------------------------


def test_get_db_raises_dberror_on_future_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "cache.db"
    monkeypatch.setattr("halyard.db._DB_PATH", db_file)
    # Create a cache that claims a version newer than this code supports.
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE sessions (x INTEGER)")
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()

    with pytest.raises(DbError) as ei:
        get_db()
    assert not isinstance(ei.value, SystemExit)
    assert "halyard db reset" in str(ei.value)


def test_main_maps_dberror_to_clean_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise DbError("cache needs reset — run `halyard db reset`")

    monkeypatch.setattr(cli, "app", boom)
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 1


def test_attribute_session_degrades_on_dberror(monkeypatch: pytest.MonkeyPatch) -> None:
    # The outcomes upsert path must swallow DbError (plain-text
    # amendment is the source of truth) — proves the except clause
    # was switched from SystemExit to DbError.
    import inspect

    from halyard import outcomes

    src = inspect.getsource(outcomes.attribute_session)
    assert "except DbError:" in src
    assert "except SystemExit:" not in src


# --- #1: 48-bit session_hash collision is quarantined, not mis-folded ------


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n")
    (p / AI_LOG_FILENAME).write_text(HEADER)
    return p


def _s(start: datetime, project: str) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=5),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cost_usd=1.0,
        project=project,
    )


def test_true_hash_collision_is_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _proj(tmp_path / "p")
    append_session(proj, _s(datetime(2026, 5, 15, 9), "acme:one"))
    append_session(proj, _s(datetime(2026, 5, 15, 10), "acme:two"))

    quarantined: list[str] = []
    monkeypatch.setattr(ai_log, "session_hash", lambda _line: "deadbeefdead")
    monkeypatch.setattr(
        ai_log, "_write_quarantine", lambda line, err: quarantined.append(err) or Path("q")
    )

    got = parse_sessions(proj)
    # First line kept; the second (different content, same forced hash)
    # is recognised as a collision and dropped, not silently folded.
    assert len(got) == 1
    assert got[0].project == "acme:one"
    assert len(quarantined) == 1
    assert "collision" in quarantined[0]


def test_identical_duplicate_line_is_not_a_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _proj(tmp_path / "p")
    s = _s(datetime(2026, 5, 15, 9), "acme:one")
    append_session(proj, s)
    append_session(proj, s)  # byte-identical duplicate line

    quarantined: list[str] = []
    monkeypatch.setattr(
        ai_log, "_write_quarantine", lambda line, err: quarantined.append(err) or Path("q")
    )
    got = parse_sessions(proj)
    # Same content → same hash is benign (existing behaviour), never
    # quarantined; both lines retained.
    assert len(got) == 2
    assert quarantined == []
