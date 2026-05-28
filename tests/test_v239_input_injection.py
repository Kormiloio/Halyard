"""Regression tests for v2.39 input-injection hardening."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

# --- #1 TOML injection via git user.name -----------------------------------


def test_sanitize_business_name_blocks_toml_breakout() -> None:
    from halyard.orchestration import (
        _HALYARD_TOML_TEMPLATE,
        _sanitize_business_name,
    )

    evil = 'x"\nadmin_override = true\n#'
    safe = _sanitize_business_name(evil)
    assert '"' not in safe
    assert "\\" not in safe
    assert "\n" not in safe

    rendered = _HALYARD_TOML_TEMPLATE.format(business_name=safe)
    parsed = tomllib.loads(rendered)
    assert "admin_override" not in parsed
    assert parsed["business"]["name"] == safe


def test_sanitize_business_name_empty_falls_back() -> None:
    from halyard.orchestration import _DEFAULT_BUSINESS_NAME, _sanitize_business_name

    assert _sanitize_business_name('"\\\n\t') == _DEFAULT_BUSINESS_NAME
    assert _sanitize_business_name("  Acme  ") == "Acme Consulting"


# --- #2 transcript_path validation -----------------------------------------


def test_safe_transcript_path_rejects_outside_allowlist() -> None:
    from halyard.collectors.claude_code import _safe_transcript_path

    assert _safe_transcript_path("/etc/passwd") is None
    assert _safe_transcript_path("") is None
    assert _safe_transcript_path("/nonexistent/nope.jsonl") is None


def test_safe_transcript_path_rejects_symlink_and_oversize(tmp_path: Path) -> None:
    from halyard.collectors import claude_code

    real = tmp_path / "real.jsonl"
    real.write_text('{"type":"assistant"}\n', encoding="utf-8")
    link = tmp_path / "link.jsonl"
    os.symlink(real, link)
    assert claude_code._safe_transcript_path(str(link)) is None

    big = tmp_path / "big.jsonl"
    big.write_text("x", encoding="utf-8")
    # Force the size check without writing 25MB.
    orig = claude_code._MAX_TRANSCRIPT_BYTES
    claude_code._MAX_TRANSCRIPT_BYTES = 0
    try:
        assert claude_code._safe_transcript_path(str(big)) is None
    finally:
        claude_code._MAX_TRANSCRIPT_BYTES = orig


def test_safe_transcript_path_accepts_normal_tmp_file(tmp_path: Path) -> None:
    from halyard.collectors.claude_code import _safe_transcript_path

    f = tmp_path / "t.jsonl"
    f.write_text('{"type":"assistant"}\n', encoding="utf-8")
    assert _safe_transcript_path(str(f)) == f.resolve()


def test_read_from_transcript_skips_bad_path() -> None:
    from halyard.collectors.claude_code import _read_from_transcript

    st = _read_from_transcript("/etc/passwd")
    assert st.model is None
    assert st.input_tokens == 0 and st.output_tokens == 0
    assert st.assistant_count == 0
    assert st.session_id is None and st.tool_calls is None


# --- #3 Gemini history size cap --------------------------------------------


def test_gemini_history_skips_oversized(tmp_path: Path) -> None:
    from halyard.collectors import gemini_history

    f = tmp_path / "session-abcd.json"
    f.write_text('{"sessionId":"abcd"}', encoding="utf-8")
    orig = gemini_history._MAX_HISTORY_BYTES
    gemini_history._MAX_HISTORY_BYTES = 0
    try:
        assert gemini_history._read_capped(f) is None
        assert gemini_history.parse_session_file(f) is None
    finally:
        gemini_history._MAX_HISTORY_BYTES = orig


# --- #7 config_history float guard -----------------------------------------


def test_safe_float_tolerates_malformed() -> None:
    from halyard.config_history import _safe_float

    assert _safe_float("1.2.3") is None
    assert _safe_float("") is None
    assert _safe_float("150.0") == pytest.approx(150.0)
