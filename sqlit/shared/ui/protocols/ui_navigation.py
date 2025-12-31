"""Protocols for UI navigation and state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.timer import Timer
    from textual.widgets import Static


class UIStateProtocol(Protocol):
    _fullscreen_mode: str
    _last_notification: str
    _last_notification_severity: str
    _last_notification_time: str
    _notification_timer: Timer | None
    _notification_history: list[tuple[str, str, str]]
    _leader_timer: Timer | None
    _leader_pending: bool
    _leader_pending_menu: str
    _last_active_pane: str | None
    _state_machine: Any
    _active_database: str | None
    _query_target_database: str | None
    log: Any


class UINavigationActionsProtocol(Protocol):
    def _update_status_bar(self) -> None:
        ...

    def _update_footer_bindings(self) -> None:
        ...

    def _set_fullscreen_mode(self, mode: str) -> None:
        ...

    def _update_section_labels(self) -> None:
        ...

    def _sync_active_pane_title(self) -> None:
        ...

    def _update_idle_scheduler_bar(self) -> None:
        ...

    def _show_error_in_results(self, message: str, timestamp: str) -> None:
        ...

    def _show_leader_menu(self, menu: str = "leader") -> None:
        ...

    def _cancel_leader_pending(self) -> None:
        ...

    def _start_leader_pending(self, menu: str) -> None:
        ...

    def _handle_leader_result(self, result: str | None) -> None:
        ...

    def _execute_leader_command(self, action: str) -> None:
        ...

    def action_close_value_view(self) -> None:
        ...

    def action_copy_value_view(self) -> None:
        ...

    @property
    def idle_scheduler_bar(self) -> Static:
        ...


class UINavigationProtocol(UIStateProtocol, UINavigationActionsProtocol, Protocol):
    """Composite protocol for UI navigation mixins."""

    pass
