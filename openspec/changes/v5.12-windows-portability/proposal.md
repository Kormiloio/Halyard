# v5.12 — Windows portability (encoding + path)

## Why

The v5.11 `test-windows` CI job ran for the first time and surfaced wide-spread
real Windows bugs (v5.9's read-lock fix itself is fine — none of the failures
touch the locking path). Three root causes:

1. **Locale-default text encoding.** `Path.write_text(...)` / `read_text()` /
   `open(path, "w")` without `encoding=` use `locale.getpreferredencoding()`,
   which is **cp1252 on Windows**. The `ai-sessions.log` and project-registry
   headers contain an em-dash (`—`); on Windows they get written as a single
   `\x97` byte. Every subsequent UTF-8 read raises
   `UnicodeDecodeError: byte 0x97`, cascading across most of the suite (60+
   tests). The voyages emoji (🐋) hits the inverse encode-side failure
   (`charmap can't encode \U0001f40b`). Audit: 30 src `write_text`, 56 src
   `read_text`, ~447 test `write_text` calls lack explicit encoding.

2. **Path serialization in `jsonio`.** `Path("/x/y")` serializes to `'\\x\\y'`
   on Windows (str-of-WindowsPath), breaking a cross-platform contract test
   that expects `'/x/y'`. Need POSIX-form normalization on the way out.

3. **Copilot importer path failure** (`test_v37_copilot_importer`). The
   importer finds 0 sessions on Windows where it should find one. Likely a
   path/glob assumption (POSIX separator, case sensitivity, or a Windows-only
   Copilot data dir convention).

## What changes

1. **Explicit UTF-8 for every text file Halyard touches.** Mechanical pass over
   `src/` and `tests/`: every `Path.read_text()` / `Path.write_text(...)` /
   `open(...)` for text mode gets `encoding="utf-8"`. The append-only log and
   every plain-text artifact are UTF-8 forever, on every platform — matching
   the project's "plain text forever" non-negotiable.

2. **`jsonio` emits POSIX paths.** The custom JSON encoder normalizes `Path`
   values to their POSIX form (`Path.as_posix()`) so a serialized path is the
   same string on every OS.

3. **Copilot importer Windows fix.** Investigated in the second iteration once
   the encoding wave clears the noise from the Windows CI log.

4. **Ruff guard against regression.** Enable `PLW1514` (`open` without explicit
   `encoding`) so a new locale-dependent text open fails CI on every platform,
   not just Windows.

## Impact

- Affected: every module that touches a text file. No behavior change on Linux
  (UTF-8 was already the implicit default there); strictly a Windows
  correctness fix. No format change.
- The non-blocking `test-windows` CI job (added in v5.11) becomes the
  verification surface — it stays `continue-on-error` until proven green, then
  flips to required.
