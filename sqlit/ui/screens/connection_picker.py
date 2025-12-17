"""Connection picker screen with fuzzy search."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ...utils import fuzzy_match, highlight_matches
from ...widgets import Dialog


class ConnectionPickerScreen(ModalScreen):
    """Modal screen for selecting a connection with fuzzy search."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("backspace", "backspace", "Backspace", show=False),
    ]

    CSS = """
    ConnectionPickerScreen {
        align: center middle;
        background: transparent;
    }

    #picker-dialog {
        width: 60;
        max-width: 80%;
        height: auto;
        max-height: 70%;
    }

    #picker-list {
        height: auto;
        max-height: 20;
        background: $surface;
        border: none;
        padding: 0;
    }

    #picker-list > .option-list--option {
        padding: 0 1;
    }

    #picker-empty {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }
    """

    def __init__(self, connections: list):
        super().__init__()
        self.connections = connections
        self.search_text = ""

    def compose(self) -> ComposeResult:
        from textual.widgets import Static

        shortcuts = [("Select", "<enter>"), ("Close", "<esc>")]

        with Dialog(id="picker-dialog", title="Connect", shortcuts=shortcuts):
            if self.connections:
                options = self._build_options("")
                yield OptionList(*options, id="picker-list")
            else:
                yield Static("No connections configured", id="picker-empty")

    def _build_options(self, pattern: str) -> list[Option]:
        """Build option list with fuzzy highlighting."""
        options = []
        for conn in self.connections:
            matches, indices = fuzzy_match(pattern, conn.name)
            if matches or not pattern:
                display = highlight_matches(conn.name, indices)
                db_type = conn.db_type.upper() if conn.db_type else "DB"
                info = conn.get_display_info()
                options.append(Option(f"{display} [{db_type}] [dim]({info})[/]", id=conn.name))
        return options

    def on_mount(self) -> None:
        # Don't focus OptionList so screen receives key events for filtering
        pass

    def on_key(self, event: Key) -> None:
        """Handle key presses for fuzzy search."""
        if event.character and event.character.isprintable():
            self.search_text += event.character
            self._update_list()
            event.stop()

    def action_backspace(self) -> None:
        """Remove last character from search."""
        if self.search_text:
            self.search_text = self.search_text[:-1]
            self._update_list()

    def _update_list(self) -> None:
        """Update the option list based on search."""
        try:
            option_list = self.query_one("#picker-list", OptionList)
        except Exception:
            return

        option_list.clear_options()
        options = self._build_options(self.search_text)

        for opt in options:
            option_list.add_option(opt)

        if options:
            option_list.highlighted = 0

    def action_move_up(self) -> None:
        try:
            option_list = self.query_one("#picker-list", OptionList)
            if option_list.highlighted is not None and option_list.highlighted > 0:
                option_list.highlighted -= 1
        except Exception:
            pass

    def action_move_down(self) -> None:
        try:
            option_list = self.query_one("#picker-list", OptionList)
            if option_list.highlighted is not None:
                option_list.highlighted += 1
        except Exception:
            pass

    def action_select(self) -> None:
        if not self.connections:
            self.dismiss(None)
            return

        try:
            option_list = self.query_one("#picker-list", OptionList)
            highlighted = option_list.highlighted
            if highlighted is not None:
                option = option_list.get_option_at_index(highlighted)
                if option:
                    self.dismiss(option.id)
                    return
        except Exception:
            pass

        self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "picker-list":
            if event.option:
                self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
