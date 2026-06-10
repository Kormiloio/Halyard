"""v5.19 parallel-review follow-ups — regression coverage for findings the
owner's external audit caught that the in-tree v5.19 work missed.

Findings covered:
  * P1 timer-target: handler returns 400 on a supplied-but-unregistered target
    (not silent fall-through to the hub's ledger).
  * P1 negative Content-Length: _read_body rejects a negative declared length
    instead of dispatching `rfile.read(-1)`.
  * P1 OTel accumulator memory: per-session caps on session_id length and on
    model_counts cardinality (the per-session row in vscode_otel.py).
  * P2 integrity-mode migration: migrate_integrity_mode() lets a write at a
    weaker mode succeed by removing the stale stronger sidecar that the B13
    floor would otherwise enforce on the next read.
"""

from __future__ import annotations

import http.client
from pathlib import Path

import pytest

from halyard import hub_server, state_integrity
from halyard.collectors import vscode_otel

# ---------------------------------------------------------------------------
# P1 timer-target: rejected target raises so the handler returns 400.
# ---------------------------------------------------------------------------


def test_unregistered_target_dir_raises_for_handler_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An attacker-supplied unregistered project_dir must surface a typed
    rejection. The timer handler catches it and responds 400 instead of
    silently rewriting the hub's own ledger (the original bug)."""
    reg = tmp_path / "proj"
    reg.mkdir()
    (reg / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    evil = tmp_path / "evil"
    evil.mkdir()
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [reg])

    with pytest.raises(hub_server._RejectedTargetDirError):
        hub_server._target_project_dir({"project_dir": str(evil)})


# ---------------------------------------------------------------------------
# P1 negative Content-Length
# ---------------------------------------------------------------------------


def test_read_body_rejects_negative_content_length(tmp_path: Path) -> None:
    """A negative Content-Length must 400, not fall through to rfile.read(-1).

    Driven through the live Hub on the unauthenticated /v1/traces path so
    the body-length check is the only gate before _read_body's guard runs.
    """
    hub = hub_server.HubServer(project_dir=tmp_path, port=0)
    hub.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", hub.port, timeout=5)
        # Construct the request by hand so we can override Content-Length
        # without http.client recomputing it from the body.
        conn.putrequest("POST", "/v1/traces", skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", f"127.0.0.1:{hub.port}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "-1")
        conn.endheaders(message_body=b"")
        resp = conn.getresponse()
        body = resp.read()
        assert resp.status == 400
        assert b"negative" in body.lower() or b"content-length" in body.lower()
    finally:
        hub.stop()


# ---------------------------------------------------------------------------
# P1 OTel accumulator memory bounds
# ---------------------------------------------------------------------------


def _span(session_id: str, model: str | None = None) -> dict:
    attrs = [{"key": "session.id", "value": {"stringValue": session_id}}]
    if model is not None:
        attrs.append({"key": "gen_ai.response.model", "value": {"stringValue": model}})
    # Tiny but valid time range so _ingest_span proceeds.
    return {
        "name": "chat",
        "attributes": attrs,
        "startTimeUnixNano": "1700000000000000000",
        "endTimeUnixNano": "1700000000100000000",
    }


def _payload(spans: list[dict]) -> dict:
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def test_otel_rejects_overlong_session_id() -> None:
    """A session id longer than the cap must be dropped — without it, a single
    span could carry a multi-MB session id and grow accumulator memory."""
    acc: dict[str, vscode_otel._SessionAcc] = {}
    huge_sid = "x" * (vscode_otel._MAX_SESSION_ID_LEN + 1)
    vscode_otel.accumulate_traces(acc, _payload([_span(huge_sid)]))
    assert huge_sid not in acc
    assert not acc  # nothing else was created


def test_otel_caps_model_cardinality_per_session() -> None:
    """A flood of unique model strings must not grow model_counts unbounded.

    A real session has ≤10 distinct models; the cap is well above that.
    """
    acc: dict[str, vscode_otel._SessionAcc] = {}
    sid = "ok-sid"
    # Send many more distinct models than the cap.
    spans = [_span(sid, model=f"m-{i}") for i in range(vscode_otel._MAX_MODELS_PER_SESSION + 50)]
    vscode_otel.accumulate_traces(acc, _payload(spans))
    assert sid in acc
    assert len(acc[sid].model_counts) <= vscode_otel._MAX_MODELS_PER_SESSION


def test_otel_overlong_model_name_is_ignored() -> None:
    """A pathologically long model name is not folded into model_counts."""
    acc: dict[str, vscode_otel._SessionAcc] = {}
    sid = "ok-sid"
    big = "z" * (vscode_otel._MAX_MODEL_NAME_LEN + 1)
    vscode_otel.accumulate_traces(acc, _payload([_span(sid, model=big)]))
    assert sid in acc
    assert big not in acc[sid].model_counts


def test_otel_already_known_model_still_bumps_after_cap() -> None:
    """Once the per-session cap is reached, *new* models are refused but the
    existing entries keep counting — otherwise legitimate spans are dropped."""
    acc: dict[str, vscode_otel._SessionAcc] = {}
    sid = "ok-sid"
    # Fill to the cap.
    spans = [_span(sid, model=f"m-{i}") for i in range(vscode_otel._MAX_MODELS_PER_SESSION)]
    vscode_otel.accumulate_traces(acc, _payload(spans))
    assert len(acc[sid].model_counts) == vscode_otel._MAX_MODELS_PER_SESSION
    # Repeat one of the in-set models — its count must rise.
    before = acc[sid].model_counts["m-0"]
    vscode_otel.accumulate_traces(acc, _payload([_span(sid, model="m-0")]))
    assert acc[sid].model_counts["m-0"] == before + 1


# ---------------------------------------------------------------------------
# P2 integrity-mode migration
# ---------------------------------------------------------------------------


def test_migrate_integrity_mode_downgrade_clears_stale_hmac_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """write_trusted_state(hmac) → migrate_integrity_mode(off) → read clean.

    Without the migration helper, the stale .hmac sidecar would remain on
    disk and the B13 floor would enforce HMAC verification against the
    new (off-mode) content, raising IntegrityError on every read.
    """
    monkeypatch.setattr(state_integrity, "_KEY_PATH", tmp_path / "integrity.key")
    state_integrity._reset_cache_for_tests()
    path = tmp_path / "active"
    state_integrity.write_trusted_state(path, "first\n", mode="hmac")
    assert state_integrity._sidecar(path, "hmac").exists()

    state_integrity.migrate_integrity_mode(path, "second\n", new_mode="off")
    # The stale stronger sidecar must be gone — otherwise B13 would pin
    # the next read to the orphaned scheme.
    assert not state_integrity._sidecar(path, "hmac").exists()
    # Now the read succeeds cleanly under the resolved (off) mode.
    assert state_integrity.read_trusted_state(path, mode="off") == "second\n"


def test_migrate_integrity_mode_downgrade_to_hash_clears_hmac(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """hmac → hash also clears the orphan .hmac sidecar so the next read
    uses the (now-fresh) .sha256 sidecar instead of mismatched .hmac."""
    monkeypatch.setattr(state_integrity, "_KEY_PATH", tmp_path / "integrity.key")
    state_integrity._reset_cache_for_tests()
    path = tmp_path / "active"
    state_integrity.write_trusted_state(path, "first\n", mode="hmac")
    state_integrity.migrate_integrity_mode(path, "second\n", new_mode="hash")
    assert not state_integrity._sidecar(path, "hmac").exists()
    assert state_integrity._sidecar(path, "hash").exists()
    assert state_integrity.read_trusted_state(path, mode="hash") == "second\n"


def test_plain_write_after_hmac_still_floor_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: a routine write_trusted_state with a weaker mode
    must NOT clear the .hmac sidecar — only the explicit migrate path does.

    Without this guarantee, any caller could silently strip integrity.
    """
    monkeypatch.setattr(state_integrity, "_KEY_PATH", tmp_path / "integrity.key")
    state_integrity._reset_cache_for_tests()
    path = tmp_path / "active"
    state_integrity.write_trusted_state(path, "first\n", mode="hmac")
    state_integrity.write_trusted_state(path, "second\n", mode="off")
    # Stale sidecar is still there.
    assert state_integrity._sidecar(path, "hmac").exists()
    # And the next read fails closed (B13 floor) instead of silently
    # accepting the downgrade — proving the floor itself is intact.
    with pytest.raises(state_integrity.IntegrityError):
        state_integrity.read_trusted_state(path, mode="off")
