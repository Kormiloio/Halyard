"""Tests for D-3: org.toml change detection via SHA-256 hash pinning.

Gap 4: hash changes between runs produce a warning; unchanged content is silent.
Baselines are keyed on the hub directory so switching hubs/orgs does not
cross-contaminate or spuriously warn.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from halyard.org import _check_org_hash, _org_hash_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# D-3 / Gap 4: org.toml change detection
# ---------------------------------------------------------------------------


def test_first_run_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """First run (no stored hash) → hash written silently, no warning."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hub = tmp_path / "hub"
    hub.mkdir()

    content = b"[org]\nid = 'acme'\n"
    _check_org_hash(content, hub)

    captured = capsys.readouterr()
    assert "Warning" not in captured.err
    assert "Warning" not in captured.out

    # Hash file is keyed on hub path; just check the content matches.
    hash_file = _org_hash_path(hub)
    assert hash_file.exists()
    assert hash_file.read_text().strip() == _sha256(content)


def test_unchanged_org_no_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same content on two consecutive calls → no warning either time."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hub = tmp_path / "hub"
    hub.mkdir()

    content = b"[org]\nid = 'acme'\n"

    _check_org_hash(content, hub)  # first run — writes hash
    capsys.readouterr()  # clear

    _check_org_hash(content, hub)  # second run — same hash
    captured = capsys.readouterr()
    assert "Warning" not in captured.err


def test_changed_org_warning_emitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Changed content on second run → warning printed to stderr."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hub = tmp_path / "hub"
    hub.mkdir()

    original = b"[org]\nid = 'acme'\n"
    changed = b"[org]\nid = 'acme'\nname = 'Acme Corp'\n"

    _check_org_hash(original, hub)
    capsys.readouterr()

    _check_org_hash(changed, hub)
    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "org.toml has changed" in captured.err


def test_changed_org_hash_updated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """After a change the new hash must be stored for the next run."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hub = tmp_path / "hub"
    hub.mkdir()

    original = b"[org]\nid = 'acme'\n"
    changed = b"[org]\nid = 'acme'\nname = 'Acme Corp'\n"

    _check_org_hash(original, hub)
    capsys.readouterr()
    _check_org_hash(changed, hub)
    capsys.readouterr()

    hash_file = _org_hash_path(hub)
    assert hash_file.read_text().strip() == _sha256(changed)

    # Third call with new content should now be silent (hash matches updated stored)
    _check_org_hash(changed, hub)
    captured = capsys.readouterr()
    assert "Warning" not in captured.err


def test_two_hubs_have_independent_org_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Switching between two hubs must not warn or overwrite the other baseline.

    Sage's D-3 review note: a single global ``~/.halyard/org-hash.txt`` would
    falsely warn (or silently overwrite the baseline) when a user moves
    between two hubs with different org.toml contents. The hash MUST be
    keyed on the hub directory so each hub keeps its own baseline.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    hub_a = tmp_path / "hub_a"
    hub_b = tmp_path / "hub_b"
    hub_a.mkdir()
    hub_b.mkdir()

    content_a = b"[org]\nid = 'acme'\n"
    content_b = b"[org]\nid = 'beta'\n"

    # Seed each hub with its own content.
    _check_org_hash(content_a, hub_a)
    _check_org_hash(content_b, hub_b)
    capsys.readouterr()

    # Re-checking hub A with the same content must not warn — its baseline
    # was not overwritten by the hub B call.
    _check_org_hash(content_a, hub_a)
    captured = capsys.readouterr()
    assert "Warning" not in captured.err

    # And the two hubs MUST resolve to different hash files.
    assert _org_hash_path(hub_a) != _org_hash_path(hub_b)


def test_read_org_config_triggers_hash_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """read_org_config() must call _check_org_hash() so callers get warnings."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    org_toml = tmp_path / "org.toml"
    org_toml.write_text(
        "[org]\nid = 'acme'\nname = 'Acme'\n"
        "[[member]]\nemail = 'a@acme.com'\nteam_id = 't1'\n"
        "[[team]]\nid = 't1'\nname = 'Eng'\n"
    )

    from halyard.org import read_org_config

    # First call — no warning
    read_org_config(tmp_path)
    capsys.readouterr()

    # Mutate content to simulate external change
    org_toml.write_text(
        "[org]\nid = 'acme'\nname = 'Acme Updated'\n"
        "[[member]]\nemail = 'a@acme.com'\nteam_id = 't1'\n"
        "[[team]]\nid = 't1'\nname = 'Eng'\n"
    )

    read_org_config(tmp_path)
    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "org.toml has changed" in captured.err
