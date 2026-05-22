"""Regression tests for v2.41 trust-hardening."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from halyard import cli_hooks, pricing
from halyard.cli_hooks import HookWriteError, _halyard_exe, _load_existing_settings

# --- #1 pricing: no redirects + host pin -----------------------------------


def _resp(body: bytes, url: str) -> MagicMock:
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.read.return_value = body
    m.geturl.return_value = url
    return m


def test_update_pricing_rejects_foreign_final_host(tmp_path: Path) -> None:
    """A redirect that lands off raw.githubusercontent.com (final URL) is
    rejected before the body is trusted."""
    resp = _resp(b"[models.a]\ninput=1\noutput=2\n", "https://evil.example.com/x.toml")
    with (
        patch.object(pricing, "_LOCAL_PRICING_FILE", tmp_path / "p.toml"),
        patch("urllib.request.urlopen", return_value=resp),
        pytest.raises(pricing.PricingFetchError, match="unexpected origin"),
    ):
        pricing.update_pricing()


def test_update_pricing_rejects_non_https_final_url(tmp_path: Path) -> None:
    resp = _resp(
        b"[models.a]\ninput=1\noutput=2\n",
        "http://raw.githubusercontent.com/x.toml",
    )
    with (
        patch.object(pricing, "_LOCAL_PRICING_FILE", tmp_path / "p.toml"),
        patch("urllib.request.urlopen", return_value=resp),
        pytest.raises(pricing.PricingFetchError, match="unexpected origin"),
    ):
        pricing.update_pricing()


# --- #2 _halyard_exe trust order -------------------------------------------


def test_halyard_exe_prefers_trusted_which() -> None:
    with (
        patch("halyard.cli_hooks.shutil.which", return_value="/usr/bin/halyard"),
        patch("halyard.cli_hooks._is_trusted_exe_path", return_value=True),
    ):
        assert _halyard_exe() == str(Path("/usr/bin/halyard").resolve())


def test_halyard_exe_rejects_untrusted_which_and_uses_trusted_argv0(tmp_path: Path) -> None:
    evil = tmp_path / "evil" / "halyard"
    trusted = tmp_path / "trusted" / "bin" / "halyard"
    evil.parent.mkdir(parents=True)
    trusted.parent.mkdir(parents=True)
    evil.write_text("#!/bin/sh\n")
    trusted.write_text("#!/bin/sh\n")

    def _trusted(path: Path) -> bool:
        return path == trusted.resolve()

    with (
        patch("halyard.cli_hooks.shutil.which", return_value=str(evil)),
        patch("halyard.cli_hooks.sys.argv", [str(trusted)]),
        patch("halyard.cli_hooks._is_trusted_exe_path", side_effect=_trusted),
    ):
        assert _halyard_exe() == str(trusted.resolve())


def test_halyard_exe_rejects_untrusted_argv0(tmp_path: Path) -> None:
    evil = tmp_path / "halyard"
    evil.write_text("#!/bin/sh\n")
    with (
        patch("halyard.cli_hooks.shutil.which", return_value=None),
        patch("halyard.cli_hooks.sys.argv", [str(evil)]),
    ):
        # A halyard-named file in a writable temp dir must NOT be embedded.
        assert _halyard_exe() == "halyard"


# --- #4 cli_hooks: never clobber unparseable config ------------------------


def test_load_existing_settings_absent_and_empty(tmp_path: Path) -> None:
    assert _load_existing_settings(tmp_path / "nope.json") == {}
    empty = tmp_path / "e.json"
    empty.write_text("   \n")
    assert _load_existing_settings(empty) == {}


def test_load_existing_settings_valid(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    f.write_text('{"hooks": {}}')
    assert _load_existing_settings(f) == {"hooks": {}}


def test_load_existing_settings_refuses_to_clobber_invalid(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    original = '{"hooks": {} // a JSONC comment Claude tolerates\n}'
    f.write_text(original)
    with pytest.raises(HookWriteError, match="not valid JSON"):
        _load_existing_settings(f)
    # The user's file must be left exactly as it was.
    assert f.read_text() == original


def test_load_existing_settings_rejects_non_object(tmp_path: Path) -> None:
    f = tmp_path / "s.json"
    f.write_text("[1, 2, 3]")
    with pytest.raises(HookWriteError, match="not a JSON object"):
        _load_existing_settings(f)


def test_hookwriteerror_is_oserror() -> None:
    # The best-effort auto-install path relies on `except OSError`.
    assert issubclass(HookWriteError, OSError)


def test_install_claude_hook_leaves_bad_config_untouched(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    bad = "{ broken json"
    settings.write_text(bad)
    with (
        patch("halyard.cli_hooks.Path.cwd", return_value=tmp_path),
        pytest.raises(HookWriteError),
    ):
        cli_hooks._do_install_hook_claude(global_=False)
    assert settings.read_text() == bad
