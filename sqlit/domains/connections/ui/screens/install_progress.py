"""Screen showing live install progress."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import RichLog, Static

from sqlit.shared.core.processes import AsyncProcess, AsyncProcessRunner, AsyncSubprocessRunner
from sqlit.shared.ui.widgets import Dialog


class InstallProgressScreen(ModalScreen[bool]):
    """Screen that shows live output of an install command."""

    BINDINGS = [
        Binding("enter", "ok", "OK", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    CSS = """
    InstallProgressScreen {
        align: center middle;
        background: transparent;
    }

    #install-dialog {
        width: 90;
        height: auto;
        max-height: 80%;
    }

    #install-command {
        margin-bottom: 1;
        color: $text-muted;
    }

    #install-output {
        height: 16;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
        padding: 0 1;
        scrollbar-size: 1 1;
    }

    #install-status {
        margin-top: 1;
        text-align: center;
    }

    #install-status.success {
        color: $success;
    }

    #install-status.error {
        color: $error;
    }

    #install-status.running {
        color: $text-muted;
    }
    """

    def __init__(self, package_name: str, command: str, *, process_runner: AsyncProcessRunner | None = None):
        super().__init__()
        self.package_name = package_name
        self.command = command
        self._process_runner = process_runner
        self._completed = False
        self._success = False
        self._process: AsyncProcess | None = None
        self._cancelled = False

    def compose(self) -> ComposeResult:
        title = f"Installing {self.package_name}"
        # Start with Cancel shortcut while installing
        shortcuts = [("Cancel", "<esc>")]

        with Dialog(id="install-dialog", title=title, shortcuts=shortcuts):
            yield Static(f"$ {self.command}", id="install-command")
            yield RichLog(id="install-output", highlight=True, markup=True)
            yield Static("Running...", id="install-status", classes="running")

    def _update_dialog_shortcuts(self, shortcuts: list[tuple[str, str]]) -> None:
        """Update the dialog's border subtitle with new shortcuts."""
        dialog = self.query_one("#install-dialog", Dialog)
        subtitle = "\u00a0·\u00a0".join(
            f"{action}: [bold]<{key}>[/]" for action, key in shortcuts
        )
        dialog.border_subtitle = subtitle

    def on_mount(self) -> None:
        self.run_worker(self._run_install(), exclusive=True)

    async def _run_install(self) -> None:
        """Run the install command and stream output."""
        log = self.query_one("#install-output", RichLog)
        status = self.query_one("#install-status", Static)

        try:
            runner = self._process_runner
            if runner is None:
                services = getattr(self.app, "services", None)
                runner = getattr(services, "async_process_runner", None) if services else None
            if runner is None:
                runner = AsyncSubprocessRunner()

            self._process = await runner.spawn(self.command)
            process = self._process
            if process is None:
                raise RuntimeError("Install process failed to start.")

            if process.stdout:
                async for line in process.stdout:
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    log.write(decoded)

            await process.wait()
            return_code = process.returncode

            self._completed = True
            self._process = None

            if self._cancelled:
                status.update("[bold]Installation cancelled[/]")
                status.remove_class("running")
                status.add_class("error")
            elif return_code == 0:
                self._success = True
                status.update("[bold]Installation complete[/]")
                status.remove_class("running")
                status.add_class("success")
            else:
                status.update(f"[bold]Installation failed[/] (exit code {return_code})")
                status.remove_class("running")
                status.add_class("error")

            # Update shortcuts to show OK when complete
            self._update_dialog_shortcuts([("OK", "enter")])

        except Exception as e:
            self._completed = True
            self._process = None
            log.write(f"[red]Error: {e}[/]")
            status.update("[bold]Installation failed[/]")
            status.remove_class("running")
            status.add_class("error")
            self._update_dialog_shortcuts([("OK", "enter")])

    def action_ok(self) -> None:
        """Dismiss the dialog (only works when completed)."""
        if self._completed:
            self.dismiss(self._success)

    def action_cancel(self) -> None:
        """Cancel the installation or dismiss if completed."""
        if self._completed:
            self.dismiss(self._success)
        elif self._process:
            self._cancelled = True
            try:
                self._process.terminate()
            except Exception:
                pass
