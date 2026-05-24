"""Windows Service provider."""

from __future__ import annotations

from pathlib import Path

from halyard.service_manager import ServiceProvider


class WindowsProvider(ServiceProvider):
    """Stub provider for Windows Services. Implementation deferred."""

    def install(self, project_dir: Path, port: int) -> str:
        raise NotImplementedError("Windows service installation is not yet implemented.")

    def uninstall(self) -> bool:
        raise NotImplementedError("Windows service management is not yet implemented.")

    def status(self) -> tuple[bool, str]:
        return False, "Windows service management not yet implemented."

    def get_port(self) -> int:
        from halyard.dashboard import DASHBOARD_PORT

        return DASHBOARD_PORT
