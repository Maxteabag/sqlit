"""Package setup screen for missing Python drivers."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.app.install_strategy import (
    InstallOption,
    detect_install_method,
    get_install_options,
)
from sqlit.shared.ui.widgets import Dialog


class PackageSetupScreen(ModalScreen):
    """Screen that shows install options for a missing Python package."""

    BINDINGS = [
        Binding("enter", "install", "Install", priority=True),
        Binding("y", "yank", "Yank"),
        Binding("escape", "cancel", "Cancel", priority=True),
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

    #install-options {
        height: auto;
        max-height: 12;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
        margin-top: 1;
    }

    #install-options > .option-list--option {
        padding: 0 1;
    }

    #install-options > .option-list--option-highlighted {
        background: $primary-darken-1;
    }
    """

    def __init__(
        self,
        error: MissingDriverError,
        *,
        on_success: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.error = error
        self._on_success = on_success
        self._install_options: list[InstallOption] = []

    def compose(self) -> ComposeResult:
        has_import_error = bool(getattr(self.error, "import_error", None))
        title = "Driver import failed" if has_import_error else "Missing package"

        message = (
            f"This connection requires the [bold]{self.error.driver_name}[/] driver.\n"
            f"Package: [bold]{self.error.package_name}[/]\n\n"
            f"[bold]Install the driver using your preferred package manager:[/]"
        )

        shortcuts = [("Install", "<enter>"), ("Yank", "y"), ("Cancel", "<esc>")]

        mock_pipx = getattr(getattr(self.app, "services", None), "runtime", None)
        mock_pipx = getattr(getattr(mock_pipx, "mock", None), "pipx_mode", None)
        self._install_options = get_install_options(self.error.package_name, mock_pipx=mock_pipx)

        with Dialog(id="package-dialog", title=title, shortcuts=shortcuts):
            yield Static(message, id="package-message")

            detected = detect_install_method(mock_pipx=mock_pipx)
            option_list = OptionList(id="install-options")
            for opt in self._install_options:
                if opt.label == detected:
                    label = f"[bold]{opt.label:<8}[/] {opt.command}  [dim](Detected)[/]"
                else:
                    label = f"[bold]{opt.label:<8}[/] {opt.command}"
                option_list.add_option(Option(label, id=opt.label))
            option_list.highlighted = 0
            yield option_list

    def on_mount(self) -> None:
        self.query_one("#install-options", OptionList).focus()

    def _get_selected_option(self) -> str | None:
        """Get the command for the currently selected option."""
        option_list = self.query_one("#install-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is not None and highlighted < len(self._install_options):
            return self._install_options[highlighted].command
        return None

    def action_install(self) -> None:
        from .install_progress import InstallProgressScreen

        command = self._get_selected_option()
        if command:

            def on_install_complete(success: bool | None) -> None:
                if success and self._on_success:
                    # Caller handles success (e.g., connection screen caches form and restarts)
                    self._on_success()
                    self.dismiss(None)
                elif success:
                    # Default: show notification and restart
                    self.app.notify(
                        f"{self.error.driver_name} installed successfully. Restarting...",
                        timeout=3,
                    )
                    self.dismiss(None)
                    restart = getattr(self.app, "restart", None)
                    if callable(restart):
                        restart()
                else:
                    self.dismiss(None)

            self.app.push_screen(
                InstallProgressScreen(self.error.package_name, command),
                on_install_complete,
            )

    def action_yank(self) -> None:
        from sqlit.shared.ui.widgets import flash_widget

        command = self._get_selected_option()
        if command:
            self.app.copy_to_clipboard(command)
            flash_widget(self.query_one("#install-options", OptionList))

    def action_cancel(self) -> None:
        self.dismiss(None)
