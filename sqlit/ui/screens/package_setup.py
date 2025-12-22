"""Package setup screen for missing Python drivers."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ...db.exceptions import MissingDriverError
from ...install_strategy import detect_strategy
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
    """

    def __init__(self, error: MissingDriverError, *, on_install: Callable[[MissingDriverError], None]):
        super().__init__()
        self.error = error
        self._on_install = on_install
        self._instructions_text = ""
        self._can_auto_install = True

    def compose(self) -> ComposeResult:
        strategy = detect_strategy(extra_name=self.error.extra_name, package_name=self.error.package_name)
        has_import_error = bool(getattr(self.error, "import_error", None))
        self._can_auto_install = strategy.can_auto_install and not has_import_error
        instructions = []
        if has_import_error:
            details = str(self.error.import_error).strip()
            if details:
                instructions.append("Import error:")
                instructions.append(details)
                instructions.append("")
        instructions.append(strategy.manual_instructions.strip())
        self._instructions_text = "\n".join(instructions).strip() + "\n"

        shortcuts = [("Yank", "y"), ("Cancel", "<esc>")]
        if self._can_auto_install:
            shortcuts.insert(0, ("Install", "i"))
        title = "Driver import failed" if has_import_error else "Missing package"
        if has_import_error:
            message = (
                f"The [bold]{self.error.driver_name}[/] driver is installed but failed to load.\n"
                f"Package: [bold]{self.error.package_name}[/]"
            )
        else:
            message = (
                f"This connection requires the [bold]{self.error.driver_name}[/] driver.\n"
                f"Package: [bold]{self.error.package_name}[/]"
            )
        with Dialog(id="package-dialog", title=title, shortcuts=shortcuts):
            yield Static(
                message,
                id="package-message",
            )

            with VerticalScroll(id="package-scroll"):
                yield Static(self._instructions_text.strip(), id="package-script")

    def on_mount(self) -> None:
        self.query_one("#package-scroll", VerticalScroll).focus()

    def action_install(self) -> None:
        if not self._can_auto_install:
            try:
                self.app.notify(
                    "Automatic installation isn't available for this Python environment.",
                    severity="warning",
                    timeout=6,
                )
            except Exception:
                pass
            return
        self._on_install(self.error)

    def action_yank(self) -> None:
        from ...widgets import flash_widget

        self.app.copy_to_clipboard(self._instructions_text.strip())
        flash_widget(self.query_one("#package-script", Static))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        if action == "install" and not self._can_auto_install:
            return False
        return super().check_action(action, parameters)
