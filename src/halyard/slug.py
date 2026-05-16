"""Shared project-slug validation.

A timer/project slug is written verbatim into ``time.timeclock``, the
global ``~/.halyard/active`` state file, and ``project=`` amendment
tokens. Whitespace, control characters, ``=`` or ``:`` would split or
forge those space- and key=value-delimited records. One canonical
validator keeps every entry point consistent.
"""

from __future__ import annotations

import re

# client/project — each segment starts alphanumeric, then alnum plus
# the safe punctuation set; exactly one '/' separator; no leading or
# trailing separator, no whitespace/control/'='/':' anywhere.
# \A...\Z (not ^...$): in Python '$' also matches just before a
# trailing newline, which would let "acme/web\n" slip through.
_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"
SLUG_RE = re.compile(rf"\A{_SEGMENT}/{_SEGMENT}\Z")


def is_valid_timer_slug(slug: str) -> bool:
    """True iff *slug* is a safe ``client/project`` value."""
    return bool(SLUG_RE.match(slug))
