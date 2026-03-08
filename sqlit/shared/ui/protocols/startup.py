"""Protocol for startup-related state used by startup_flow."""

from __future__ import annotations

from typing import Any, Protocol

from sqlit.domains.connections.domain.config import ConnectionConfig


class StartupProtocol(Protocol):
    services: Any
    _restart_argv: list[str] | None
    _startup_profile: bool
    _startup_mark: float | None
    _startup_init_time: float
    _startup_events: list[tuple[str, float]]
    _startup_connection: ConnectionConfig | None
    _startup_connect_config: ConnectionConfig | None
    _debug_mode: bool
    _debug_idle_scheduler: bool
    _idle_scheduler: Any | None
    _idle_scheduler_bar_timer: Any | None
    _theme_manager: Any
    _expanded_paths: set[str]

    def _startup_stamp(self, name: str) -> None:
        ...

    def _record_launch_ms(self) -> None:
        ...

    def _compute_restart_argv(self) -> list[str]:
        ...
