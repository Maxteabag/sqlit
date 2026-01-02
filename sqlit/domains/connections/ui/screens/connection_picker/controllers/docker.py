"""Docker discovery controller for the connection picker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.domains.connections.discovery.docker_detector import DetectedContainer, DockerStatus

if TYPE_CHECKING:
    from sqlit.domains.connections.ui.screens.connection_picker.screen import ConnectionPickerScreen
    from sqlit.domains.connections.ui.screens.connection_picker.state import DockerState


class DockerController:
    """Handle Docker discovery lifecycle and status messaging."""

    def __init__(self, screen: ConnectionPickerScreen, state: DockerState) -> None:
        self._screen = screen
        self._state = state

    def load_async(self) -> None:
        self._state.loading = True
        self._screen._rebuild_list()
        self._screen.run_worker(self._detect_worker, thread=True)

    def _detect_worker(self) -> None:
        status, containers = self._screen._app().services.docker_detector()
        self._screen.app.call_from_thread(self.on_containers_loaded, status, containers)

    def on_containers_loaded(
        self,
        status: DockerStatus,
        containers: list[DetectedContainer],
    ) -> None:
        self._state.loading = False
        self._state.containers = containers
        self._state.status_message = self._status_message(status, containers)
        self._screen._rebuild_list()
        self._screen._update_shortcuts()

    def _status_message(
        self,
        status: DockerStatus,
        containers: list[DetectedContainer],
    ) -> str | None:
        if status == DockerStatus.NOT_INSTALLED:
            return "(Docker not detected)"
        if status == DockerStatus.NOT_RUNNING:
            return "(Docker not running)"
        if status == DockerStatus.NOT_ACCESSIBLE:
            return "(Docker not accessible)"
        if status == DockerStatus.AVAILABLE and not containers:
            return "(no database containers found)"
        return None
