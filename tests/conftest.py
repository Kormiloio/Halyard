"""Shared test fixtures.

Isolation: no test may read or write the real ~/.halyard/projects.
`registry.register_project` also refuses temp-dir paths in production
(v2.48), but this redirect is belt-and-suspenders so a test can never
touch the user's real registry regardless of how it's invoked.
"""

from __future__ import annotations

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
