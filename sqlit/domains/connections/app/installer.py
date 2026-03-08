"""Service for handling automatic package installation."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from sqlit.domains.connections.app.install_strategy import detect_strategy
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.shared.core.processes import SubprocessRunner, SyncProcess, SyncProcessRunner


class InstallerApp(Protocol):
    def push_screen(self, screen: Any, callback: Any = None, wait_for_dismiss: bool = False) -> Any: ...
    def pop_screen(self) -> Any: ...
    def call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...
    def notify(self, message: str, *, severity: str = "information", timeout: float | int | None = None) -> Any: ...
    def restart(self) -> Any: ...


class Installer:
    """Manages the automatic installation of missing drivers."""

    def __init__(self, app: InstallerApp, *, process_runner: SyncProcessRunner | None = None):
        self.app = app
        self._process_runner = process_runner
        self._active_process: SyncProcess | None = None

    def install(self, error: MissingDriverError) -> None:
        """Push a loading screen and run installation in a background thread."""
        from sqlit.shared.ui.screens.loading import LoadingScreen

        cancel_event = threading.Event()
        self.app.push_screen(
            LoadingScreen(
                f"Installing {error.driver_name}... (Esc to cancel)",
                on_cancel=cancel_event.set,
            )
        )

        def worker() -> None:
            result = self._do_install(error, cancel_event)
            self.app.call_from_thread(self._on_install_complete, result)

        threading.Thread(target=worker, daemon=True).start()

    def install_in_background(
        self,
        error: MissingDriverError,
        *,
        on_complete: Callable[[bool, str, MissingDriverError], None],
    ) -> None:
        """Run installation in a background thread and report completion on the main thread."""

        def worker() -> None:
            # Reuse the same implementation, but without the modal LoadingScreen.
            result = self._do_install(error, threading.Event())
            success, output, err = result
            self.app.call_from_thread(on_complete, success, output, err)

        threading.Thread(target=worker, daemon=True).start()

    def _do_install(
        self, error: MissingDriverError, cancel_event: threading.Event
    ) -> tuple[bool, str, MissingDriverError]:
        """
        Synchronous method to be run in a worker thread.
        Determines the command and executes it.
        """
        services = getattr(self.app, "services", None)

        if services is not None:
            strategy = services.install_strategy.detect(
                extra_name=error.extra_name,
                package_name=error.package_name,
            )
        else:
            strategy = detect_strategy(extra_name=error.extra_name, package_name=error.package_name)
        if not strategy.can_auto_install or not strategy.auto_install_command:
            reason = strategy.reason_unavailable or "Automatic installation is not available."
            return False, f"{reason}\n\n{strategy.manual_instructions}".strip(), error

        command = strategy.auto_install_command
        cwd: str | None = None

        if cancel_event.is_set():
            return False, "Installation cancelled by user.", error

        try:
            runner = self._process_runner
            if runner is None and services is not None:
                runner = getattr(services, "sync_process_runner", None)
            if runner is None:
                runner = SubprocessRunner()

            self._active_process = runner.spawn(command, cwd=cwd)
            process = self._active_process
            if process is None:
                return False, "Installation failed to start.", error

            stdout = ""
            stderr = ""

            while True:
                if cancel_event.is_set():
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except Exception:
                        try:
                            process.kill()
                            process.wait(timeout=5)
                        except Exception:
                            pass
                    try:
                        stdout, stderr = process.communicate(timeout=1)
                    except Exception:
                        pass
                    return False, "Installation cancelled by user.", error

                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    time.sleep(0.05)
                    continue

            rc = process.returncode
            if rc == 0:
                return True, stdout, error
            return False, stderr or stdout, error
        except FileNotFoundError as e:
            return False, str(e), error
        finally:
            self._active_process = None

    def _on_install_complete(self, result: tuple[bool, str, MissingDriverError]) -> None:
        """
        Callback executed on the main thread after installation attempt.
        """
        from textual.css.stylesheet import StylesheetParseError

        from sqlit.shared.ui.screens.message import MessageScreen

        success, _output, error = result
        self.app.pop_screen()  # Pop the LoadingScreen

        try:
            if success:
                restart = getattr(self.app, "restart", None)
                on_enter = None
                if callable(restart):
                    def _restart() -> None:
                        restart()
                        return None

                    on_enter = _restart
                self.app.push_screen(
                    MessageScreen(
                        "Driver installed",
                        f"{error.driver_name} installed successfully. Please restart to apply.",
                        enter_label="Restart",
                        on_enter=on_enter,
                    )
                )
            else:
                # Keep the manual instructions in the underlying setup screen.
                self.app.push_screen(
                    MessageScreen(
                        "Couldn't install automatically",
                        "Couldn't install automatically, please install manually.",
                    )
                )
        except StylesheetParseError as e:
            # Fallback: avoid crashing the app if the stylesheet can't be reparsed after install.
            try:
                details = str(e.args[0])
            except Exception:
                details = str(e)
            print(f"StylesheetParseError while showing install result:\n{details}", file=sys.stderr)
            try:
                self.app.notify(
                    "Installation completed, but UI failed to render result. Please restart sqlit-tui.",
                    severity="warning",
                    timeout=10,
                )
            except Exception:
                pass
