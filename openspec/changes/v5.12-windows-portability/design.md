# Design — v5.12 Windows portability

## 1. UTF-8 everywhere

Three mechanical edits across `src/halyard/` and `tests/`:

| Pattern | Replacement |
|---|---|
| `.read_text()` | `.read_text(encoding="utf-8")` |
| `.write_text(X)` | `.write_text(X, encoding="utf-8")` |
| `open(p, "<text-mode>")` | `open(p, "<text-mode>", encoding="utf-8")` |

A small Python script does the rewrite with AST-style tokenization rather than
naive regex to avoid mangling multi-line calls. Lines that already contain
`encoding=` are skipped (idempotent). The script is run, then `ruff format` is
applied. No-op on Linux (same bytes); fixes Windows.

Binary modes (`"rb"`, `"wb"`) are untouched. The handful of intentionally
locale-controlled paths (subprocess, OS-level logging) — none in Halyard — would
be skipped manually.

## 2. `jsonio` POSIX paths

`halyard.jsonio` (the JSON encoder) detects `pathlib.PurePath` and emits
`str(p.as_posix())` instead of `str(p)`. Round-trip is a string, not a Path, so
no decode side. Test `test_jsonio_encodes_paths_and_dates` becomes
cross-platform: both sides expect `'/x/y'`.

## 3. Copilot importer Windows fix

Deferred to the second iteration: once the encoding wave is gone, the remaining
Copilot failures will be readable in the Windows CI log and the fix becomes
targeted (probably a `Path` join / glob using a hard-coded `/` or a Windows-only
Copilot-data location).

## 4. Ruff `PLW1514`

Add `"PLW1514"` to the `tool.ruff.lint.extend-select` list in `pyproject.toml`.
That rule flags `open(...)` without `encoding=` regardless of platform. Once
v5.12 lands, any new locale-dependent open fails CI everywhere — the bug class
is closed.

## Tests

Existing tests are the verification: the Windows CI job goes from "60+
failures" to "green" across iterations. No new tests needed for the encoding
fix (the existing suite, when run on Windows, IS the regression test). One new
test for the `jsonio` POSIX-path contract (it already exists as
`test_jsonio_encodes_paths_and_dates`, currently Windows-only-failing; it now
passes on every platform).
