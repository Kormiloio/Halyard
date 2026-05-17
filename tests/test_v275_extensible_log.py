"""v2.75 — extensible log contract (unknown-token preservation).

Pins the hard invariants from the changeset design: unknown `s `-line
tokens round-trip losslessly, the empty case is byte-stable, known
fields are never shadowed, the content-addressed identity is
unaffected, and a value cannot inject a delimiter.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from halyard.ai_log import AiSession, session_hash
from halyard.db import _session_id


def _s(**kw: object) -> AiSession:
    start = datetime(2026, 5, 17, 9, 0, 0)
    base: dict = {
        "start": start,
        "end": start + timedelta(minutes=5),
        "tool": "claude-code",
        "model": "claude-opus-4-7",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.01,
        "project": "kormilo:halyard",
    }
    base.update(kw)
    return AiSession(**base)


def test_round_trip_lossless_adversarial_values() -> None:
    extra = {
        "cost_center": "fixed income / rates",
        "roi_ref": "JIRA-123=ABC",
        "weird": "100% done, x=y",
        "uni": "café — naïve",
        "csv": "a,b,c",
    }
    line = _s(extra=dict(extra)).to_log_line()
    back = AiSession.from_log_line(line)
    assert back is not None
    assert back.extra == extra
    # equality ignores `extra` (compare=False) — both must still be ==
    assert back == _s()


def test_empty_extra_is_byte_stable() -> None:
    s = _s()
    assert s.extra == {}
    line = s.to_log_line()
    # no stray tokens appended; round-trips to no extra
    assert "=" in line  # sanity: it has normal kv tokens
    back = AiSession.from_log_line(line)
    assert back is not None and back.extra == {}
    # serialization is idempotent and hash-stable for the empty case,
    # so existing on-disk amendments (keyed by session_hash) still join
    assert back.to_log_line() == line
    assert session_hash(line) == session_hash(back.to_log_line())


def test_known_fields_are_never_shadowed() -> None:
    # project= is a known field; an unknown token sits beside it.
    line = (
        _s(project="acme:web")
        .to_log_line()
        .replace(" project=acme:web", " project=acme:web zzz_custom=hello")
    )
    back = AiSession.from_log_line(line)
    assert back is not None
    assert back.project == "acme:web"  # known field wins
    assert back.extra == {"zzz_custom": "hello"}
    assert "project" not in back.extra


def test_identity_unaffected_by_extra() -> None:
    """The content-addressed cache id depends only on immutable
    identity fields — an extra-only difference must not repartition
    the cache or break amendment joins."""
    a = _s()
    b = _s(extra={"cost_center": "alpha"})

    def sid(x: AiSession) -> str:
        return _session_id(
            x.start.isoformat(),
            x.end.isoformat(),
            x.tool,
            x.model,
            x.input_tokens,
            x.output_tokens,
        )

    assert sid(a) == sid(b)  # same identity
    assert a == b  # dataclass eq ignores extra (compare=False)


def test_forward_compat_token_preserved_not_interpreted() -> None:
    line = _s().to_log_line() + " cost_center=fraud-detection"
    back = AiSession.from_log_line(line)
    assert back is not None
    assert back.extra["cost_center"] == "fraud-detection"
    # OSS must NOT interpret it — no attribute is created/changed
    assert not hasattr(back, "cost_center")
    assert back.project == "kormilo:halyard"  # untouched
    # and it survives a re-serialize
    assert "cost_center=fraud-detection" in back.to_log_line()


def test_value_cannot_inject_a_delimiter() -> None:
    s = _s(extra={"x": "a=b c d"})
    line = s.to_log_line()
    # the dangerous chars are percent-encoded → exactly one x= token
    assert line.count(" x=") == 1
    assert " c " not in line and "a=b" not in line
    back = AiSession.from_log_line(line)
    assert back is not None
    assert back.extra == {"x": "a=b c d"}  # decodes back intact


def test_malformed_extra_key_is_dropped_not_stored() -> None:
    # A token whose key isn't well-formed must not become a junk sink.
    base = _s().to_log_line()
    back = AiSession.from_log_line(base + " 9bad%=oops")
    assert back is not None
    assert all(k != "9bad%" for k in back.extra)


def test_amendment_line_parsing_unchanged() -> None:
    # `extra` is an `s `-line concern only; `a ` amendment parsing is
    # untouched and still round-trips a session through its hash.
    s = _s(project="acme:web")
    sline = s.to_log_line()
    h = session_hash(sline)
    from halyard.ai_log import parse_amendment

    amend = parse_amendment(f"a {h} project=beta:api")
    assert amend is not None
    assert amend.session_hash == h
    assert amend.kvs.get("project") == "beta:api"
