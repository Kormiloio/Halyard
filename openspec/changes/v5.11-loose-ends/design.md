# Design — v5.11 Loose ends

## 1. Committable alias map

Two sources, merged in `load_project_aliases(project_dir: Path | None = None)`:

- **Committed:** `<project_dir>/project-aliases.toml` — shared, version-controlled.
- **Local:** `~/.halyard/project-aliases.toml` — per-machine override (kept for
  backward compatibility).

Merge precedence: `{**committed, **home}` — the home file overrides the committed
baseline for the same source slug, so a machine can locally re-point an alias
without editing the shared file. Both files use the same `[aliases]` table shape.

`load_project_aliases` keeps its no-arg form working (home-only) so existing
callers don't break; callers that have a project dir pass it:
- `ai_log.parse_sessions` (has `project_dir`) → passes it.
- `budget.budget_status`, `invoicing` account canonicalization → pass it.
- `hub_server` live slug → passes `self.project_dir` when set.

Cache: keyed on `(home_mtime, project_path, project_mtime)`. A missing file
contributes a sentinel mtime so its later creation invalidates the cache. The
cache is still a single module-global tuple (CLI/process-scoped reads).

`set_project_alias(source, canonical, project_dir: Path | None = None)` writes to
`<project_dir>/project-aliases.toml` when `project_dir` is given (so the alias is
committed), else the home file. `halyard projects alias` resolves the project dir
via `find_project_dir()` and passes it for both list and write; `--list` shows
the merged view.

Migration: the two existing home aliases are copied into the repo file as part of
this change so the canonical merges survive in version control.

## 2. `log_diagnostic` newline hygiene

`msg`, `tool`, and `project` are flattened (`"\n"`/`"\r"` → `" "`) before
formatting, so one diagnostic event is always exactly one physical line. The
existing `try/except OSError: pass` swallow is unchanged.

## 3. Test isolation for diag/audit logs

`conftest._isolate_halyard_logs` (autouse) redirects
`ai_log._HALYARD_DIAG_LOG` and `ai_log._HALYARD_AUDIT_LOG` to
`tmp_path_factory` paths, mirroring `_isolate_auto_timer`. Production code reads
these module globals at call time, so all in-process test code is covered. No
test asserts on the real log paths.

## 4. Windows CI

A second job in `ci.yml`:

```yaml
  test-windows:
    runs-on: windows-latest
    continue-on-error: true   # soft-launch until proven green
    strategy:
      matrix:
        python-version: ["3.12"]
    steps: checkout → setup-python → pip install -e .[dev] → pytest -q
```

Lint/format/mypy/pip-audit stay ubuntu-only (platform-independent). The Windows
job runs only the suite, which exercises the read-lock (`_acquire_read_lock` /
`_release_read_lock`, the v5.9 crash site) and all file-path handling on real
Windows. `continue-on-error` keeps it from blocking merges until the first green
run confirms the suite passes there.

## Tests

`tests/test_v511_loose_ends.py`:
- alias merge: committed-only, home-only, both (home overrides), cache refresh
  when the committed file appears/changes.
- `set_project_alias(project_dir=...)` writes the committed file.
- `log_diagnostic` collapses an embedded newline to one line.
- (Isolation fixture is exercised implicitly by the whole suite no longer
  touching the real logs; an explicit assertion seeds a real log and confirms it
  is untouched.)
The read-release Windows regression is already covered by
`test_v59_review_remediation.py::test_read_locked_file_uses_read_release`.
