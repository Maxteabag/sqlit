"""Folder input dialog for organizing connections."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from sqlit.shared.ui.widgets import Dialog


class FolderInputScreen(ModalScreen):
    """Modal screen for setting a connection folder path."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "submit", "Save", show=False),
    ]

    CSS = """
    FolderInputScreen {
        align: center middle;
        background: transparent;
    }

    #folder-dialog {
        width: 60;
        height: auto;
        max-height: 14;
    }

    #folder-description {
        margin-bottom: 1;
        color: $text-muted;
        height: auto;
    }

    #folder-container {
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

    #folder-container.focused {
        border: solid $primary;
        border-title-color: $primary;
    }

    #folder-container Input {
        border: none;
        height: 1;
        padding: 0;
        background: $surface;
    }

    #folder-container Input:focus {
        border: none;
        background-tint: $foreground 5%;
    }
    """

    def __init__(
        self,
        connection_name: str,
        *,
        current_value: str = "",
        title: str = "Move to Folder",
        description: str | None = None,
    ) -> None:
        super().__init__()
        self.connection_name = connection_name
        self._title = title
        self._value = current_value
        if description is not None:
            self._description = description
        else:
            self._description = (
                f"Folder for '{connection_name}' (use / for nesting, blank for root):"
            )

    def compose(self) -> ComposeResult:
        shortcuts: list[tuple[str, str]] = [("Save", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(id="folder-dialog", title=self._title, shortcuts=shortcuts):
            yield Static(self._description, id="folder-description")
            from textual.containers import Container

            container = Container(id="folder-container")
            container.border_title = "Folder"
            with container:
                yield Input(
                    value=self._value,
                    placeholder="e.g. prod/analytics",
                    id="folder-input",
                    password=False,
                )

    def on_mount(self) -> None:
        self.query_one("#folder-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "folder-input":
            self.dismiss(event.value)

    def on_descendant_focus(self, event: Any) -> None:
        try:
            container = self.query_one("#folder-container")
            container.add_class("focused")
        except Exception:
            pass

    def on_descendant_blur(self, event: Any) -> None:
        try:
            container = self.query_one("#folder-container")
            container.remove_class("focused")
        except Exception:
            pass

    def action_submit(self) -> None:
        value = self.query_one("#folder-input", Input).value
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
