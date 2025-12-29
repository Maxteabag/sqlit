"""Screen showing live install progress."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import RichLog, Static

from ...widgets import Dialog


class InstallProgressScreen(ModalScreen[bool]):
    """Screen that shows live output of an install command."""

    BINDINGS = [
        Binding("enter", "ok", "OK", priority=True),
        Binding("escape", "ok", "OK", priority=True),
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

    def __init__(self, package_name: str, command: str):
        super().__init__()
        self.package_name = package_name
        self.command = command
        self._completed = False
        self._success = False

    def compose(self) -> ComposeResult:
        title = f"Installing {self.package_name}"
        shortcuts = [("OK", "<enter>")]

        with Dialog(id="install-dialog", title=title, shortcuts=shortcuts):
            yield Static(f"$ {self.command}", id="install-command")
            yield RichLog(id="install-output", highlight=True, markup=True)
            yield Static("Running...", id="install-status", classes="running")

    def on_mount(self) -> None:
        self.run_worker(self._run_install(), exclusive=True)

    async def _run_install(self) -> None:
        """Run the install command and stream output."""
        log = self.query_one("#install-output", RichLog)
        status = self.query_one("#install-status", Static)

        try:
            process = await asyncio.create_subprocess_shell(
                self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            if process.stdout:
                async for line in process.stdout:
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    log.write(decoded)

            await process.wait()
            return_code = process.returncode

            self._completed = True
            if return_code == 0:
                self._success = True
                status.update("[bold]Installation complete[/]")
                status.remove_class("running")
                status.add_class("success")
            else:
                status.update(f"[bold]Installation failed[/] (exit code {return_code})")
                status.remove_class("running")
                status.add_class("error")

        except Exception as e:
            self._completed = True
            log.write(f"[red]Error: {e}[/]")
            status.update("[bold]Installation failed[/]")
            status.remove_class("running")
            status.add_class("error")

    def action_ok(self) -> None:
        self.dismiss(self._success)
