"""Base ServiceProvider interface for Halyard background services."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path


class ServiceProvider(ABC):
    """Abstract base class for platform-specific service management."""

    def __init__(self, label: str):
        self.label = label

    @abstractmethod
    def install(self, project_dir: Path, port: int) -> str:
        """Install and start the service. Returns the dashboard URL."""
        pass

    @abstractmethod
    def uninstall(self) -> bool:
        """Stop and remove the service. Returns True if a service was removed."""
        pass

    @abstractmethod
    def status(self) -> tuple[bool, str]:
        """Return (is_running, message)."""
        pass

    @abstractmethod
    def get_port(self) -> int:
        """Return the port currently configured in the service definition."""
        pass


def get_provider(label: str) -> ServiceProvider:
    """Return the appropriate ServiceProvider for the current platform."""
    if sys.platform == "darwin":
        from halyard.service_providers.launchd import LaunchdProvider

        return LaunchdProvider(label)
    elif sys.platform == "linux":
        from halyard.service_providers.systemd import SystemdProvider

        return SystemdProvider(label)
    elif sys.platform == "win32":
        from halyard.service_providers.windows import WindowsProvider

        return WindowsProvider(label)
    else:
        raise NotImplementedError(f"Service management not supported on {sys.platform}")
