"""v5.38 — Junie (JetBrains) CLI was captured by nothing at all.

Junie ships as a standalone CLI at ``~/.local/bin/junie``, not only the
JetBrains IDE plugin, so nothing appears under ``Application Support`` to
hint that it exists. On the machine that prompted this it had run 4 sessions
and 23.1M tokens entirely unrecorded, and only surfaced because the user
said out loud that they had used it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from halyard.collectors import junie


@pytest.fixture(autouse=True)
def _junie_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "junie"
    (root / "sessions").mkdir(parents=True)
    monkeypatch.setattr(junie, "_SESSIONS_DIR", root / "sessions")
    monkeypatch.setattr(junie, "_INDEX_FILE", root / "sessions" / "index.jsonl")
    monkeypatch.setattr(junie, "_IMPORTED_STATE_FILE", tmp_path / "junie-imported")
    return root


def _ms(y: int, mo: int, d: int, h: int = 9, mi: int = 0) -> int:
    return int(datetime(y, mo, d, h, mi).timestamp() * 1000)


def _session(
    root: Path,
    sid: str,
    *,
    created: int,
    updated: int,
    project_dir: str = "/tmp/proj",
    usages: list[tuple[str, int, int, int, float]] | None = None,
) -> None:
    """Write one session's index line and events.jsonl."""
    idx = root / "sessions" / "index.jsonl"
    with idx.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "sessionId": sid,
                    "createdAt": created,
                    "updatedAt": updated,
                    "projectDir": project_dir,
                    "taskName": "t",
                }
            )
            + "\n"
        )
    sdir = root / "sessions" / sid
    sdir.mkdir(parents=True, exist_ok=True)
    lines = []
    for model, tin, tout, cache, cost in usages or [("Sonnet-X", 100, 10, 5, 0.02)]:
        lines.append(
            json.dumps(
                {
                    "kind": "SessionA2uxEvent",
                    "timestampMs": updated,
                    "event": {
                        "agentEvent": {
                            "kind": "LlmResponseMetadataEvent",
                            "modelUsage": [
                                {
                                    "model": model,
                                    "cost": cost,
                                    "inputTokens": tin,
                                    "outputTokens": tout,
                                    "cacheInputTokens": cache,
                                    "cacheCreateTokens": 0,
                                }
                            ],
                        }
                    },
                }
            )
        )
    (sdir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- capture ----------------------------------------------------------


def test_a_session_is_captured_with_its_tokens(_junie_home: Path) -> None:
    _session(_junie_home, "s1", created=_ms(2026, 8, 25), updated=_ms(2026, 8, 25, 12))

    out = junie.import_junie_sessions(dry_run=True)

    assert len(out) == 1
    s = out[0]
    assert s.tool == "junie"
    assert (s.input_tokens, s.output_tokens, s.cache_read) == (100, 10, 5)


def test_tokens_sum_across_events(_junie_home: Path) -> None:
    _session(
        _junie_home,
        "s1",
        created=_ms(2026, 8, 25),
        updated=_ms(2026, 8, 25, 12),
        usages=[("M", 100, 10, 1, 0.0), ("M", 200, 20, 2, 0.0)],
    )
    s = junie.import_junie_sessions(dry_run=True)[0]
    assert (s.input_tokens, s.output_tokens, s.cache_read) == (300, 30, 3)


def test_the_dominant_model_labels_the_row(_junie_home: Path) -> None:
    """A session may use several models; one label has to stand for the row."""
    _session(
        _junie_home,
        "s1",
        created=_ms(2026, 8, 25),
        updated=_ms(2026, 8, 25, 12),
        usages=[("small", 10, 1, 0, 0.0), ("big", 900, 90, 0, 0.0)],
    )
    assert junie.import_junie_sessions(dry_run=True)[0].model == "big"


# --- local models -----------------------------------------------------


def test_a_local_model_is_recorded_but_not_billed(_junie_home: Path) -> None:
    """Tokens are real compute; the zero cost is real too, not missing.

    ``sum_spend`` filters on ``billing == "api"``, so marking local keeps
    on-device work in usage totals without diluting the money series.
    """
    _session(
        _junie_home,
        "s1",
        created=_ms(2026, 9, 1),
        updated=_ms(2026, 9, 1, 12),
        usages=[("Qwen3.6-27B-MLX-4bit", 1000, 100, 50, 0.0)],
    )
    s = junie.import_junie_sessions(dry_run=True)[0]
    assert s.billing == "local"
    assert s.cost_usd == 0.0
    assert s.input_tokens == 1000, "tokens still counted"


def test_a_hosted_model_reporting_zero_cost_is_not_reclassified(_junie_home: Path) -> None:
    """A free tier or a billing outage must not silently become 'local'.

    Otherwise real API usage quietly leaves the spend series the moment a
    provider reports 0.0.
    """
    _session(
        _junie_home,
        "s1",
        created=_ms(2026, 9, 1),
        updated=_ms(2026, 9, 1, 12),
        usages=[("gpt-5.6-sol", 1000, 100, 0, 0.0)],
    )
    assert junie.import_junie_sessions(dry_run=True)[0].billing == "api"


def test_a_hosted_model_keeps_its_cost(_junie_home: Path) -> None:
    _session(
        _junie_home,
        "s1",
        created=_ms(2026, 9, 1),
        updated=_ms(2026, 9, 1, 12),
        usages=[("gpt-5.6-sol", 100, 10, 0, 0.25)],
    )
    s = junie.import_junie_sessions(dry_run=True)[0]
    assert s.billing == "api"
    assert s.cost_usd == pytest.approx(0.25)


# --- long sessions ----------------------------------------------------


def test_a_multi_day_session_is_kept(_junie_home: Path) -> None:
    """Junie holds a session open for days — two observed spanned 143 h and 75 h.

    The 12 h plausibility cap would drop them and lose their tokens. That
    cap guards *duration* reporting, which v5.33 and v5.35 already bound at
    the right layer by excluding over-cap sessions from timeclock
    reconciliation and the coverage denominator.
    """
    _session(_junie_home, "long", created=_ms(2026, 8, 27), updated=_ms(2026, 9, 2, 12))

    out = junie.import_junie_sessions(dry_run=True)

    assert len(out) == 1
    assert (out[0].end - out[0].start).total_seconds() / 3600 > 12


# --- growth re-import -------------------------------------------------


def test_a_grown_session_is_re_imported(_junie_home: Path) -> None:
    """Junie writes as it works; a session captured mid-write must not freeze."""
    _session(_junie_home, "s1", created=_ms(2026, 8, 25), updated=_ms(2026, 8, 25, 12))
    first = junie.import_junie_sessions(dry_run=False)
    assert len(first) == 1

    assert junie.import_junie_sessions(dry_run=False) == [], "unchanged: no re-import"

    events = _junie_home / "sessions" / "s1" / "events.jsonl"
    with events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "kind": "SessionA2uxEvent",
                    "timestampMs": _ms(2026, 8, 25, 14),
                    "event": {
                        "agentEvent": {
                            "kind": "LlmResponseMetadataEvent",
                            "modelUsage": [
                                {"model": "M", "cost": 0.0, "inputTokens": 500, "outputTokens": 5}
                            ],
                        }
                    },
                }
            )
            + "\n"
        )

    again = junie.import_junie_sessions(dry_run=True)
    assert len(again) == 1
    assert again[0].input_tokens == 600, "grown session re-imports with the new total"


def test_dry_run_records_no_state(_junie_home: Path) -> None:
    _session(_junie_home, "s1", created=_ms(2026, 8, 25), updated=_ms(2026, 8, 25, 12))
    junie.import_junie_sessions(dry_run=True)
    assert junie.import_junie_sessions(dry_run=True), "dry run must not mark as imported"


# --- robustness -------------------------------------------------------


def test_a_malformed_index_line_is_skipped(_junie_home: Path) -> None:
    idx = _junie_home / "sessions" / "index.jsonl"
    idx.write_text("not json\n\n", encoding="utf-8")
    _session(_junie_home, "s1", created=_ms(2026, 8, 25), updated=_ms(2026, 8, 25, 12))
    assert len(junie.import_junie_sessions(dry_run=True)) == 1


def test_malformed_token_fields_degrade_to_zero(_junie_home: Path) -> None:
    """Untrusted input: one crafted value must not abort the import."""
    _session(
        _junie_home,
        "s1",
        created=_ms(2026, 8, 25),
        updated=_ms(2026, 8, 25, 12),
        usages=[("M", 0, 0, 0, 0.0)],
    )
    ev = _junie_home / "sessions" / "s1" / "events.jsonl"
    ev.write_text(
        ev.read_text(encoding="utf-8").replace('"inputTokens": 0', '"inputTokens": "abc"'),
        encoding="utf-8",
    )
    out = junie.import_junie_sessions(dry_run=True)
    assert out == [] or out[0].input_tokens == 0


def test_no_history_is_not_an_error(_junie_home: Path) -> None:
    assert junie.import_junie_sessions(dry_run=True) == []
    assert junie.junie_history_present() is False


def test_history_and_imported_predicates(_junie_home: Path) -> None:
    _session(_junie_home, "s1", created=_ms(2026, 8, 25), updated=_ms(2026, 8, 25, 12))
    assert junie.junie_history_present() is True
    assert junie.junie_imported_any() is False

    junie.import_junie_sessions(dry_run=False)

    assert junie.junie_imported_any() is True
