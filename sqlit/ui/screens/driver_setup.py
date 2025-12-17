"""ODBC driver setup screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static, TextArea
from textual.widgets.option_list import Option

from ...widgets import Dialog


class DriverSetupScreen(ModalScreen):
    """Screen for setting up ODBC drivers."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("i", "install_driver", "Install"),
        Binding("y", "yank", "Yank"),
    ]

    CSS = """
    DriverSetupScreen {
        align: center middle;
        background: transparent;
    }

    #driver-dialog {
        width: 80;
        height: auto;
        max-height: 90%;
    }

    #driver-message {
        margin-bottom: 1;
    }

    #driver-list {
        height: auto;
        max-height: 8;
        background: $surface;
        border: solid $primary-darken-2;
        margin-bottom: 1;
    }

    #install-commands {
        height: auto;
        max-height: 12;
        background: $surface-darken-1;
        padding: 1;
        margin-top: 1;
        overflow-y: auto;
    }
    """

    def __init__(self, installed_drivers: list[str] | None = None):
        super().__init__()
        self.installed_drivers = installed_drivers or []
        self._install_commands: list[str] = []
        self._install_script: str = ""

    def compose(self) -> ComposeResult:
        from ...drivers import SUPPORTED_DRIVERS, get_install_commands, get_os_info

        os_type, os_version = get_os_info()
        has_drivers = len(self.installed_drivers) > 0

        if has_drivers:
            title = "Select ODBC Driver"
            shortcuts = [("Select", "<enter>"), ("Yank", "y"), ("Cancel", "<esc>")]
        else:
            title = "No ODBC Driver Found"
            shortcuts = [("Select", "<enter>"), ("Install", "I"), ("Yank", "y"), ("Cancel", "<esc>")]

        with Dialog(id="driver-dialog", title=title, shortcuts=shortcuts):
            if has_drivers:
                yield Static(
                    f"Found {len(self.installed_drivers)} installed driver(s):",
                    id="driver-message",
                )
            else:
                yield Static(
                    f"Detected OS: [bold]{os_type}[/] {os_version}\n"
                    "You need an ODBC driver to connect to SQL Server.",
                    id="driver-message",
                )

            # Show installed drivers or available options
            options = []
            if has_drivers:
                for driver in self.installed_drivers:
                    options.append(Option(f"[#4ADE80]{driver}[/]", id=driver))
            else:
                for driver in SUPPORTED_DRIVERS[:3]:  # Show top 3 options
                    options.append(Option(f"[dim]{driver}[/] (not installed)", id=driver))

            yield OptionList(*options, id="driver-list")

            # Show install commands if no drivers
            if not has_drivers:
                install_info = get_install_commands()
                if install_info:
                    self._install_commands = install_info.commands
                    self._install_script = "\n".join(install_info.commands).strip()
                    yield TextArea(
                        f"{install_info.description}:\n\n{self._install_script}\n",
                        id="install-commands",
                        read_only=True,
                        language="bash",
                    )

    def on_mount(self) -> None:
        self.query_one("#driver-list", OptionList).focus()

    def action_select(self) -> None:
        option_list = self.query_one("#driver-list", OptionList)
        if option_list.highlighted is not None:
            option = option_list.get_option_at_index(option_list.highlighted)
            self.dismiss(("select", option.id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(("select", event.option.id))

    def action_install_driver(self) -> None:
        """Run installation commands for the selected driver."""
        if not self._install_commands:
            self.notify("No installation commands available", severity="warning")
            return

        from ...drivers import get_os_info

        os_type, _ = get_os_info()

        # On Windows, just show instructions
        if os_type == "windows":
            self.notify(
                "Please download and run the installer from Microsoft",
                severity="information",
            )
            return

        self.dismiss(("install", self._install_commands))

    def action_yank(self) -> None:
        from ...widgets import flash_widget

        script = self._install_script.strip()
        if not script:
            return
        self.app.copy_to_clipboard(script)
        flash_widget(self.query_one("#install-commands", TextArea))

    def action_cancel(self) -> None:
        self.dismiss(None)
