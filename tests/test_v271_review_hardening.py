"""Regression tests for v2.71 pre-OSS review-hardening fixes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AiSession
from halyard.cli import app


def _session(**kw: object) -> AiSession:
    start = datetime(2026, 5, 16, 9, 0, 0)
    base: dict = {
        "start": start,
        "end": start + timedelta(minutes=5),
        "tool": "claude-code",
        "model": "claude-opus-4-7",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.01,
        "project": "acme:web",
    }
    base.update(kw)
    return AiSession(**base)


# --- 1. hook crash backstop ------------------------------------------------


def test_run_hook_swallows_any_exception_and_returns_zero() -> None:
    from halyard import cli_hooks

    def boom() -> int:
        raise RuntimeError("kaboom")

    assert cli_hooks._run_hook(boom) == 0  # never propagates into the host
    assert cli_hooks._run_hook(lambda: 7) == 7  # success passes through


def test_run_hook_reraises_keyboardinterrupt() -> None:
    from halyard import cli_hooks

    def interrupt() -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        cli_hooks._run_hook(interrupt)


def test_coerce_int_is_tolerant() -> None:
    from halyard.collectors.claude_code import _coerce_int as cc
    from halyard.collectors.gemini_cli import _coerce_int as gc

    for fn in (cc, gc):
        assert fn("abc") == 0
        assert fn(None) == 0
        assert fn({}) == 0
        assert fn("5") == 5
        assert fn(9) == 9


def test_cc_hook_command_never_crashes_on_garbage_stdin() -> None:
    # End-to-end: a malformed Stop payload must exit cleanly, not
    # traceback into Claude Code.
    result = CliRunner().invoke(app, ["cc-hook"], input='{"usage": {"input_tokens": "NOPE"}}')
    assert result.exit_code == 0


# --- 2. tags round-trip ----------------------------------------------------


def test_tags_with_comma_and_space_round_trip() -> None:
    s = _session(tags=["a,b", "feat: x", "branch:main"])
    back = AiSession.from_log_line(s.to_log_line())
    assert back is not None
    assert back.tags == ["a,b", "feat: x", "branch:main"]
    assert back.branch == "main"  # v2.24 promotion still works post-decode


def test_legacy_comma_tags_still_parse() -> None:
    # Pre-v2.71 form: raw comma-joined, no percent-encoding.
    line = _session().to_log_line()
    line = line.split(" tags=")[0] + " tags=alpha,beta,branch:dev"
    back = AiSession.from_log_line(line)
    assert back is not None
    assert back.tags == ["alpha", "beta", "branch:dev"]
    assert back.branch == "dev"


# --- 4. append_session no longer O(n^2) ------------------------------------


def test_append_session_does_not_reparse_log(tmp_path: Path, monkeypatch) -> None:
    from halyard import ai_log

    (tmp_path / "halyard.toml").write_text("[project]\n")
    (tmp_path / "ai-sessions.log").write_text("; header\n")

    calls = {"n": 0}
    real = ai_log.parse_sessions

    def spy(project_dir: Path):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return real(project_dir)

    monkeypatch.setattr(ai_log, "parse_sessions", spy)
    for _ in range(20):
        ai_log.append_session(tmp_path, _session())
    assert calls["n"] == 0  # append must never parse the whole log


# --- 5. SQLite concurrency -------------------------------------------------


def test_sqlite_concurrent_open_does_not_raise(tmp_path: Path, monkeypatch) -> None:
    from halyard import db as dbmod

    monkeypatch.setattr(dbmod, "_DB_PATH", tmp_path / "cache.db")
    c1 = dbmod.get_db()
    try:
        c2 = dbmod.get_db()  # second concurrent handle must not blow up
        c2.close()
    finally:
        c1.close()
    assert (tmp_path / "cache.db").exists()


# --- 6. --json error contract ----------------------------------------------


def test_report_json_error_is_structured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "halyard.toml").write_text("[project]\n")
    (tmp_path / "ai-sessions.log").write_text("; header\n")
    result = CliRunner().invoke(app, ["report", "--json", "--month", "not-a-month"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert "error" in payload


# --- 7. store applies `a ` incrementally -----------------------------------


def test_store_applies_amendment_without_full_reload(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "ai-sessions.log"
    s = _session(project="acme:web")
    log.write_text("; header\n" + s.to_log_line() + "\n")

    from halyard.tui.store import SessionStore

    store = SessionStore(log)
    store.load()
    assert store.sessions and store.sessions[0].project == "acme:web"

    raw = store.sessions[0]._raw_hash
    assert raw is not None

    reload_called = {"n": 0}
    orig_load = store.load

    def spy_load() -> None:
        reload_called["n"] += 1
        orig_load()

    monkeypatch.setattr(store, "load", spy_load)
    with log.open("a") as fh:
        fh.write(f"a {raw} project=beta:api\n")
    store.read_new_lines()
    assert store.sessions[0].project == "beta:api"
    assert reload_called["n"] == 0  # applied incrementally, no full reload


# --- bounded-read symlink rejection ----------------------------------------


def test_codex_iter_rejects_symlink(tmp_path: Path) -> None:
    from halyard.collectors.codex_app import _iter_jsonl_lines

    real = tmp_path / "real.jsonl"
    real.write_text('{"ok": 1}\n')
    link = tmp_path / "link.jsonl"
    link.symlink_to(real)
    assert list(_iter_jsonl_lines(link)) == []


def test_gemini_history_read_capped_rejects_symlink(tmp_path: Path) -> None:
    from halyard.collectors.gemini_history import _read_capped

    real = tmp_path / "real.json"
    real.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert _read_capped(link) is None


# --- 10. install-claude byte-stable no-op ----------------------------------


def test_install_claude_is_byte_stable_no_op(tmp_path: Path, monkeypatch) -> None:
    from halyard import cli_hooks

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cli_hooks._do_install_hook_claude(global_=True)
    settings = tmp_path / ".claude" / "settings.json"
    first = settings.read_text()
    cli_hooks._do_install_hook_claude(global_=True)
    assert settings.read_text() == first  # second run must not rewrite


# --- Risk 1: typst invoked by resolved path, not bare name -----------------


def test_render_pdf_uses_resolved_typst_path(tmp_path: Path, monkeypatch) -> None:
    from halyard import invoicing

    captured: dict = {}

    monkeypatch.setattr(invoicing.shutil, "which", lambda _name: "/opt/safe/bin/typst")
    monkeypatch.setattr(invoicing, "_open_file", lambda _p: None)
    monkeypatch.setattr(
        invoicing.subprocess,
        "run",
        lambda argv, **kw: captured.setdefault("argv", argv),
    )
    invoice = tmp_path / "inv.typ"
    invoice.write_text("#text[hi]")
    assert invoicing.render_pdf(invoice) is None
    assert captured["argv"][0] == "/opt/safe/bin/typst"  # resolved, not "typst"


def test_render_pdf_skips_cleanly_when_typst_absent(tmp_path: Path, monkeypatch) -> None:
    from halyard import invoicing

    monkeypatch.setattr(invoicing.shutil, "which", lambda _name: None)
    msg = invoicing.render_pdf(tmp_path / "inv.typ")
    assert msg is not None and "typst not found" in msg


# --- Risk 2: timeclock structural anomalies surfaced, not swallowed --------


def test_timeclock_anomalies_detects_double_in_and_orphan_out(tmp_path: Path) -> None:
    from halyard.reports import timeclock_anomalies

    tc = tmp_path / "time.timeclock"
    tc.write_text(
        "i 2026-05-16 09:00:00 acme:web\n"
        "i 2026-05-16 10:00:00 acme:web\n"  # second open — first is lost
        "o 2026-05-16 11:00:00\n"
        "o 2026-05-16 12:00:00\n"  # orphan close — no open
    )
    dropped, orphans = timeclock_anomalies(tc)
    assert dropped == 1
    assert orphans == 1


def test_timeclock_health_warns_on_structural_issue(tmp_path: Path) -> None:
    from halyard.reports import _timeclock_check

    tc = tmp_path / "time.timeclock"
    tc.write_text("i 2026-05-16 09:00:00 acme:web\ni 2026-05-16 10:00:00 acme:web\n")
    check = _timeclock_check(tc)
    assert check.status == "warning"
    assert "undercounted" in check.detail


def test_clean_timeclock_stays_healthy(tmp_path: Path) -> None:
    from halyard.reports import _timeclock_check, timeclock_anomalies

    tc = tmp_path / "time.timeclock"
    tc.write_text("i 2026-05-16 09:00:00 acme:web\no 2026-05-16 10:00:00\n")
    assert timeclock_anomalies(tc) == (0, 0)
    assert _timeclock_check(tc).status == "healthy"
