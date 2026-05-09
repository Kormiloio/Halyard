"""Gap 10: _validate_base_url localhost variant coverage.

Extends the base_url validation tests from v2.20 (test_log_agent_openai.py)
with explicit named tests for each localhost form and a private-IP rejection
case, matching the spec requirement for all six scenarios.
"""

from __future__ import annotations

import pytest

from halyard.log_agent import LogAgentError, _validate_base_url

# ---------------------------------------------------------------------------
# Accepted — loopback addresses (various forms)
# ---------------------------------------------------------------------------


def test_validate_127_0_0_1_accepted() -> None:
    """Plain IPv4 loopback without port is accepted."""
    url = "http://127.0.0.1/v1"
    assert _validate_base_url(url) == url


def test_validate_localhost_accepted() -> None:
    """Hostname 'localhost' without port is accepted."""
    url = "http://localhost/v1"
    assert _validate_base_url(url) == url


def test_validate_ipv6_loopback_accepted() -> None:
    """IPv6 loopback [::1] (bracket-enclosed per RFC 2732) is accepted."""
    url = "http://[::1]/v1"
    assert _validate_base_url(url) == url


def test_validate_127_0_0_1_with_port_accepted() -> None:
    """IPv4 loopback with an explicit port is accepted (common for Ollama / LM Studio)."""
    url = "http://127.0.0.1:11434/v1"
    assert _validate_base_url(url) == url


def test_validate_localhost_with_port_accepted() -> None:
    """'localhost' with an explicit port is accepted."""
    url = "http://localhost:8080/v1"
    assert _validate_base_url(url) == url


# ---------------------------------------------------------------------------
# Rejected — private / routable IP over plain HTTP
# ---------------------------------------------------------------------------


def test_validate_private_ip_rejected() -> None:
    """A private RFC-1918 address over plain HTTP is rejected.

    192.168.x.x is a routable LAN address.  Allowing it over plain HTTP
    would expose session metadata to any process on the same subnet.
    Only loopback (127.0.0.1, localhost, ::1) is accepted for HTTP.
    """
    with pytest.raises(LogAgentError, match="must be HTTPS or a localhost HTTP URL"):
        _validate_base_url("http://192.168.1.1/v1")
