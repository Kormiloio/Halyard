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

**Hash storage:** per hub/org under `~/.halyard/org-hashes/` — single line,
hex SHA-256 digest.

The storage key must include either:

- a stable hash of the resolved hub path; or
- the `org.id` after parsing, with a fallback path hash before parsing.

Do not use one global `~/.halyard/org-hash.txt`. Users can work with multiple
Halyard hubs/orgs on the same machine, and a single global baseline creates
false-positive warnings and overwrites the previous org's trusted baseline.

**Load sequence:**

1. Read `org.toml` bytes.
2. Compute `hashlib.sha256(content).hexdigest()`.
3. Resolve the hub/org-specific hash path.
4. Read that hash file if present.
5. Compare. If different (or file absent for the first time after this release),
   emit warning to stderr, then write new hash.
6. Parse and return the org config.

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
5. If hashes differ (and a stored hash exists): emit warning to stderr and
   abort persistence unless the caller has passed an explicit accept/force
   flag.
6. If no stored hash exists: treat this as initial trust establishment and
   persist the table/hash after normal validation succeeds.
7. If hashes match: accept silently. No extra hash write needed.

Review note: a warning-only implementation is not sufficient if it still
overwrites `~/.halyard/pricing.toml` and `pricing-hash.txt`. That behavior
destroys the last-known-good baseline while telling the user to review.
The CLI should expose an explicit acceptance path, for example
`halyard update-pricing --accept-changed-table`, or prompt interactively when
stdin is a TTY and fail closed in non-interactive runs.

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

Additional review constraints:

- Active-file concurrency tests must collect exceptions from every writer
  thread and assert the collection is empty after join. Pytest warnings are
  not enough because the test can otherwise pass while a writer crashed.
- The active-file test writer must use a unique temp path per write, matching
  the production helper. Sharing one `active.tmp` between writers is itself a
  race and proves the wrong behavior.
- The test module must pass `ruff check` and `ruff format --check` before
  the changeset can be marked complete.

---

## No new dependencies

- `xml.sax.saxutils` — standard library
- `hashlib` — standard library

No additions to `pyproject.toml`.
