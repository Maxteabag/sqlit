"""Password input dialog screen."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from sqlit.shared.ui.widgets import Dialog


class PasswordInputScreen(ModalScreen):
    """Modal screen for password input.

    This screen prompts the user to enter a password when connecting
    to a database that has no stored password.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "submit", "Submit", show=False),
        Binding("tab", "focus_next", "Next field", show=False, priority=True),
        Binding("shift+tab", "focus_prev", "Previous field", show=False, priority=True),
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

    #password-row {
        width: 100%;
        height: 1;
    }

    #password-row Input {
        width: 1fr;
    }

    #password-toggle {
        width: 6;
        min-width: 6;
        height: 1;
        border: none;
        margin-left: 1;
        padding: 0;
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
        self._submit_logged = False
        self._cancel_logged = False
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
            container = Container(id="password-container")
            container.border_title = "Password"
            with container:
                row = Horizontal(id="password-row")
                row.compose_add_child(
                    Input(
                        value="",
                        placeholder="",
                        id="password-input",
                        password=True,
                    )
                )
                row.compose_add_child(Button("Show", id="password-toggle"))
                yield row

    def on_mount(self) -> None:
        self.query_one("#password-input", Input).focus()
        self._emit_debug(
            "password_prompt.open",
            connection=self.connection_name,
            password_type=self.password_type,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "password-input":
            self._log_submit("input_submitted", event.value)
            self.dismiss(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "password-toggle":
            return
        input_widget = self.query_one("#password-input", Input)
        input_widget.password = not input_widget.password
        event.button.label = "Hide" if not input_widget.password else "Show"
        input_widget.focus()

    def action_focus_next(self) -> None:
        input_widget = self.query_one("#password-input", Input)
        toggle_btn = self.query_one("#password-toggle", Button)
        if self.focused is input_widget:
            toggle_btn.focus()
        else:
            input_widget.focus()

    def action_focus_prev(self) -> None:
        self.action_focus_next()

    def on_descendant_focus(self, event: Any) -> None:
        try:
            container = self.query_one("#password-container")
            container.add_class("focused")
        except Exception:
            pass

    def on_descendant_blur(self, event: Any) -> None:
        try:
            container = self.query_one("#password-container")
            container.remove_class("focused")
        except Exception:
            pass

    def action_submit(self) -> None:
        password = self.query_one("#password-input", Input).value
        self._log_submit("action_submit", password)
        self.dismiss(password)

    def action_cancel(self) -> None:
        if not self._cancel_logged:
            self._emit_debug(
                "password_prompt.cancel",
                connection=self.connection_name,
                password_type=self.password_type,
            )
            self._cancel_logged = True
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            if action in {"cancel", "submit"}:
                self._emit_debug(
                    "password_prompt.action_blocked",
                    action=action,
                    active_screen=getattr(self.app.screen, "__class__", type(self.app.screen)).__name__,
                )
            return False
        return super().check_action(action, parameters)

    def _emit_debug(self, name: str, **data: Any) -> None:
        emit = getattr(self.app, "emit_debug_event", None)
        if callable(emit):
            emit(name, **data)

    def _log_submit(self, source: str, value: str) -> None:
        if self._submit_logged:
            return
        self._submit_logged = True
        self._emit_debug(
            "password_prompt.submit",
            connection=self.connection_name,
            password_type=self.password_type,
            source=source,
            value_len=len(value),
        )
