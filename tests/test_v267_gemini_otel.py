"""v2.67 — Gemini OpenTelemetry ingestion.

Fixtures use the **verified 0.41.1 framing**: the outfile is a stream
of concatenated pretty-printed JSON objects (NOT line-delimited), and
`session.id` is a *resource* attribute, not a per-record attribute
(see the v2.67 design.md Phase 0 contract).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, api_plus_tool_seconds


def _rec(session_id: str, event: str, duration_ms: int, **attrs: object) -> dict:
    return {
        "resource": {"attributes": {"service.name": "gemini-cli", "session.id": session_id}},
        "body": event,
        "severityText": "INFO",
        "attributes": {"duration_ms": duration_ms, **attrs},
    }


def _write_outfile(path: Path, records: list[dict]) -> None:
    # Exactly the FileExporter framing: JSON.stringify(rec, null, 2)+"\n",
    # appended (concatenated multi-line objects, NOT one per line).
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, indent=2) + "\n")


def _session(**kw: object) -> AiSession:
    start = datetime(2026, 5, 16, 9, 0, 0)
    base: dict = {
        "start": start,
        "end": start + timedelta(minutes=5),
        "tool": "gemini-cli",
        "model": "gemini-2.5-pro",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.01,
        "project": "acme:web",
    }
    base.update(kw)
    return AiSession(**base)


def test_reader_sums_by_session_real_framing(tmp_path: Path) -> None:
    from halyard.collectors.gemini_otel import read_otel_durations

    out = tmp_path / "otel.log"
    _write_outfile(
        out,
        [
            _rec("S1", "gemini_cli.api_response", 1200, model="gemini-2.5-pro"),
            _rec("S1", "gemini_cli.api_response", 800),
            _rec("S1", "gemini_cli.tool_call", 3000, function_name="read_file"),
            _rec("S2", "gemini_cli.api_response", 9999),  # other session, excluded
            _rec("S2", "gemini_cli.tool_call", 9999),
        ],
    )
    assert read_otel_durations(out, "S1") == (2, 3)  # round(2000/1000), round(3000/1000)


def test_collector_enriches_and_leaves_agent_active_untouched(tmp_path: Path) -> None:
    from halyard.collectors.gemini_otel import read_otel_durations, resolve_telemetry_outfile

    workspace = tmp_path / "ws"
    (workspace / ".gemini").mkdir(parents=True)
    out = workspace / "tel.log"
    (workspace / ".gemini" / "settings.json").write_text(
        json.dumps({"telemetry": {"enabled": True, "target": "local", "outfile": str(out)}})
    )
    _write_outfile(
        out,
        [
            _rec("SID", "gemini_cli.api_response", 4000),
            _rec("SID", "gemini_cli.tool_call", 1000),
        ],
    )
    resolved = resolve_telemetry_outfile(workspace)
    assert resolved == str(out)
    api_s, tool_s = read_otel_durations(resolved, "SID")
    s = _session(session_id="SID", agent_active_seconds=42, api_seconds=api_s, tool_seconds=tool_s)
    assert (s.api_seconds, s.tool_seconds) == (4, 1)
    assert s.agent_active_seconds == 42  # independent field, untouched


def test_unavailable_is_none_not_zero(tmp_path: Path) -> None:
    from halyard.collectors.gemini_otel import read_otel_durations

    assert read_otel_durations(tmp_path / "absent.log", "S1") == (None, None)
    out = tmp_path / "otel.log"
    _write_outfile(out, [_rec("S1", "gemini_cli.api_response", 2500)])
    # api present, no tool records → tool stays None (not 0).
    # round(2500/1000) == round(2.5) == 2 (Python banker's rounding).
    assert read_otel_durations(out, "S1") == (2, None)
    assert read_otel_durations(out, "") == (None, None)


def test_bounded_read_malformed_and_oversized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.collectors import gemini_otel

    out = tmp_path / "otel.log"
    # Valid api record, then a truncated/garbage region, then a valid
    # tool record — the bad region is skipped, the rest still parses.
    good = json.dumps(_rec("S1", "gemini_cli.api_response", 5000), indent=2)
    tool = json.dumps(_rec("S1", "gemini_cli.tool_call", 2000), indent=2)
    out.write_text(good + "\n{ this is not json (((\n" + tool + "\n")
    assert gemini_otel.read_otel_durations(out, "S1") == (5, 2)

    # Oversized → fail closed to (None, None), no crash.
    monkeypatch.setattr(gemini_otel, "_MAX_OTEL_BYTES", 10)
    assert gemini_otel.read_otel_durations(out, "S1") == (None, None)


def test_privacy_content_never_read(tmp_path: Path) -> None:
    from halyard.collectors.gemini_otel import read_otel_durations

    out = tmp_path / "otel.log"
    _write_outfile(
        out,
        [
            _rec(
                "S1",
                "gemini_cli.api_response",
                1000,
                response_text="SECRET MODEL OUTPUT",
                request_text="SECRET PROMPT",
            ),
            _rec("S1", "gemini_cli.tool_call", 2000, function_args="{'path': '/etc/passwd'}"),
        ],
    )
    result = read_otel_durations(out, "S1")
    assert result == (1, 2)
    # The return is pure ints — no content can ride along.
    assert "SECRET" not in repr(result)


def test_round_trip_and_forward_compat() -> None:
    from halyard.ai_log import AiSession as A

    s = _session(api_seconds=7, tool_seconds=3, agent_active_seconds=99)
    line = s.to_log_line()
    assert "api_seconds=7" in line and "tool_seconds=3" in line
    back = A.from_log_line(line)
    assert back is not None
    assert (back.api_seconds, back.tool_seconds) == (7, 3)
    assert back.agent_active_seconds == 99

    # An old line without the tokens parses with both None; helper None.
    old = _session(agent_active_seconds=99)
    old_back = A.from_log_line(old.to_log_line())
    assert old_back is not None
    assert old_back.api_seconds is None and old_back.tool_seconds is None
    assert api_plus_tool_seconds(old_back) is None
    assert old_back.agent_active_seconds == 99


def test_install_gemini_telemetry_no_op_and_preserves_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import cli_hooks

    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    settings = home / ".gemini" / "settings.json"
    settings.write_text(
        json.dumps(
            {"defaultModel": "x", "telemetry": {"otlpEndpoint": "http://foreign:4317"}},
            indent=2,
        )
        + "\n"
    )

    cli_hooks._do_install_gemini_telemetry()
    data = json.loads(settings.read_text())
    assert data["telemetry"]["enabled"] is True
    assert data["telemetry"]["target"] == "local"
    assert data["telemetry"]["logPrompts"] is False
    assert data["telemetry"]["outfile"].endswith("gemini-otel.log")
    assert data["telemetry"]["otlpEndpoint"] == "http://foreign:4317"  # foreign key kept
    assert data["defaultModel"] == "x"

    # Byte-stable no-op on a second run.
    before = settings.read_text()
    cli_hooks._do_install_gemini_telemetry()
    assert settings.read_text() == before


def test_install_gemini_telemetry_refuses_bad_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import cli_hooks

    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    settings = home / ".gemini" / "settings.json"

    settings.write_text("{ not valid json")
    with pytest.raises(cli_hooks.HookWriteError):
        cli_hooks._do_install_gemini_telemetry()

    settings.write_text(json.dumps({"telemetry": "not-an-object"}))
    with pytest.raises(cli_hooks.HookWriteError):
        cli_hooks._do_install_gemini_telemetry()


def test_doctor_nudge_when_hook_on_telemetry_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.doctor import build_doctor_report

    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    (home / ".gemini" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "/b/halyard gc-session"}]}
                    ],
                    "AfterModel": [
                        {"hooks": [{"type": "command", "command": "/b/halyard gc-model"}]}
                    ],
                    "AfterAgent": [
                        {"hooks": [{"type": "command", "command": "/b/halyard gc-hook"}]}
                    ],
                }
            }
        )
    )
    report = build_doctor_report(start=tmp_path, tool="gemini")
    tel = [c for c in report.checks if c.id == "telemetry.gemini"]
    assert len(tel) == 1
    assert tel[0].status == "warning"
    assert tel[0].fix == "halyard install-gemini-telemetry"
    # The nudge itself is warn-only — it never contributes an error
    # status (the doctor exit code is error-only).
    assert all(c.status != "error" for c in report.checks if c.id == "telemetry.gemini")


def test_mcp_sessions_exposes_api_tool_seconds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from halyard import mcp_server

    monkeypatch.setattr(
        mcp_server,
        "_aggregate_sessions",
        lambda: [_session(api_seconds=12, tool_seconds=4)],
    )
    rows = mcp_server._sessions(limit=5)
    assert rows and rows[0]["api_seconds"] == 12 and rows[0]["tool_seconds"] == 4
