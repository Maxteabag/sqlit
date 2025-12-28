"""Password input dialog screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ...widgets import Dialog


class PasswordInputScreen(ModalScreen):
    """Modal screen for password input.

    This screen prompts the user to enter a password when connecting
    to a database that has no stored password.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Submit", show=False),
    ]

    CSS = """
    PasswordInputScreen {
        align: center middle;
        background: transparent;
    }

    #password-dialog {
        width: 50;
        height: auto;
        max-height: 12;
    }

    #password-description {
        margin-bottom: 1;
        color: $text-muted;
        height: auto;
    }

    #password-container {
        border: solid $panel;
        background: $surface;
        padding: 0;
        margin-top: 0;
        height: 3;
        border-title-align: left;
        border-title-color: $text-muted;
        border-title-background: $surface;
        border-title-style: none;
    }

    #password-container.focused {
        border: solid $primary;
        border-title-color: $primary;
    }

    #password-container Input {
        border: none;
        height: 1;
        padding: 0;
        background: $surface;
    }

    #password-container Input:focus {
        border: none;
        background-tint: $foreground 5%;
    }
    """

    def __init__(
        self,
        connection_name: str,
        *,
        title: str = "Password Required",
        description: str | None = None,
        password_type: str = "database",
    ):
        """Initialize the password input screen.

        Args:
            connection_name: The name of the connection requiring the password.
            title: The dialog title.
            description: Optional description text.
            password_type: Type of password ("database" or "ssh").
        """
        super().__init__()
        self.connection_name = connection_name
        self.title_text = title
        self.password_type = password_type
        if description:
            self.description = description
        else:
            if password_type == "ssh":
                self.description = f"Enter SSH password for '{connection_name}':"
            else:
                self.description = f"Enter password for '{connection_name}':"

    def compose(self) -> ComposeResult:
        shortcuts: list[tuple[str, str]] = [("Submit", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(id="password-dialog", title=self.title_text, shortcuts=shortcuts):
            yield Static(self.description, id="password-description")
            from textual.containers import Container

            container = Container(id="password-container")
            container.border_title = "Password"
            with container:
                yield Input(
                    value="",
                    placeholder="",
                    id="password-input",
                    password=False,
                )

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            self.dismiss(event.value)

    def on_descendant_focus(self, event) -> None:
        try:
            container = self.query_one("#password-container")
            container.add_class("focused")
        except Exception:
            pass

    def on_descendant_blur(self, event) -> None:
        try:
            container = self.query_one("#password-container")
            container.remove_class("focused")
        except Exception:
            pass

    def action_submit(self) -> None:
        password = self.query_one("#password-input", Input).value
        self.dismiss(password)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
