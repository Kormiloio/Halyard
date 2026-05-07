"""Tests for halyard.git_context — git-based project inference."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.git_context import (
    _extract_repo_name,
    _normalize_remote,
    _remote_matches,
    infer_project,
    register_repo,
)

# ---------------------------------------------------------------------------
# _normalize_remote
# ---------------------------------------------------------------------------


def test_normalize_https() -> None:
    assert _normalize_remote("https://github.com/user/my-repo.git") == "github.com/user/my-repo"


def test_normalize_ssh() -> None:
    assert _normalize_remote("git@github.com:user/my-repo.git") == "github.com/user/my-repo"


def test_normalize_no_git_suffix() -> None:
    assert _normalize_remote("https://github.com/user/repo") == "github.com/user/repo"


def test_normalize_strips_trailing_slash() -> None:
    assert _normalize_remote("https://github.com/user/repo/") == "github.com/user/repo"


# ---------------------------------------------------------------------------
# _remote_matches
# ---------------------------------------------------------------------------


def test_remote_matches_exact() -> None:
    assert _remote_matches("https://github.com/acme/auth.git", "github.com/acme/auth")


def test_remote_matches_wildcard() -> None:
    assert _remote_matches("https://github.com/acme/frontend.git", "github.com/acme/*")


def test_remote_no_match() -> None:
    assert not _remote_matches("https://github.com/acme/auth.git", "github.com/other/auth")


def test_remote_wildcard_no_cross_segment() -> None:
    # * should not match across path segments
    assert not _remote_matches("https://github.com/acme/sub/repo.git", "github.com/acme/*")


# ---------------------------------------------------------------------------
# _extract_repo_name
# ---------------------------------------------------------------------------


def test_extract_repo_name_https() -> None:
    assert _extract_repo_name("https://github.com/user/my-app.git") == "my-app"


def test_extract_repo_name_ssh() -> None:
    assert _extract_repo_name("git@github.com:user/my-app.git") == "my-app"


# ---------------------------------------------------------------------------
# infer_project
# ---------------------------------------------------------------------------


def _mock_remote(url: str):  # type: ignore[no-untyped-def]
    return patch("halyard.git_context._git_remote_url", return_value=url)


def _mock_repos(mapping: dict) -> patch:  # type: ignore[type-arg]
    return patch("halyard.git_context._load_repos_config", return_value=mapping)


def test_infer_project_explicit_mapping(tmp_path: Path) -> None:
    with (
        _mock_remote("https://github.com/acme/auth.git"),
        _mock_repos({"github.com/acme/auth": "acme:auth"}),
    ):
        assert infer_project(tmp_path) == "acme:auth"


def test_infer_project_wildcard_mapping(tmp_path: Path) -> None:
    with (
        _mock_remote("https://github.com/acme/frontend.git"),
        _mock_repos({"github.com/acme/*": "acme:general"}),
    ):
        assert infer_project(tmp_path) == "acme:general"


def test_infer_project_auto_slug(tmp_path: Path) -> None:
    with (
        _mock_remote("https://github.com/user/cool-app.git"),
        _mock_repos({}),
    ):
        assert infer_project(tmp_path) == "git/cool-app"


def test_infer_project_no_remote(tmp_path: Path) -> None:
    with patch("halyard.git_context._git_remote_url", return_value=None):
        assert infer_project(tmp_path) is None


# ---------------------------------------------------------------------------
# register_repo
# ---------------------------------------------------------------------------


def test_register_repo_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "repos.toml"
    monkeypatch.setattr("halyard.git_context._REPOS_CONFIG", config)

    register_repo("github.com/acme/auth", "acme:auth")

    assert config.exists()
    text = config.read_text()
    assert '"github.com/acme/auth" = "acme:auth"' in text


def test_register_repo_updates_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "repos.toml"
    config.write_text('[repos]\n"github.com/acme/auth" = "acme:old"\n')
    monkeypatch.setattr("halyard.git_context._REPOS_CONFIG", config)

    register_repo("github.com/acme/auth", "acme:new")

    text = config.read_text()
    assert '"acme:new"' in text
    assert '"acme:old"' not in text
