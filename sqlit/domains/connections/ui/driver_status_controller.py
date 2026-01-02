"""Driver availability checks and status updates for connection screens."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.widgets import Static

from sqlit.domains.connections.domain.config import DatabaseType
from sqlit.domains.connections.providers.driver import ensure_provider_driver_available
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.providers.metadata import supports_ssh
from sqlit.domains.connections.ui.driver_status import build_driver_status_display
from sqlit.shared.ui.protocols import AppProtocol
from sqlit.shared.ui.widgets import Dialog


class DriverStatusController:
    """Encapsulate driver checks, install prompts, and status display updates."""

    def __init__(self, *, app: AppProtocol, post_install_message: str | None) -> None:
        self._app = app
        self._post_install_message = post_install_message
        self._missing_driver_error: MissingDriverError | None = None
        self._missing_ssh_driver_error: MissingDriverError | None = None

    @property
    def missing_driver_error(self) -> MissingDriverError | None:
        return self._missing_driver_error

    @property
    def missing_ssh_driver_error(self) -> MissingDriverError | None:
        return self._missing_ssh_driver_error

    def check_driver_availability(self, db_type: DatabaseType) -> None:
        self._missing_driver_error = None
        try:
            provider = self._app.services.provider_factory(db_type.value)
            ensure_provider_driver_available(provider, resolver=self._app.services.driver_resolver)
        except MissingDriverError as e:
            self._missing_driver_error = e

    def check_ssh_driver_availability(self, db_type: DatabaseType) -> None:
        from sqlit.domains.connections.app.tunnel import ensure_ssh_tunnel_available

        self._missing_ssh_driver_error = None
        if not supports_ssh(db_type.value):
            return
        try:
            ensure_ssh_tunnel_available()
        except MissingDriverError as e:
            self._missing_ssh_driver_error = e

    def update_status_ui(self, *, active_tab: str, test_status: Static | None, dialog: Dialog | None) -> None:
        if test_status is None or dialog is None:
            return

        try:
            test_status.remove_class("success")
        except Exception:
            pass

        error = self._missing_ssh_driver_error if active_tab == "tab-ssh" else self._missing_driver_error

        display = build_driver_status_display(
            error,
            self._post_install_message,
            self._app.services.install_strategy,
        )
        test_status.update(display.message)
        if display.success:
            try:
                test_status.add_class("success")
            except Exception:
                pass
        dialog.border_subtitle = display.subtitle

    def prompt_install_missing_driver(
        self,
        error: Exception,
        *,
        write_restart_cache: Callable[[str | None], None],
        restart_app: Callable[[], None] | None,
    ) -> None:
        from sqlit.domains.connections.ui.screens.package_setup import PackageSetupScreen

        if not isinstance(error, MissingDriverError):
            return

        def on_install_success() -> None:
            write_restart_cache("Successfully installed driver")
            if restart_app is not None:
                restart_app()

        self._app.push_screen(PackageSetupScreen(error, on_success=on_install_success))

    def prompt_install_for_active_tab(
        self,
        active_tab: str,
        *,
        write_restart_cache: Callable[[str | None], None],
        restart_app: Callable[[], None] | None,
    ) -> None:
        error = self._missing_ssh_driver_error if active_tab == "tab-ssh" else self._missing_driver_error
        if error is not None:
            self.prompt_install_missing_driver(
                error,
                write_restart_cache=write_restart_cache,
                restart_app=restart_app,
            )

    def get_package_install_hint(self, db_type: str) -> str | None:
        try:
            provider = self._app.services.provider_factory(db_type)
            driver = provider.driver
            if driver is None or not driver.package_name or not driver.extra_name:
                return None
            strategy = self._app.services.install_strategy.detect(
                extra_name=driver.extra_name,
                package_name=driver.package_name,
            )
            if strategy.can_auto_install:
                return self._format_install_hint(strategy)
            manual = getattr(strategy, "manual_instructions", "")
            if isinstance(manual, str) and manual:
                return manual.split("\n")[0].strip()
            return None
        except (ValueError, ImportError):
            return None

    def _format_install_hint(self, strategy: Any) -> str:
        from sqlit.domains.connections.ui.driver_status import _format_install_hint

        return _format_install_hint(strategy)
