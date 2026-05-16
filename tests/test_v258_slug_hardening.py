"""v2.58 — shared slug validation + amendment-token sanitization (P2)."""

from __future__ import annotations

import pytest

from halyard.ai_log import _amendment_line
from halyard.slug import is_valid_timer_slug


@pytest.mark.parametrize(
    "good",
    ["acme/web", "acme/auth-migration", "a/b", "Client.1/proj_2", "x9/y9"],
)
def test_valid_slugs(good: str) -> None:
    assert is_valid_timer_slug(good) is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "noslash",
        "/leading",
        "trailing/",
        "a/b/c",  # two separators
        "acme/ web",  # whitespace
        "acme/web\n",  # newline
        "acme/we=b",  # '=' would forge a key
        "acme:web",  # ':' is the stored form, not input
        "a b/c",
        "../etc/passwd",  # leading '.' not allowed as segment start
    ],
)
def test_invalid_slugs(bad: str) -> None:
    assert is_valid_timer_slug(bad) is False


def test_amendment_line_neutralises_injection() -> None:
    # Even if a hostile value reached here, the space/'=' must not
    # forge extra tokens in the space-delimited amendment record.
    line = _amendment_line(
        "s 2026-05-15T10:00:00 2026-05-15T10:05:00 cc m 1 1 0.0",
        project="evil prj attr_method=manual extra=1",
        attr_method="backfill",
    )
    parts = line.split()
    assert parts[0] == "a"
    # Exactly: a <hash> project=<safe> attr_method=<safe>
    assert len(parts) == 4
    assert parts[2].startswith("project=")
    assert parts[3] == "attr_method=backfill"
    assert "attr_method=manual" not in line
    assert " " not in parts[2].split("=", 1)[1]
