"""Package setup screen for missing Python drivers."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ...db.exceptions import MissingDriverError
from ...widgets import Dialog


class PackageSetupScreen(ModalScreen):
    """Screen that shows install instructions for a missing Python package."""

    BINDINGS = [
        Binding("i", "install", "Install"),
        Binding("y", "yank", "Yank"),
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    PackageSetupScreen {
        align: center middle;
        background: transparent;
    }

    #package-dialog {
        width: 80;
        height: auto;
        max-height: 90%;
    }

    #package-message {
        margin-bottom: 1;
    }

    #package-scroll {
        height: auto;
        max-height: 12;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
        padding: 1;
        margin-top: 1;
        overflow-y: auto;
    }

    #package-script.flash-copy {
        background: $primary 30%;
    }
    """

    def __init__(self, error: MissingDriverError, *, on_install: Callable[[MissingDriverError], None]):
        super().__init__()
        self.error = error
        self._on_install = on_install
        self._instructions_text = ""

    def _detect_installer(self) -> str:
        pipx_override = os.environ.get("SQLIT_MOCK_PIPX", "").strip().lower()
        is_pipx = "pipx" in sys.executable
        if pipx_override in {"1", "true", "yes", "pipx"}:
            is_pipx = True
        elif pipx_override in {"0", "false", "no", "pip"}:
            is_pipx = False

        return "pipx" if is_pipx else "pip"

    def compose(self) -> ComposeResult:
        installer = self._detect_installer()
        if installer == "pipx":
            self._instructions_text = f"pipx inject sqlit-tui {self.error.package_name}\n"
        else:
            self._instructions_text = f'pip install "sqlit-tui[{self.error.extra_name}]"\n'

        shortcuts = [("Install", "i"), ("Yank", "y"), ("Cancel", "<esc>")]
        with Dialog(id="package-dialog", title="Missing package", shortcuts=shortcuts):
            yield Static(
                f"This connection requires the [bold]{self.error.driver_name}[/] driver.\n"
                f"Package: [bold]{self.error.package_name}[/]",
                id="package-message",
            )

            with VerticalScroll(id="package-scroll"):
                yield Static(self._instructions_text.strip(), id="package-script")

    def on_mount(self) -> None:
        self.query_one("#package-scroll", VerticalScroll).focus()

    def action_install(self) -> None:
        self._on_install(self.error)

    def action_yank(self) -> None:
        self.app.copy_to_clipboard(self._instructions_text.strip())
        script = self.query_one("#package-script", Static)
        script.add_class("flash-copy")
        self.set_timer(0.15, lambda: script.remove_class("flash-copy"))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
