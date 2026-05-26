"""Shared test fixtures.

Isolation: no test may read or write the real ~/.halyard/projects.
`registry.register_project` also refuses temp-dir paths in production
(v2.48), but this redirect is belt-and-suspenders so a test can never
touch the user's real registry regardless of how it's invoked.
"""

from __future__ import annotations

import os
import sys

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
