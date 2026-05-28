"""Tests for halyard.log_config — LogConfig dataclass and load_log_config()."""

from __future__ import annotations

import warnings
from pathlib import Path

from halyard.log_config import LogConfig, load_log_config


def test_load_log_config_absent_file(tmp_path: Path) -> None:
    cfg = load_log_config(config_file=tmp_path / "nonexistent.toml")
    assert cfg == LogConfig()
    assert cfg.default_agent == "local"
    assert cfg.openai_base_url == "https://api.openai.com/v1"


def test_load_log_config_valid(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '[log]\ndefault_agent = "openai"\n'
        'openai_base_url = "http://localhost:11434/v1"\n'
        'openai_model = "llama3.3"\n'
        'claude_model = "claude-3-haiku-20240307"\n',
        encoding="utf-8",
    )
    cfg = load_log_config(config_file=config)
    assert cfg.default_agent == "openai"
    assert cfg.openai_base_url == "http://localhost:11434/v1"
    assert cfg.openai_model == "llama3.3"
    assert cfg.claude_model == "claude-3-haiku-20240307"


def test_load_log_config_unknown_agent_warns(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[log]\ndefault_agent = "xyz"\n', encoding="utf-8")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cfg = load_log_config(config_file=config)
    assert cfg.default_agent == "local"
    assert any("unknown log.default_agent 'xyz'" in str(warning.message) for warning in w)


def test_load_log_config_partial_section(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[log]\ndefault_agent = "claude"\n', encoding="utf-8")
    cfg = load_log_config(config_file=config)
    assert cfg.default_agent == "claude"
    # unset fields use defaults
    assert cfg.openai_base_url == "https://api.openai.com/v1"
    assert cfg.openai_model == "gpt-4o"


def test_load_log_config_empty_toml(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("", encoding="utf-8")
    cfg = load_log_config(config_file=config)
    assert cfg == LogConfig()
