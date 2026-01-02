"""Connection test workflow for the connection screen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.widgets import Static

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.ui.driver_status_controller import DriverStatusController
from sqlit.shared.ui.protocols import AppProtocol
from sqlit.shared.ui.spinner import SPINNER_FRAMES, Spinner


class ConnectionTestController:
    """Run connection tests and update UI feedback."""

    def __init__(
        self,
        *,
        screen: Any,
        app: AppProtocol,
        driver_status: DriverStatusController,
    ) -> None:
        self._screen = screen
        self._app = app
        self._driver_status = driver_status
        self._test_in_progress: bool = False
        self._test_spinner: Spinner | None = None
        self._test_start_time: float = 0.0
        self._last_test_error: str = ""
        self._last_test_ok: bool | None = None

    @property
    def last_test_error(self) -> str:
        return self._last_test_error

    @property
    def last_test_ok(self) -> bool | None:
        return self._last_test_ok

    def _start_test_spinner(self) -> None:
        import time

        self._test_in_progress = True
        self._test_start_time = time.perf_counter()
        if self._test_spinner is not None:
            self._test_spinner.stop()
        self._test_spinner = Spinner(self._screen, on_tick=lambda _: self._update_test_status(), fps=30)
        self._test_spinner.start()

    def _stop_test_spinner(self) -> None:
        self._test_in_progress = False
        if self._test_spinner is not None:
            self._test_spinner.stop()
            self._test_spinner = None

    def _update_test_status(self) -> None:
        import time

        try:
            test_status = self._screen.query_one("#test-status", Static)
        except Exception:
            return

        if self._test_in_progress:
            elapsed = time.perf_counter() - self._test_start_time
            spinner_frame = self._test_spinner.frame if self._test_spinner else SPINNER_FRAMES[0]
            test_status.update(f"{spinner_frame} Testing ({elapsed:.1f}s)...")

    def test_connection(
        self,
        config: ConnectionConfig,
        *,
        write_restart_cache: Callable[[str | None], None],
        restart_app: Callable[[], None] | None,
    ) -> None:
        import time

        self._last_test_ok = None
        self._last_test_error = ""

        def on_test_success() -> None:
            self._stop_test_spinner()
            elapsed = time.perf_counter() - self._test_start_time
            try:
                set_health = getattr(self._app, "_set_connection_health", None)
                if callable(set_health):
                    set_health(config.name, True)
            except Exception:
                pass
            self._last_test_ok = True
            try:
                test_status = self._screen.query_one("#test-status", Static)
                test_status.update(f"[green]\u2713[/] Connection OK ({elapsed:.1f}s)")
            except Exception:
                pass

        def on_test_error(error: Exception) -> None:
            self._stop_test_spinner()
            elapsed = time.perf_counter() - self._test_start_time

            if isinstance(error, MissingDriverError):
                self._last_test_ok = False
                self._driver_status.prompt_install_missing_driver(
                    error,
                    write_restart_cache=write_restart_cache,
                    restart_app=restart_app,
                )
            elif isinstance(error, (ModuleNotFoundError, ImportError)):
                hint = self._driver_status.get_package_install_hint(config.db_type)
                if hint:
                    error_msg = f"Install with: {hint}"
                else:
                    error_msg = str(error)
                self._last_test_ok = False
                self._last_test_error = error_msg
                try:
                    test_status = self._screen.query_one("#test-status", Static)
                    test_status.update(f"[red]\u2717[/] Missing package ({elapsed:.1f}s)")
                except Exception:
                    pass
            else:
                try:
                    set_health = getattr(self._app, "_set_connection_health", None)
                    if callable(set_health):
                        set_health(config.name, False)
                except Exception:
                    pass
                self._last_test_ok = False
                self._last_test_error = str(error)
                try:
                    test_status = self._screen.query_one("#test-status", Static)
                    err_str = str(error)
                    if "]" in err_str:
                        err_str = err_str.split("]")[-1].strip()
                    if len(err_str) > 50:
                        err_str = err_str[:47] + "..."
                    test_status.update(f"[red]\u2717[/] {err_str} ({elapsed:.1f}s)")
                except Exception:
                    pass

        def do_test() -> None:
            try:
                manager = self._app._connection_manager
                assert manager is not None
                result = manager.test_connection(config)
                if result.ok:
                    self._screen.app.call_from_thread(on_test_success)
                else:
                    self._screen.app.call_from_thread(on_test_error, result.error)
            except Exception as e:
                self._screen.app.call_from_thread(on_test_error, e)

        self._start_test_spinner()
        self._screen.run_worker(do_test, name="test-connection", thread=True, exclusive=True)
