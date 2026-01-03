"""Leader key helpers for UI navigation."""

from __future__ import annotations

from typing import Any

from sqlit.shared.ui.protocols import UINavigationMixinHost


class UILeaderMixin:
    """Mixin providing leader-key menu handling."""

    _leader_timer: Any | None = None
    _leader_pending: bool = False
    _leader_pending_menu: str = "leader"
    def action_leader_key(self: UINavigationMixinHost) -> None:
        """Handle leader key (space) press - show command menu after delay."""
        self._start_leader_pending("leader")

    def action_delete_leader_key(self: UINavigationMixinHost) -> None:
        """Handle delete leader key (d) press - show delete menu after delay."""
        self._start_leader_pending("delete")

    def _start_leader_pending(self: UINavigationMixinHost, menu: str) -> None:
        """Start a leader-style pending state and show menu if no follow-up key."""
        from sqlit.core.vim import VimMode

        # Don't trigger in INSERT mode
        if self.vim_mode == VimMode.INSERT:
            return

        # Cancel any existing timer
        if hasattr(self, "_leader_timer") and self._leader_timer is not None:
            self._leader_timer.stop()

        self._leader_pending = True
        self._leader_pending_menu = menu

        def show_menu() -> None:
            if getattr(self, "_leader_pending", False):
                self._leader_pending = False
                self._show_leader_menu(menu)

        # Show menu after 350ms delay
        self._leader_timer = self.set_timer(0.35, show_menu)

    def _cancel_leader_pending(self: UINavigationMixinHost) -> None:
        """Cancel leader pending state and timer."""
        self._leader_pending = False
        self._leader_pending_menu = "leader"
        if hasattr(self, "_leader_timer") and self._leader_timer is not None:
            self._leader_timer.stop()
            self._leader_timer = None

    def _execute_leader_command(self: UINavigationMixinHost, action: str) -> None:
        """Execute a leader command by action name.

        Also clears leader pending state - this is the single place
        where leader state transitions happen (except timeout → menu).
        """
        self._cancel_leader_pending()
        if action == "quit":
            self.exit()
            return
        action_method = getattr(self, f"action_{action}", None)
        if action_method:
            action_method()

    def _show_leader_menu(self: UINavigationMixinHost, menu: str = "leader") -> None:
        """Display a leader menu."""
        from textual.screen import ModalScreen

        from ..screens import LeaderMenuScreen

        if any(isinstance(screen, ModalScreen) for screen in self.screen_stack[1:]):
            return

        self.push_screen(LeaderMenuScreen(menu), self._handle_leader_result)

    def _handle_leader_result(self: UINavigationMixinHost, result: str | None) -> None:
        """Handle result from leader menu."""
        self._update_footer_bindings()
        if not result:
            return
        action_method = getattr(self, f"action_{result}", None)
        if action_method:
            action_method()
            return
        self._execute_leader_command(result)

    def action_leader_toggle_explorer(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("toggle_explorer")

    def action_leader_toggle_fullscreen(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("toggle_fullscreen")

    def action_leader_show_connection_picker(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("show_connection_picker")

    def action_leader_disconnect(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("disconnect")

    def action_leader_cancel_operation(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("cancel_operation")

    def action_leader_change_theme(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("change_theme")

    def action_leader_toggle_process_worker(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("toggle_process_worker")

    def action_leader_show_help(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("show_help")

    def action_leader_telescope(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("telescope")

    def action_leader_quit(self: UINavigationMixinHost) -> None:
        self._execute_leader_command("quit")
