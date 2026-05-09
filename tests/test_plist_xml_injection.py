"""Tests for D-4: plist XML injection — service._plist() must produce valid XML.

Gap 6: project_dir with <, >, & characters produces valid XML in the generated plist.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from halyard.service import _plist


def _parse_xml(text: str) -> ET.Element:
    """Parse plist XML, raising ET.ParseError on malformed input."""
    # Strip the DOCTYPE line — ElementTree doesn't handle external DTDs.
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("<!DOCTYPE")]
    return ET.fromstring("\n".join(lines))


# ---------------------------------------------------------------------------
# D-4 / Gap 6: plist XML injection
# ---------------------------------------------------------------------------


def test_plist_xml_safe_project_dir() -> None:
    """A normal path with no XML-special chars produces valid, parseable XML."""
    result = _plist("/usr/local/bin/halyard", Path("/home/user/myproject"), 7432)
    root = _parse_xml(result)  # raises ET.ParseError if malformed
    assert root.tag == "plist"


def test_plist_xml_injection_lt_gt() -> None:
    """project_dir containing < and > produces valid XML (not broken by injection)."""
    evil_dir = Path("/home/user/<project>/dir")
    result = _plist("/usr/local/bin/halyard", evil_dir, 7432)
    root = _parse_xml(result)
    assert root.tag == "plist"
    # Confirm the escaped text appears in the parsed tree
    strings = [el.text for el in root.iter("string")]
    assert any("<project>" in (s or "") for s in strings)


def test_plist_xml_injection_ampersand() -> None:
    """project_dir containing & produces valid XML."""
    evil_dir = Path("/home/user/acme&corp/proj")
    result = _plist("/usr/local/bin/halyard", evil_dir, 7432)
    root = _parse_xml(result)
    assert root.tag == "plist"
    strings = [el.text for el in root.iter("string")]
    assert any("acme&corp" in (s or "") for s in strings)


def test_plist_xml_injection_combined() -> None:
    """project_dir with all three XML-special chars (<, >, &) parses cleanly."""
    evil_dir = Path("/tmp/<bad>&<worse>/proj")
    result = _plist("/usr/local/bin/halyard", evil_dir, 7432)
    root = _parse_xml(result)
    assert root.tag == "plist"
    strings = [el.text for el in root.iter("string")]
    assert any("<bad>&<worse>" in (s or "") for s in strings)


def test_plist_xml_no_special_chars_unchanged_semantics() -> None:
    """When project_dir has no XML-special chars, the generated text is functionally
    identical to what a plain f-string would have produced."""
    normal_dir = Path("/home/user/halyard-project")
    result = _plist("/usr/local/bin/halyard", normal_dir, 7432)
    assert str(normal_dir) in result
    root = _parse_xml(result)
    assert root.tag == "plist"


def test_plist_xml_exe_with_special_chars() -> None:
    """halyard_exe path containing & produces valid XML."""
    result = _plist("/usr/local/bin/hal<yard", Path("/home/user/proj"), 7432)
    root = _parse_xml(result)
    assert root.tag == "plist"
