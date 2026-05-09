# v2.22 Design — Security Architecture

## D-4: Plist XML injection

**Library:** `xml.sax.saxutils.escape()` from the Python standard library.
No new dependencies.

`service.py` currently interpolates `project_dir` and other values directly
into the plist XML string. The fix wraps each interpolated value:

```python
from xml.sax.saxutils import escape

plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
...
<string>{escape(str(project_dir))}</string>
...
"""
```

`escape()` handles `&`, `<`, and `>`. Attribute values (if any) additionally
need `quoteattr()`, but the launchd plist format uses element content only,
so `escape()` is sufficient.

---

## D-3: org.toml integrity

**Hash storage:** `~/.halyard/org-hash.txt` — single line, hex SHA-256 digest.

**Load sequence:**

1. Read `org.toml` bytes.
2. Compute `hashlib.sha256(content).hexdigest()`.
3. Read `~/.halyard/org-hash.txt` if present.
4. Compare. If different (or file absent for the first time after this release),
   emit warning to stderr, then write new hash.
5. Parse and return the org config.

The warning does not block startup. It is informational.

No new dependencies. `hashlib` is standard library.

---

## D-5: Pricing table hash pinning

**Hash storage:** `~/.halyard/pricing-hash.txt` — single line, hex SHA-256
digest of the last accepted pricing table response body.

**Fetch sequence:**

1. Fetch pricing table HTTP response body (in memory).
2. If response is incomplete / truncated (Content-Length mismatch or connection
   error), abort: do not update local table or hash.
3. Compute `hashlib.sha256(body).hexdigest()`.
4. Read `~/.halyard/pricing-hash.txt` if present.
5. If hashes differ (or no stored hash yet): emit warning to stderr. Do not
   write new hash yet — new hash is written only when the caller explicitly
   accepts the table (TBD in a future acceptance policy flag; for now, the
   warning is issued but the table is accepted for the current session without
   persisting the hash).
6. If hashes match: accept silently. No hash write needed.

This is a first-step implementation. A future change will add an explicit
accept/reject prompt and a `--trust-pricing-hash` flag.

---

## Test coverage gaps — implementation notes

Each gap maps to a new test function. No production code changes are needed
for gaps 1, 2, 3, 5, 7, 9, 10 — these are tests of existing behavior that
was untested. Gaps 4, 6, 8 are tests of the new D-3, D-4, D-5 behavior.

| Gap | File | Notes |
|---|---|---|
| 1 | `tests/test_session_roundtrip.py` | Parametrize over all field combinations |
| 2 | `tests/test_active_file_concurrent.py` | threading.Thread × 2 |
| 3 | `tests/test_active_file_concurrent.py` | Write partial slug, read returns None |
| 4 | `tests/test_org_hash.py` | Monkeypatch hash file |
| 5 | `tests/test_collector_attr_method.py` | Already exists from v2.21; extend |
| 6 | `tests/test_plist_xml_injection.py` | Parse generated plist with xml.etree |
| 7 | `tests/test_gemini_prefix_collision.py` | Two sessions, same 8-char prefix |
| 8 | `tests/test_pricing_hash.py` | Monkeypatch HTTP response; truncate |
| 9 | `tests/test_read_sessions_limit.py` | Generate 10 000-line log; assert < 1s |
| 10 | `tests/test_base_url_validation.py` | Already exists from v2.20; extend |

---

## No new dependencies

- `xml.sax.saxutils` — standard library
- `hashlib` — standard library

No additions to `pyproject.toml`.
