"""v2.74 — Ambient Status.

Pins the changeset invariants: snapshot is composed only from
existing builders, projection is a labeled estimate with no
divide-by-zero, render escapes user strings, and the build never
opens a provider credential file. The v2.69 `status --json` timer
contract must stay byte-compatible (additive only).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from halyard.budget import BudgetStatus
from halyard.cli import app
from halyard.status_render import render_status_text
from halyard.status_snapshot import (
    AdriftStatus,
    CaptureStatus,
    ClientSpend,
    SpendStatus,
    StatusSnapshot,
    _budgets,
    build_status_snapshot,
)

_NOW = datetime(2026, 5, 17, 12, 0, 0)


# --- projection math (the CodexBar reframe) --------------------------------


def test_projection_linear_and_estimate_always_true(monkeypatch) -> None:
    import halyard.status_snapshot as ss

    # day 17 of a 31-day month, $170 mtd, $400 limit.
    monkeypatch.setattr(
        ss,
        "budget_status",
        lambda now=None: [
            BudgetStatus(
                slug="acme:web",
                today_spend=10.0,
                today_limit=None,
                month_spend=170.0,
                month_limit=400.0,
            )
        ],
    )
    [b] = _budgets(_NOW)  # 2026-05 has 31 days, day_of_month=17
    assert b.estimate is True  # non-removable
    # run_rate = 170/17 = 10/day → projected = 10*31 = 310
    assert b.projected_month_end_usd == 310.0
    # days_until_limit = floor((400-170)/10) = 23
    assert b.days_until_limit == 23
    assert b.pct == 42  # int(170/400*100)


def test_projection_zero_runrate_no_divide_by_zero(monkeypatch) -> None:
    import halyard.status_snapshot as ss

    monkeypatch.setattr(
        ss,
        "budget_status",
        lambda now=None: [
            BudgetStatus(
                slug="x:y",
                today_spend=0.0,
                today_limit=None,
                month_spend=0.0,
                month_limit=100.0,
            )
        ],
    )
    [b] = _budgets(_NOW)
    assert b.days_until_limit is None  # run-rate 0 → no projection
    assert b.projected_month_end_usd == 0.0
    assert b.estimate is True


def test_no_limit_budget_has_no_days_until(monkeypatch) -> None:
    import halyard.status_snapshot as ss

    monkeypatch.setattr(
        ss,
        "budget_status",
        lambda now=None: [
            BudgetStatus(
                slug="n:l", today_spend=1.0, today_limit=None, month_spend=50.0, month_limit=None
            )
        ],
    )
    [b] = _budgets(_NOW)
    assert b.month_limit_usd is None
    assert b.days_until_limit is None
    assert b.pct == 0


# --- composed only from existing builders ----------------------------------


def _patch_sources(monkeypatch, sessions: list, budgets: list, healthy: bool = True) -> None:
    import halyard.status_snapshot as ss
    from halyard.doctor import DoctorCheck, DoctorReport

    monkeypatch.setattr(ss, "_all_sessions", lambda: sessions)
    monkeypatch.setattr(ss, "budget_status", lambda now=None: budgets)
    rep = DoctorReport(
        status="ok" if healthy else "error",
        checks=[
            DoctorCheck(
                id="hook.claude",
                label="Claude",
                status="ok" if healthy else "error",
                detail="",
            )
        ],
    )
    monkeypatch.setattr(ss, "build_doctor_report", lambda *a, **k: rep)


def test_snapshot_shape_and_single_source_parity(monkeypatch) -> None:
    from halyard.ai_log import AiSession
    from halyard.usage import sum_spend

    s = AiSession(
        start=_NOW - timedelta(days=1),
        end=_NOW - timedelta(days=1, minutes=-5),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=10,
        output_tokens=5,
        cost_usd=2.50,
        project="kormilo:halyard",
    )
    _patch_sources(monkeypatch, [s], [])
    import halyard.status_snapshot as ss

    monkeypatch.setattr(ss, "_adrift", lambda: AdriftStatus(count=0, usd=0.0))

    snap = build_status_snapshot(now=_NOW)
    assert isinstance(snap, StatusSnapshot)
    month_start = datetime(_NOW.year, _NOW.month, 1)
    # spend value is exactly what sum_spend (the shared convention) returns
    assert snap.spend.month_usd == sum_spend([s], period_start=month_start, period_end=_NOW)
    assert snap.capture.hooks == {"claude": "ok"}
    assert snap.capture.healthy is True

    from halyard.jsonio import to_jsonable

    j = to_jsonable(snap)
    assert set(j) >= {"generated_at", "capture", "spend", "adrift", "budgets"}


def test_empty_state_no_exception(monkeypatch) -> None:
    import halyard.status_snapshot as ss

    _patch_sources(monkeypatch, [], [])
    monkeypatch.setattr(ss, "_adrift", lambda: AdriftStatus(count=0, usd=0.0))
    snap = build_status_snapshot(now=_NOW)
    assert snap.spend.month_usd == 0.0
    assert snap.capture.minutes_since_last_capture is None
    assert snap.budgets == []


# --- privacy: never opens a provider credential file -----------------------


def test_build_opens_no_provider_credentials(monkeypatch, tmp_path) -> None:
    import builtins

    import halyard.status_snapshot as ss

    _patch_sources(monkeypatch, [], [])
    monkeypatch.setattr(ss, "_adrift", lambda: AdriftStatus(count=0, usd=0.0))

    opened: list[str] = []
    real_open = builtins.open

    def rec_open(file, *a, **k):  # type: ignore[no-untyped-def]
        opened.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", rec_open)
    build_status_snapshot(now=_NOW)

    forbidden = ("oauth_creds", "gemini-credentials", ".codex", "Keychain", "cookies")
    leaks = [p for p in opened for f in forbidden if f in p]
    assert not leaks, f"snapshot opened provider/credential paths: {leaks}"


# --- render: escapes user strings, marks estimates -------------------------


def test_render_escapes_and_marks_estimate() -> None:
    snap = StatusSnapshot(
        generated_at=_NOW,
        capture=CaptureStatus(healthy=True, hooks={"claude": "ok"}, minutes_since_last_capture=3),
        spend=SpendStatus(
            today_usd=1.0,
            month_usd=12.0,
            by_client=[ClientSpend(slug="ev[red]il:proj", month_usd=9.0)],
        ),
        adrift=AdriftStatus(count=0, usd=0.0),
        budgets=[],
    )
    text = render_status_text(snap)
    assert r"ev\[red]il:proj" in text  # markup-escaped
    assert "[red]il:proj" not in text.replace(r"\[red]", "")
    assert "capture ok" in text


def test_render_shows_budget_burn_with_estimate_tilde() -> None:
    snap = StatusSnapshot(
        generated_at=_NOW,
        capture=CaptureStatus(healthy=True, hooks={}, minutes_since_last_capture=0),
        spend=SpendStatus(today_usd=0.0, month_usd=0.0, by_client=[]),
        adrift=AdriftStatus(count=0, usd=0.0),
        budgets=[
            type(
                "B",
                (),
                {
                    "slug": "acme:web",
                    "month_limit_usd": 400.0,
                    "month_spend_usd": 170.0,
                    "pct": 42,
                    "projected_month_end_usd": 310.0,
                    "days_until_limit": 23,
                    "estimate": True,
                },
            )()
        ],
    )
    text = render_status_text(snap)
    assert "~$310 proj" in text and "~23d to limit" in text


# --- CLI: v2.69 timer contract preserved; snapshot is additive -------------


def test_status_json_timer_contract_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["status", "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert "active" in payload  # v2.69 timer shape, NOT the snapshot


def test_status_snapshot_json_is_the_new_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    import halyard.status_snapshot as ss

    _patch_sources(monkeypatch, [], [])
    monkeypatch.setattr(ss, "_adrift", lambda: AdriftStatus(count=0, usd=0.0))
    r = CliRunner().invoke(app, ["status", "--snapshot", "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert set(payload) >= {"capture", "spend", "adrift", "budgets"}
    assert "active" not in payload  # distinct from the timer contract


# --- perf: per-build bound, tracing-aware ----------------------------------


def test_snapshot_build_is_bounded(
    tmp_path: Path, monkeypatch, perf_ceiling: Callable[[float], float]
) -> None:
    import time

    import halyard.status_snapshot as ss
    from halyard.ai_log import AiSession

    big = [
        AiSession(
            start=_NOW - timedelta(minutes=i + 1),
            end=_NOW - timedelta(minutes=i),
            tool="claude-code",
            model="m",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.001,
            project="a:b",
        )
        for i in range(5000)
    ]
    _patch_sources(monkeypatch, big, [])
    monkeypatch.setattr(ss, "_adrift", lambda: AdriftStatus(count=0, usd=0.0))
    t0 = time.monotonic()
    build_status_snapshot(now=_NOW)
    assert time.monotonic() - t0 < perf_ceiling(1.0)
