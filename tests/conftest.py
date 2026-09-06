"""Shared test fixtures.

Isolation: no test may read or write the real ~/.halyard/projects.
`registry.register_project` also refuses temp-dir paths in production
(v2.48), but this redirect is belt-and-suspenders so a test can never
touch the user's real registry regardless of how it's invoked.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from halyard import registry

# A trace function is installed by coverage (sys.settrace), profilers,
# and debuggers. Line tracing inflates wall-clock by 20-50%+, so any
# *absolute* real-time assertion is meaningless under it.
TRACING_ACTIVE: bool = sys.gettrace() is not None


def _perf_ceiling(seconds: float, *, traced_multiplier: float = 5.0) -> float:
    """Return a wall-clock ceiling that is safe under coverage/tracing.

    Single source for every timing assertion in the suite — do NOT
    write a bare ``assert elapsed < <literal>``; take the
    ``perf_ceiling`` fixture and use
    ``assert elapsed < perf_ceiling(<budget>)`` instead. When a trace
    function is active the budget is widened ``traced_multiplier``x.
    The point of these tests is catching an *algorithmic* regression
    (e.g. O(n) -> O(n^2), which is orders of magnitude), so a 5x
    headroom still fails loudly on a real regression while never
    flaking on instrumentation overhead.
    """
    return seconds * (traced_multiplier if TRACING_ACTIVE else 1.0)


@pytest.fixture
def perf_ceiling():  # type: ignore[no-untyped-def]
    """Tracing-aware wall-clock ceiling. See ``_perf_ceiling``."""
    return _perf_ceiling


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    reg = tmp_path_factory.mktemp("halyard-registry") / "projects"
    monkeypatch.setattr(registry, "REGISTRY_PATH", reg)
    return reg


@pytest.fixture(autouse=True)
def _isolate_halyard_logs(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
):
    """No test may write the real ~/.halyard/{diagnostic,halyard}.log.

    Many code paths call ``log_diagnostic`` / the audit log, which resolve to
    module-level ``Path.home()`` constants — so without isolation the suite
    scribbles "in tests" lines into the developer's real logs.
    """
    logdir = tmp_path_factory.mktemp("halyard-logs")
    monkeypatch.setattr("halyard.ai_log._HALYARD_DIAG_LOG", logdir / "diagnostic.log")
    monkeypatch.setattr("halyard.ai_log._HALYARD_AUDIT_LOG", logdir / "halyard.log")
    return logdir


@pytest.fixture(autouse=True)
def _isolate_auto_timer(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """No test may read, write, or delete the real ~/.halyard/auto-timer state.

    The presence-window state file holds the live human-time clock-in. A test
    that touches the real one (e.g. an autouse ``unlink`` for cleanup) deletes
    an active clock-in mid-session, orphaning it — every ``pytest`` run during
    real work then drops a billable open. Redirect it to a throwaway path.
    """
    state = tmp_path_factory.mktemp("halyard-auto-timer") / "auto-timer"
    monkeypatch.setattr("halyard.auto_timer._AUTO_TIMER_FILE", state)
    return state


@pytest.fixture(scope="session", autouse=True)
def _isolate_db(tmp_path_factory: pytest.TempPathFactory):
    """No test may write the real ~/.halyard/cache.db.

    v5.37. ``db._DB_PATH`` is a module-level constant bound to the real
    ``Path.home()`` at import time, and ``get_db`` uses it directly, so a
    test patching ``Path.home`` never reaches it. Only three tests patched
    ``_DB_PATH`` explicitly; every other test touching the cache wrote into
    the developer's production database — 62 fixture rows carrying $0.61 of
    fabricated cost were found in a real one, growing with each suite run.

    **Session-scoped deliberately.** A function-scoped patch is restored at
    each test's teardown, and `HubServer` runs in a background thread that
    can outlive it — so a write landing in that window hits the *real* path
    after the patch is gone. That race is order-dependent, which is why a
    full run could look clean (474 -> 474 rows) and then leak
    ``tool-1``/``tool-2`` on the next run under a different
    ``pytest-randomly`` seed. Holding the override for the whole session
    removes the window rather than narrowing it.

    Same class as the v5.23 follow-up that added ``_no_real_hub_pointer``
    below, after v5.21 test rows were found in the real hub ledger.
    """
    from _pytest.monkeypatch import MonkeyPatch

    from halyard import db

    mp = MonkeyPatch()
    mp.setattr(db, "_DB_PATH", tmp_path_factory.mktemp("halyard-db") / "cache.db")
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolate_path_map(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """No test may read or write the real ~/.halyard/paths.toml.

    v5.39 added another module-level ``Path.home()`` constant
    (``git_context._PATHS_CONFIG``), and ``resolve_paths`` is now on the
    universal read path — so without this, every test that parses a ledger
    consults the developer's own path map, and a test that writes one leaks
    into it. Exactly the class v5.37's guard was built to make loud.
    """
    from halyard import git_context

    monkeypatch.setattr(
        git_context, "_PATHS_CONFIG", tmp_path_factory.mktemp("halyard-paths") / "paths.toml"
    )


@pytest.fixture(scope="session", autouse=True)
def _guard_real_cache_db():
    """Fail the run if a test introduced a session into the real cache.db.

    ``_isolate_db`` above fixes the known leak; this catches the next one.
    Roughly twenty module-level ``Path.home()`` constants across
    ``src/halyard/`` share that shape, and enumerating them one incident at
    a time is how the cache.db leak survived v5.28.

    It compares the *set of tool names*, not a row count. A row count fails
    on legitimate activity: a live Claude Code hook captures and syncs the
    developer's own work while the suite runs, so a counting guard fires on
    real usage and gets disabled — which is the failure mode of a guard
    nobody trusts. Real activity adds rows under tools already present; a
    test introduces a name that was not there (``tool-1``, ``test-tool``,
    ``shell-tool``).

    Read-only connection so the guard cannot become a writer itself, and any
    ``sqlite3.Error`` disables the check rather than failing a run for an
    unrelated reason.
    """
    import sqlite3
    from pathlib import Path

    real = Path.home() / ".halyard" / "cache.db"

    def _tools() -> set[str] | None:
        if not real.exists():
            return None
        try:
            with sqlite3.connect(f"file:{real}?mode=ro", uri=True) as c:
                return {r[0] for r in c.execute("select distinct tool from sessions")}
        except sqlite3.Error:
            return None

    before = _tools()
    yield
    after = _tools()
    if before is None or after is None:
        return
    introduced = after - before
    if introduced:
        raise AssertionError(
            f"a test wrote the real {real}, introducing tool(s): {sorted(introduced)}. "
            "Some module-level path still resolves to the real home — add it to an "
            "autouse isolation fixture in conftest (see _isolate_db)."
        )


@pytest.fixture(autouse=True)
def _no_real_hub_pointer(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make ``find_hub`` hermetic: never read the dev machine's real
    ``~/.halyard/hub`` pointer.

    v5.23 follow-up — the duplicate canary's first live catch was two v5.21
    test rows direct-written into the developer's real hub ledger:
    ``_no_real_hub`` below blocks the Hub *daemon* HTTP path, but
    ``find_hub()`` still resolved the real hub *directory*, and
    ``append_session`` fell back to a direct file write into it. Point the
    pointer at an empty temp path; a test that needs a hub provisions its
    own via ``set_hub`` (which goes through the same override).
    """
    from halyard import hub

    monkeypatch.setattr(hub, "_HUB_POINTER", tmp_path_factory.mktemp("halyard-hub") / "hub-pointer")


@pytest.fixture(autouse=True)
def _no_real_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the suite hermetic against a Hub running on the dev machine.

    Every ``hub_client`` call funnels through ``_request``. A real Bridge on the
    default port (:4318) would intercept session appends, timer/presence writes,
    and collision checks, silently breaking tests that then read local state
    (observed: append_session is Hub-first, so the local log stays empty).

    Clear any inherited Hub env, then make ``_request`` report "unreachable"
    unless a test has provisioned its own in-process Hub — signalled by setting
    ``HALYARD_HUB_PORT`` (as the v4.2 state tests do). Those pass straight
    through to their own server; every other test falls back to local writes,
    exactly as in CI where no Hub runs. Leaves the configured URL/port intact
    so URL-rendering assertions (realtime dashboard) are unaffected.
    """
    from halyard import hub_client

    for var in ("HALYARD_HUB_PORT", "HALYARD_HUB_HOST", "HALYARD_DISABLE_HUB"):
        monkeypatch.delenv(var, raising=False)

    real_request = hub_client._request

    def _guarded_request(*args, **kwargs):  # type: ignore[no-untyped-def]
        if "HALYARD_HUB_PORT" not in os.environ:
            return None  # no test-provisioned Hub → treat as unreachable
        return real_request(*args, **kwargs)

    monkeypatch.setattr(hub_client, "_request", _guarded_request)


@pytest.fixture(autouse=True)
def _no_real_ledger_writes(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No test may append a session to a ledger outside the temp tree.

    Patching ``Path.home()`` is *not* sufficient. A collector resolves its
    target ledger from ``Path.cwd()`` when no workspace is known, and
    ``find_project_dir`` walks *up* the tree — so a test that forgets to
    chdir will climb out of the repo, find a real Halyard project on the
    developer's machine, and append synthetic rows to a real
    ``ai-sessions.log``. v5.24's Antigravity importer tests did exactly
    that: 80 fabricated rows in a live ledger before anyone noticed.

    ``append_session`` is imported by-name into every collector module, so
    rebinding it on ``halyard.ai_log`` alone would miss them. Rebind every
    already-imported reference.
    """
    import halyard.ai_log as ai_log

    real_append = ai_log.append_session
    basetemp = tmp_path_factory.getbasetemp().resolve()
    systemp = Path(tempfile.gettempdir()).resolve()

    def guarded(project_dir: Path, *args: object, **kwargs: object) -> object:
        resolved = Path(project_dir).resolve()
        if not (resolved.is_relative_to(basetemp) or resolved.is_relative_to(systemp)):
            raise AssertionError(
                "test tried to append a session to a ledger outside the temp "
                f"tree: {resolved}. Add monkeypatch.chdir(tmp_path) to the "
                "test's isolation fixture — patching Path.home() is not enough."
            )
        return real_append(project_dir, *args, **kwargs)

    monkeypatch.setattr(ai_log, "append_session", guarded)
    for name, module in list(sys.modules.items()):
        if not name.startswith("halyard.") or module is None:
            continue
        if getattr(module, "append_session", None) is real_append:
            monkeypatch.setattr(module, "append_session", guarded)
