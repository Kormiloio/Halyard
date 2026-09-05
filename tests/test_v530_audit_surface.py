"""v5.30 — the MCP extra must resolve to an SDK Halyard can actually use.

`mcp>=1.2` let a fresh install resolve mcp 2.x, where FastMCP was renamed to
MCPServer. `mcp_server.py` imports `mcp.server.fastmcp`, so the server died on
import — and `cli_mcp` reported that ModuleNotFoundError as "the MCP SDK is
not installed", sending the user to reinstall an extra they already had. The
reinstall resolved 2.x again and reproduced the identical message.

No test covered `build_server()` against a wrong-major SDK, so CI stayed green
the whole time.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
from typer.testing import CliRunner

from halyard.cli import app

runner = CliRunner()

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _mcp_requirements() -> list[Requirement]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    out = []
    for group in ("mcp", "all"):
        for raw in extras[group]:
            req = Requirement(raw)
            if req.name == "mcp":
                out.append(req)
    return out


def test_mcp_extra_excludes_the_incompatible_major() -> None:
    """Both the `mcp` and `all` extras must exclude 2.x."""
    reqs = _mcp_requirements()
    assert len(reqs) == 2, "expected an mcp pin in both the `mcp` and `all` extras"
    for req in reqs:
        assert not req.specifier.contains(Version("2.0.0")), f"{req} admits mcp 2.x"
        assert not req.specifier.contains(Version("2.1.1")), f"{req} admits mcp 2.x"


def test_mcp_extra_clears_the_known_advisories() -> None:
    """PYSEC-2026-3481/3482 fixed in 1.27.2, PYSEC-2026-3483 in 1.28.1."""
    for req in _mcp_requirements():
        assert not req.specifier.contains(Version("1.27.1")), f"{req} admits a vulnerable mcp"
        assert req.specifier.contains(Version("1.29.1")), f"{req} excludes a known-good mcp"


def test_incompatible_sdk_is_not_reported_as_missing(monkeypatch) -> None:
    """The two failures are distinct and must not share a message."""
    import halyard.mcp_server as mcp_server

    def _boom() -> object:
        # exc.name is what the import system sets; a submodule miss means
        # the package is present but wrong-major.
        raise ModuleNotFoundError("No module named 'mcp.server.fastmcp'", name="mcp.server.fastmcp")

    monkeypatch.setattr(mcp_server, "build_server", _boom)

    result = runner.invoke(app, ["mcp"])
    assert result.exit_code == 1
    assert "not compatible" in result.stdout
    assert "not installed" not in result.stdout


def test_absent_sdk_still_reports_missing(monkeypatch) -> None:
    import halyard.mcp_server as mcp_server

    def _boom() -> object:
        raise ModuleNotFoundError("No module named 'mcp'", name="mcp")

    monkeypatch.setattr(mcp_server, "build_server", _boom)

    result = runner.invoke(app, ["mcp"])
    assert result.exit_code == 1
    assert "not installed" in result.stdout
    assert "not compatible" not in result.stdout


def test_ci_audits_the_optional_surface() -> None:
    """CI must install the extras it audits.

    Until v5.30 `lint-and-test` installed only `[dev]`, so `pip-audit`
    never saw mcp, starlette, cryptography, pyjwt, python-multipart or
    msgpack — the Hub's network-facing dependency surface — and reported
    the audit green while 27 advisories sat open there.
    """
    ci = (PYPROJECT.parent / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'pip install -e ".[dev,all]"' in ci, (
        "lint-and-test must install the optional extras so pip-audit covers them"
    )
