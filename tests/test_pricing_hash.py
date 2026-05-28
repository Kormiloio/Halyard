"""Tests for D-5: pricing table hash pinning.

Gap 8: truncated HTTP response does not overwrite local table or update hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import halyard.pricing as pricing_mod
from halyard.pricing import (
    PricingFetchError,
    PricingHashChangedError,
    _check_pricing_hash,
    update_pricing,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOML = b"""\
[models.model-a]
input = 1.00
output = 4.00

[models.model-b]
input = 2.00
output = 8.00

[models.model-c]
input = 0.50
output = 2.00
"""

_CHANGED_TOML = b"""\
[models.model-a]
input = 9.99
output = 39.99

[models.model-b]
input = 2.00
output = 8.00

[models.model-c]
input = 0.50
output = 2.00
"""


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _reset_cache() -> None:
    pricing_mod._merged_table = None


def _mock_resp(body: bytes) -> MagicMock:
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.geturl.return_value = pricing_mod._REMOTE_URL
    return mock


# ---------------------------------------------------------------------------
# _check_pricing_hash unit tests
# ---------------------------------------------------------------------------


def test_first_fetch_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No stored hash → accept silently, return True."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = _check_pricing_hash(_VALID_TOML)

    assert result is True
    captured = capsys.readouterr()
    assert "Warning" not in captured.err


def test_matching_hash_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stored hash matches fetched body → accept silently, return True."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Write the hash first
    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(_sha256(_VALID_TOML) + "\n", encoding="utf-8")

    result = _check_pricing_hash(_VALID_TOML)

    assert result is True
    captured = capsys.readouterr()
    assert "Warning" not in captured.err


def test_changed_pricing_table_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stored hash differs from new body → warning printed, return False."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Store hash of original
    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(_sha256(_VALID_TOML) + "\n", encoding="utf-8")

    result = _check_pricing_hash(_CHANGED_TOML)

    assert result is False
    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "pricing table has changed" in captured.err


# ---------------------------------------------------------------------------
# Gap 8: truncated response — local table and hash must not be updated
# ---------------------------------------------------------------------------


def test_truncated_response_no_overwrite(tmp_path: Path) -> None:
    """A response with < 3 models (truncation sentinel) must not overwrite local table."""
    _reset_cache()
    local = tmp_path / "pricing.toml"
    original_content = "[models.existing]\ninput = 5.0\noutput = 20.0\n"
    local.write_text(original_content, encoding="utf-8")

    truncated_body = b"[models.only-one]\ninput = 1.0\noutput = 4.0\n"
    mock = _mock_resp(truncated_body)

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock),
        pytest.raises(PricingFetchError, match="only 1 model"),
    ):
        update_pricing()

    # Local table must be unchanged
    assert local.read_text(encoding="utf-8") == original_content
    _reset_cache()


def test_truncated_response_hash_not_updated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncated response must not update the pricing hash file."""
    _reset_cache()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    local = tmp_path / "pricing.toml"
    local.write_text(
        "[models.a]\ninput=1.0\noutput=4.0\n"
        "[models.b]\ninput=2.0\noutput=8.0\n"
        "[models.c]\ninput=0.5\noutput=2.0\n",
        encoding="utf-8",
    )

    # Pre-populate the hash file with the known-good hash
    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    original_hash = "aabbccdd" * 8  # fake known-good hash
    hash_file.write_text(original_hash + "\n", encoding="utf-8")

    truncated_body = b"[models.only-one]\ninput = 1.0\noutput = 4.0\n"
    mock = _mock_resp(truncated_body)

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock),
        pytest.raises(PricingFetchError),
    ):
        update_pricing()

    # Hash file must be unchanged
    assert hash_file.read_text(encoding="utf-8").strip() == original_hash
    _reset_cache()


# ---------------------------------------------------------------------------
# Hash written after successful fetch
# ---------------------------------------------------------------------------


def test_successful_fetch_writes_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a successful update_pricing() the hash file must be written."""
    _reset_cache()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    local = tmp_path / "pricing.toml"

    mock = _mock_resp(_VALID_TOML)

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock),
    ):
        update_pricing()

    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    assert hash_file.exists()
    assert hash_file.read_text(encoding="utf-8").strip() == _sha256(_VALID_TOML)
    _reset_cache()


def test_changed_table_warning_on_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """update_pricing() with a changed body must emit a warning via _check_pricing_hash."""
    _reset_cache()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    local = tmp_path / "pricing.toml"

    # Pre-populate stored hash for original table
    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(_sha256(_VALID_TOML) + "\n", encoding="utf-8")

    # Serve the changed table
    mock = _mock_resp(_CHANGED_TOML)

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock),
        pytest.raises(PricingHashChangedError),
    ):
        update_pricing()

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "pricing table has changed" in captured.err
    _reset_cache()


def test_changed_pricing_table_does_not_overwrite_without_accept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without --accept-changed, a hash mismatch must NOT replace the local table."""
    _reset_cache()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    local = tmp_path / "pricing.toml"
    local.write_bytes(_VALID_TOML)  # local has the original table

    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(_sha256(_VALID_TOML) + "\n", encoding="utf-8")  # baseline matches local

    mock = _mock_resp(_CHANGED_TOML)  # remote serves a different table

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock),
        pytest.raises(PricingHashChangedError),
    ):
        update_pricing(accept_changed=False)

    # Local table must still match the original — NOT the changed remote body.
    assert local.read_bytes() == _VALID_TOML
    # Stored hash must still be the original — not the new one.
    assert hash_file.read_text(encoding="utf-8").strip() == _sha256(_VALID_TOML)
    _reset_cache()


def test_changed_pricing_table_accept_flag_overwrites_and_updates_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With --accept-changed, the local table is updated and the stored hash refreshed."""
    _reset_cache()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    local = tmp_path / "pricing.toml"
    local.write_bytes(_VALID_TOML)

    hash_file = tmp_path / ".halyard" / "pricing-hash.txt"
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(_sha256(_VALID_TOML) + "\n", encoding="utf-8")

    mock = _mock_resp(_CHANGED_TOML)

    with (
        patch.object(pricing_mod, "_LOCAL_PRICING_FILE", local),
        patch("urllib.request.urlopen", return_value=mock),
    ):
        update_pricing(accept_changed=True)

    # Local table is now the changed body.
    assert local.read_bytes() == _CHANGED_TOML
    # And the stored hash has been refreshed.
    assert hash_file.read_text(encoding="utf-8").strip() == _sha256(_CHANGED_TOML)
    _reset_cache()
