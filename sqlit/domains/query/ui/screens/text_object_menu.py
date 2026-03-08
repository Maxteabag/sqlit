"""Text object pending menu screen for i/a (inner/around) text objects."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.shared.ui.widgets import Dialog


class TextObjectMenuScreen(ModalScreen[str | None]):
    """Modal screen showing text object options for inner/around."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("w", "select_w", "word", show=False),
        Binding("W", "select_W", "WORD", show=False),
        Binding("(", "select_paren", "(", show=False),
        Binding(")", "select_paren", ")", show=False),
        Binding("b", "select_paren", "b", show=False),
        Binding("[", "select_square", "[", show=False),
        Binding("]", "select_square", "]", show=False),
        Binding("{", "select_curly", "{", show=False),
        Binding("}", "select_curly", "}", show=False),
        Binding("B", "select_curly", "B", show=False),
        Binding("<", "select_angle", "<", show=False),
        Binding(">", "select_angle", ">", show=False),
        Binding('"', "select_dquote", '"', show=False),
        Binding("'", "select_squote", "'", show=False),
        Binding("`", "select_backtick", "`", show=False),
    ]

    CSS = """
    TextObjectMenuScreen {
        align: right bottom;
        background: rgba(0, 0, 0, 0);
        overlay: none;
    }

    #text-object-menu {
        max-width: 35;
        margin: 0;
        border: solid $primary;
    }

    #text-object-menu-content {
        width: auto;
        height: auto;
    }
    """

    def __init__(self, mode: str, operator: str = "delete") -> None:
        """Initialize the text object menu.

        Args:
            mode: Either "inner" or "around"
            operator: The operator context ("delete", "yank", or "change")
        """
        super().__init__()
        self._mode = mode
        self._operator = operator

    def compose(self) -> ComposeResult:
        prefix = "inner" if self._mode == "inner" else "around"
        op_name = self._operator.capitalize()
        title = f"{op_name} {prefix}..."

        content = f"""[bold $text-muted]{title}[/]

[bold $text-muted]Words[/]
  [bold $warning]w[/] word    [bold $warning]W[/] WORD

[bold $text-muted]Brackets[/]
  [bold $warning]( ) b[/] parentheses
  [bold $warning][ ][/]   square brackets
  [bold $warning]{{ }} B[/] curly braces
  [bold $warning]< >[/]   angle brackets

[bold $text-muted]Quotes[/]
  [bold $warning]"[/] double  [bold $warning]'[/] single  [bold $warning]`[/] backtick"""

        with Dialog(id="text-object-menu", shortcuts=[("Cancel", "esc")]):
            yield Static(content, id="text-object-menu-content")

    def on_key(self, event: Any) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
            return

        # Accept text object chars directly
        char = event.character if hasattr(event, "character") else None
        valid_text_objects = set('wW"\'()[]{}bB<>`')
        if char and char in valid_text_objects:
            self.dismiss(char)
            event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select_w(self) -> None:
        self.dismiss("w")

    def action_select_W(self) -> None:
        self.dismiss("W")

    def action_select_paren(self) -> None:
        self.dismiss("(")

    def action_select_square(self) -> None:
        self.dismiss("[")

    def action_select_curly(self) -> None:
        self.dismiss("{")

    def action_select_angle(self) -> None:
        self.dismiss("<")

    def action_select_dquote(self) -> None:
        self.dismiss('"')

    def action_select_squote(self) -> None:
        self.dismiss("'")

    def action_select_backtick(self) -> None:
        self.dismiss("`")
