"""v5.11 — loose ends: committable alias map, log hygiene, test isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from halyard import ai_log, attribution


@pytest.fixture(autouse=True)
def _reset_alias_cache():
    attribution._alias_cache = None
    yield
    attribution._alias_cache = None


def _write_aliases(path: Path, mapping: dict[str, str]) -> None:
    body = "[aliases]\n" + "".join(f'"{k}" = "{v}"\n' for k, v in mapping.items())
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Committable alias map
# ---------------------------------------------------------------------------


def test_committed_alias_file_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(attribution, "_ALIASES_PATH", tmp_path / "home" / "project-aliases.toml")
    proj = tmp_path / "proj"
    proj.mkdir()
    _write_aliases(proj / "project-aliases.toml", {"git/Foo": "acme:foo"})

    aliases = attribution.load_project_aliases(proj)
    assert aliases == {"git/Foo": "acme:foo"}


def test_home_overrides_committed(tmp_path, monkeypatch):
    home = tmp_path / "home" / "project-aliases.toml"
    home.parent.mkdir(parents=True)
    monkeypatch.setattr(attribution, "_ALIASES_PATH", home)
    proj = tmp_path / "proj"
    proj.mkdir()
    _write_aliases(proj / "project-aliases.toml", {"git/Foo": "acme:foo", "x": "committed"})
    _write_aliases(home, {"x": "local"})

    aliases = attribution.load_project_aliases(proj)
    # committed baseline merged, but the home value wins for a shared key
    assert aliases == {"git/Foo": "acme:foo", "x": "local"}


def test_no_project_dir_reads_home_only(tmp_path, monkeypatch):
    home = tmp_path / "home" / "project-aliases.toml"
    home.parent.mkdir(parents=True)
    monkeypatch.setattr(attribution, "_ALIASES_PATH", home)
    _write_aliases(home, {"a": "b"})
    assert attribution.load_project_aliases() == {"a": "b"}


def test_cache_invalidated_when_committed_file_appears(tmp_path, monkeypatch):
    monkeypatch.setattr(attribution, "_ALIASES_PATH", tmp_path / "home" / "project-aliases.toml")
    proj = tmp_path / "proj"
    proj.mkdir()
    assert attribution.load_project_aliases(proj) == {}  # caches the "absent" sig
    _write_aliases(proj / "project-aliases.toml", {"git/Foo": "acme:foo"})
    # New file → new sig → cache miss → re-read.
    assert attribution.load_project_aliases(proj) == {"git/Foo": "acme:foo"}


def test_set_project_alias_writes_committed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(attribution, "_ALIASES_PATH", tmp_path / "home" / "project-aliases.toml")
    proj = tmp_path / "proj"
    proj.mkdir()
    attribution.set_project_alias("git/Foo", "acme:foo", proj)

    committed = proj / "project-aliases.toml"
    assert committed.exists()
    assert "git/Foo" in committed.read_text(encoding="utf-8")
    assert not (tmp_path / "home" / "project-aliases.toml").exists()
    assert attribution.load_project_aliases(proj) == {"git/Foo": "acme:foo"}


def test_set_project_alias_without_dir_writes_home(tmp_path, monkeypatch):
    home = tmp_path / "home" / "project-aliases.toml"
    monkeypatch.setattr(attribution, "_ALIASES_PATH", home)
    attribution.set_project_alias("git/Foo", "acme:foo")
    assert home.exists() and "git/Foo" in home.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# log_diagnostic newline hygiene
# ---------------------------------------------------------------------------


def test_log_diagnostic_collapses_newlines(tmp_path, monkeypatch):
    log = tmp_path / "diagnostic.log"
    monkeypatch.setattr(ai_log, "_HALYARD_DIAG_LOG", log)
    ai_log.log_diagnostic("line one\nline two\r\nthree", tool="a\nb", project="p\nq")
    content = log.read_text(encoding="utf-8")
    assert content.count("\n") == 1  # exactly one trailing newline → one entry
    assert "line one line two three" in content
    assert "[a b]" in content and "[p q]" in content


# ---------------------------------------------------------------------------
# Test isolation: the real ~/.halyard logs are never written by the suite
# ---------------------------------------------------------------------------


def test_real_diag_log_untouched_by_diagnostics():
    # The autouse _isolate_halyard_logs fixture must have redirected the target
    # away from the real path; a diagnostic write lands in the tmp redirect.
    real = Path.home() / ".halyard" / "diagnostic.log"
    assert real != ai_log._HALYARD_DIAG_LOG
    before = real.read_text(encoding="utf-8") if real.exists() else None
    ai_log.log_diagnostic("isolation probe — must not hit the real log")
    after = real.read_text(encoding="utf-8") if real.exists() else None
    assert after == before  # real log unchanged
    assert "isolation probe" in ai_log._HALYARD_DIAG_LOG.read_text(encoding="utf-8")
