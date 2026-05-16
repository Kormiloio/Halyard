"""Shared test fixtures.

Isolation: no test may read or write the real ~/.halyard/projects.
`registry.register_project` also refuses temp-dir paths in production
(v2.48), but this redirect is belt-and-suspenders so a test can never
touch the user's real registry regardless of how it's invoked.
"""

from __future__ import annotations

import pytest

from halyard import registry


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    reg = tmp_path_factory.mktemp("halyard-registry") / "projects"
    monkeypatch.setattr(registry, "REGISTRY_PATH", reg)
    return reg
