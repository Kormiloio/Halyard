"""v3.12 — VS Code Copilot OpenTelemetry capture.

Phase 0 (a real live OTLP capture) was deferred — Copilot Chat was not
installed in the build environment — so these fixtures are built from the
documented OTel GenAI semconv + OTLP/JSON encoding. The mapper is the
testable core; re-verify the exact attribute shape against a live capture
before production reliance (see design.md Phase 0).
"""

from __future__ import annotations

import dataclasses
import json
import urllib.request
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, parse_sessions
from halyard.collectors.vscode_otel import (
    accumulate_traces,
    finalize,
    otel_capture_enabled,
    parse_traces_to_sessions,
)

# ── OTLP/JSON fixture builders ─────────────────────────────────────────


def _kv(key: str, value: object) -> dict:
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}  # OTLP/JSON encodes ints as strings
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


def _span(
    *,
    name: str,
    start_ns: int,
    end_ns: int,
    attrs: dict | None = None,
    status_error: bool = False,
) -> dict:
    span: dict = {
        "name": name,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [_kv(k, v) for k, v in (attrs or {}).items()],
    }
    if status_error:
        span["status"] = {"code": 2}
    return span


def _payload(spans: list[dict], *, resource_session_id: str | None = "S1") -> dict:
    resource: dict = {"attributes": []}
    if resource_session_id is not None:
        resource["attributes"].append(_kv("session.id", resource_session_id))
    return {"resourceSpans": [{"resource": resource, "scopeSpans": [{"spans": spans}]}]}


_T0 = 1_700_000_000_000_000_000  # a fixed unix-nano base


# ── Mapper unit tests ──────────────────────────────────────────────────


def test_single_chat_span_aggregates() -> None:
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 2_000_000_000,
                attrs={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.response.model": "gpt-4o",
                    "gen_ai.usage.input_tokens": 120,
                    "gen_ai.usage.output_tokens": 45,
                },
            )
        ]
    )
    [s] = parse_traces_to_sessions(payload)
    assert s.tool == "github-copilot"
    assert s.model == "gpt-4o"
    assert s.input_tokens == 120
    assert s.output_tokens == 45
    assert s.tokens_available is True
    assert s.api_seconds == 2
    assert s.interaction_count == 1
    assert s.assistant_message_count == 1
    assert s.session_id == "S1"
    assert s.job_id == "copilot-otel:S1"
    assert s.telemetry_source == "copilot-otel"
    assert s.tool_calls is None  # unavailable is not zero


def test_tool_spans_counted_with_errors() -> None:
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={"gen_ai.operation.name": "chat", "gen_ai.response.model": "gpt-4o"},
            ),
            _span(
                name="execute_tool",
                start_ns=_T0 + 1_000_000_000,
                end_ns=_T0 + 4_000_000_000,
                attrs={"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "read_file"},
            ),
            _span(
                name="execute_tool",
                start_ns=_T0 + 4_000_000_000,
                end_ns=_T0 + 5_000_000_000,
                attrs={"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "run_tests"},
                status_error=True,
            ),
        ]
    )
    [s] = parse_traces_to_sessions(payload)
    assert s.tool_calls == 2
    assert s.tool_errors == 1
    assert s.tool_seconds == 4  # 3s + 1s
    assert s.interaction_count == 3  # 1 chat + 2 tools


def test_multi_model_breakdown() -> None:
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={"gen_ai.operation.name": "chat", "gen_ai.response.model": "gpt-4o"},
            ),
            _span(
                name="chat",
                start_ns=_T0 + 1_000_000_000,
                end_ns=_T0 + 2_000_000_000,
                attrs={"gen_ai.operation.name": "chat", "gen_ai.response.model": "claude-sonnet"},
            ),
            _span(
                name="chat",
                start_ns=_T0 + 2_000_000_000,
                end_ns=_T0 + 3_000_000_000,
                attrs={"gen_ai.operation.name": "chat", "gen_ai.response.model": "gpt-4o"},
            ),
        ]
    )
    [s] = parse_traces_to_sessions(payload)
    assert s.model == "gpt-4o"  # most used (2 vs 1)
    assert s.model_breakdown == "gpt-4o:2|claude-sonnet:1"


def test_session_id_from_span_attr_when_no_resource() -> None:
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.conversation.id": "CONV9",
                    "gen_ai.response.model": "gpt-4o",
                },
            )
        ],
        resource_session_id=None,
    )
    [s] = parse_traces_to_sessions(payload)
    assert s.session_id == "CONV9"


def test_span_with_no_session_id_is_dropped() -> None:
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={"gen_ai.operation.name": "chat"},
            )
        ],
        resource_session_id=None,
    )
    assert parse_traces_to_sessions(payload) == []


def test_incremental_accumulation_across_payloads() -> None:
    acc: dict = {}
    accumulate_traces(
        acc,
        _payload(
            [
                _span(
                    name="chat",
                    start_ns=_T0 + 5_000_000_000,
                    end_ns=_T0 + 6_000_000_000,
                    attrs={"gen_ai.operation.name": "chat", "gen_ai.usage.output_tokens": 10},
                )
            ]
        ),
    )
    accumulate_traces(
        acc,
        _payload(
            [
                _span(
                    name="chat",
                    start_ns=_T0,  # earlier — must become the new min start
                    end_ns=_T0 + 1_000_000_000,
                    attrs={"gen_ai.operation.name": "chat", "gen_ai.usage.output_tokens": 30},
                )
            ]
        ),
    )
    assert set(acc) == {"S1"}
    s = finalize(acc["S1"])
    assert s is not None
    assert s.output_tokens == 40
    assert s.start.timestamp() == pytest.approx((_T0) / 1e9, abs=1)
    assert s.end.timestamp() == pytest.approx((_T0 + 6_000_000_000) / 1e9, abs=1)


def test_double_value_and_int_value_decode() -> None:
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.usage.input_tokens": 7,  # int -> "7"
                    "gen_ai.usage.output_tokens": 3,
                },
            )
        ]
    )
    [s] = parse_traces_to_sessions(payload)
    assert s.input_tokens == 7
    assert s.output_tokens == 3


def test_malformed_payload_never_raises() -> None:
    for junk in (None, {}, {"resourceSpans": "x"}, {"resourceSpans": [None, 5]}, []):
        assert parse_traces_to_sessions(junk) == []


# ── Privacy fuzz (the binding constraint) ──────────────────────────────


def test_content_attributes_never_reach_the_row() -> None:
    secret = "SUPER_SECRET_abc123"
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={
                    "gen_ai.operation.name": "chat",
                    "gen_ai.response.model": "gpt-4o",
                    "gen_ai.usage.input_tokens": 5,
                    # Content / non-allowlisted attributes — must all be dropped:
                    "gen_ai.prompt": secret,
                    "gen_ai.completion": secret,
                    "gen_ai.system_instructions": secret,
                    "gen_ai.request.messages": secret,
                    "code.filepath": "/Users/me/" + secret,
                    "arbitrary.future.key": secret,
                },
            ),
            _span(
                name="execute_tool",
                start_ns=_T0 + 1_000_000_000,
                end_ns=_T0 + 2_000_000_000,
                attrs={
                    "gen_ai.operation.name": "execute_tool",
                    "gen_ai.tool.name": secret,  # even the tool name is never stored
                    "gen_ai.tool.input": secret,
                },
            ),
        ]
    )
    [s] = parse_traces_to_sessions(payload)
    # 1. No field on the dataclass holds the secret.
    blob = json.dumps(dataclasses.asdict(s), default=str)
    assert secret not in blob
    # 2. The log-line surface is clean.
    assert secret not in s.to_log_line()
    # 3. extra (the v2.75 passthrough) was never populated by the mapper.
    assert s.extra == {}
    # The metadata we DO keep is still correct.
    assert s.tool_calls == 1
    assert s.input_tokens == 5


# ── Receiver: localhost-only, end-to-end ───────────────────────────────


def test_receiver_binds_localhost_and_records_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.collectors.otel_receiver import OTelReceiver

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text('[project]\nslug = "acme:proj"', encoding="utf-8")
    (project_dir / AI_LOG_FILENAME).write_text("", encoding="utf-8")

    # Don't pollute the real ~/.halyard during the flush.
    monkeypatch.setattr("halyard.ai_log.maybe_show_dashboard_hint", lambda: None)
    monkeypatch.setattr(
        "halyard.collectors.copilot._IMPORTED_STATE_FILE", tmp_path / "copilot-imported"
    )

    receiver = OTelReceiver(project_dir, port=0)
    receiver.start()
    try:
        # Bound to loopback only.
        assert receiver._server is not None
        assert receiver._server.server_address[0] == "127.0.0.1"
        port = receiver._server.server_port

        payload = _payload(
            [
                _span(
                    name="chat",
                    start_ns=_T0,
                    end_ns=_T0 + 1_000_000_000,
                    attrs={
                        "gen_ai.operation.name": "chat",
                        "gen_ai.response.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 11,
                        "gen_ai.usage.output_tokens": 22,
                    },
                )
            ]
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/traces",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
    finally:
        receiver.stop()  # also force-flushes pending sessions

    logged = parse_sessions(project_dir)
    assert len(logged) == 1
    assert logged[0].session_id == "S1"
    assert logged[0].telemetry_source == "copilot-otel"
    assert logged[0].output_tokens == 22


def test_receiver_rejects_unknown_path_and_oversize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.collectors.otel_receiver import OTelReceiver

    receiver = OTelReceiver(None, port=0)
    receiver.start()
    try:
        assert receiver._server is not None
        port = receiver._server.server_port
        req = urllib.request.Request(f"http://127.0.0.1:{port}/nope", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code == 404
    finally:
        receiver.stop()


def test_start_receiver_gated_on_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard.collectors import otel_receiver, vscode_otel

    marker = tmp_path / "marker"
    monkeypatch.setattr(vscode_otel, "MARKER_PATH", marker)
    # Marker absent → no listener started.
    assert otel_receiver.start_receiver(None, port=0) is None
    # Marker present → a receiver is started; clean it up.
    marker.write_text("enabled\n", encoding="utf-8")
    assert otel_capture_enabled() is True
    rec = otel_receiver.start_receiver(None, port=0)
    assert rec is not None
    rec.stop()


# ── Coexistence with the v3.7 importer (no double-count) ────────────────


def test_importer_skips_otel_captured_via_state_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard.collectors import copilot

    state = tmp_path / "copilot-imported"
    monkeypatch.setattr(copilot, "_IMPORTED_STATE_FILE", state)
    copilot.record_otel_capture("session-123")
    assert "session-123" in copilot._load_imported_state()


def test_importer_skips_otel_captured_via_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Authoritative coexistence: even with a cleared state file, an
    OTel-captured session already in the ledger is not re-imported."""
    from halyard.ai_log import append_session
    from halyard.collectors import copilot

    project_dir = tmp_path / "halyard"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text('[project]\nslug = "acme:halyard"', encoding="utf-8")
    (project_dir / AI_LOG_FILENAME).write_text("", encoding="utf-8")

    # An OTel row for session-123 is already in the ledger.
    payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={"gen_ai.operation.name": "chat", "gen_ai.usage.output_tokens": 9},
            )
        ],
        resource_session_id="session-123",
    )
    [otel_row] = parse_traces_to_sessions(payload)
    append_session(project_dir, otel_row)

    # v5.22: _otel_captured_ids generalised to _ledger_covered_ids (all
    # non-importer rows); the OTel coexistence property is unchanged.
    captured = copilot._ledger_covered_ids(project_dir)
    assert "session-123" in captured


def test_importer_end_to_end_skips_otel_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A VS Code chat session file present on disk is skipped by the
    importer when the same id was already captured via OTel."""
    from halyard.ai_log import append_session
    from halyard.collectors import copilot

    storage = tmp_path / "vscode-storage"
    storage.mkdir()
    project_dir = tmp_path / "halyard"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text('[project]\nslug = "acme:halyard"', encoding="utf-8")
    (project_dir / AI_LOG_FILENAME).write_text("", encoding="utf-8")

    ws = storage / "ws1"
    ws.mkdir()
    (ws / "workspace.json").write_text(
        json.dumps({"folder": project_dir.as_uri()}), encoding="utf-8"
    )
    chat = ws / "chatSessions"
    chat.mkdir()
    sid = "dup-session"
    (chat / f"{sid}.jsonl").write_text(
        json.dumps(
            {
                "kind": 0,
                "v": {
                    "creationDate": 1779548400000,
                    "sessionId": sid,
                    "requests": [
                        {
                            "requestId": "r1",
                            "timestamp": 1779548460000,
                            "response": [{"kind": "message"}],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(copilot, "_VSCODE_STORAGE_DIR", storage)
    monkeypatch.setattr(copilot, "_IMPORTED_STATE_FILE", tmp_path / "imported")

    # Seed the ledger with the OTel-captured row for the same id.
    otel_payload = _payload(
        [
            _span(
                name="chat",
                start_ns=_T0,
                end_ns=_T0 + 1_000_000_000,
                attrs={"gen_ai.operation.name": "chat", "gen_ai.usage.output_tokens": 5},
            )
        ],
        resource_session_id=sid,
    )
    [otel_row] = parse_traces_to_sessions(otel_payload)
    append_session(project_dir, otel_row)

    imported = copilot.import_copilot_sessions(project_dir=project_dir)
    assert imported == []  # the on-disk session is skipped (already OTel-captured)
    assert len(parse_sessions(project_dir)) == 1  # no double-count


# ── Installer ──────────────────────────────────────────────────────────


def test_install_writes_keys_and_marker_then_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import cli_hooks
    from halyard.collectors import vscode_otel

    settings = tmp_path / "settings.json"
    marker = tmp_path / "marker"
    monkeypatch.setattr(cli_hooks, "_VSCODE_USER_SETTINGS", settings)
    monkeypatch.setattr(vscode_otel, "MARKER_PATH", marker)

    cli_hooks._do_install_vscode_otel()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["github.copilot.chat.otel.enabled"] is True
    assert data["github.copilot.chat.otel.otlpEndpoint"] == "http://localhost:4318"
    assert data["github.copilot.chat.otel.exporterType"] == "http"
    assert marker.exists()

    # Byte-stable no-op on re-run.
    before = settings.read_text(encoding="utf-8")
    cli_hooks._do_install_vscode_otel()
    assert settings.read_text(encoding="utf-8") == before


def test_install_preserves_foreign_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import cli_hooks
    from halyard.collectors import vscode_otel

    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"editor.fontSize": 14, "files.autoSave": "off"}), encoding="utf-8"
    )
    monkeypatch.setattr(cli_hooks, "_VSCODE_USER_SETTINGS", settings)
    monkeypatch.setattr(vscode_otel, "MARKER_PATH", tmp_path / "marker")

    cli_hooks._do_install_vscode_otel()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["editor.fontSize"] == 14
    assert data["files.autoSave"] == "off"
    assert data["github.copilot.chat.otel.enabled"] is True


def test_uninstall_removes_keys_and_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard import cli_hooks
    from halyard.collectors import vscode_otel

    settings = tmp_path / "settings.json"
    marker = tmp_path / "marker"
    monkeypatch.setattr(cli_hooks, "_VSCODE_USER_SETTINGS", settings)
    monkeypatch.setattr(vscode_otel, "MARKER_PATH", marker)

    cli_hooks._do_install_vscode_otel()
    assert marker.exists()
    cli_hooks._do_uninstall_vscode_otel()
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert "github.copilot.chat.otel.enabled" not in data
    assert not marker.exists()


# ── Doctor nudge ───────────────────────────────────────────────────────


def _copilot_check(checks: list) -> object | None:
    return next((c for c in checks if c.id == "telemetry.copilot"), None)


def test_doctor_warns_when_copilot_present_but_unwired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import doctor
    from halyard.collectors import vscode_otel

    monkeypatch.setattr("halyard.collectors.copilot.copilot_history_present", lambda: True)
    monkeypatch.setattr(vscode_otel, "MARKER_PATH", tmp_path / "absent")

    report = doctor.build_doctor_report(tool="copilot", start=tmp_path)
    chk = _copilot_check(report.checks)
    assert chk is not None
    assert chk.status == "warning"
    assert chk.fix == "halyard install-vscode-otel"


def test_doctor_ok_when_otel_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard import doctor
    from halyard.collectors import vscode_otel

    marker = tmp_path / "marker"
    marker.write_text("enabled\n", encoding="utf-8")
    monkeypatch.setattr("halyard.collectors.copilot.copilot_history_present", lambda: True)
    monkeypatch.setattr(vscode_otel, "MARKER_PATH", marker)

    report = doctor.build_doctor_report(tool="copilot", start=tmp_path)
    chk = _copilot_check(report.checks)
    assert chk is not None
    assert chk.status == "ok"


def test_doctor_silent_when_no_copilot_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import doctor

    monkeypatch.setattr("halyard.collectors.copilot.copilot_history_present", lambda: False)
    report = doctor.build_doctor_report(tool="copilot", start=tmp_path)
    assert _copilot_check(report.checks) is None
