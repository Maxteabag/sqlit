"""Theme selection dialog screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ...widgets import Dialog

THEMES = [
    ("textual-dark", "Textual Dark"),
    ("textual-light", "Textual Light"),
    ("nord", "Nord"),
    ("gruvbox", "Gruvbox"),
    ("tokyo-night", "Tokyo Night"),
    ("solarized-light", "Solarized Light"),
    ("catppuccin-mocha", "Catppuccin Mocha"),
    ("dracula", "Dracula"),
]


class ThemeScreen(ModalScreen[str | None]):
    """Modal screen for theme selection."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select_option", "Select"),
    ]

    CSS = """
    ThemeScreen {
        align: center middle;
        background: transparent;
    }

    #theme-dialog {
        width: 40;
    }

    #theme-list {
        height: auto;
        max-height: 16;
        border: none;
    }

    #theme-list > .option-list--option {
        padding: 0 1;
    }
    """

    def __init__(self, current_theme: str):
        super().__init__()
        self.current_theme = current_theme

    def compose(self) -> ComposeResult:
        shortcuts = [("Select", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(id="theme-dialog", title="Select Theme", shortcuts=shortcuts):
            options = []
            for theme_id, theme_name in THEMES:
                prefix = "> " if theme_id == self.current_theme else "  "
                options.append(Option(f"{prefix}{theme_name}", id=theme_id))
            yield OptionList(*options, id="theme-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        option_list.focus()
        # Highlight current theme
        for i, (theme_id, _) in enumerate(THEMES):
            if theme_id == self.current_theme:
                option_list.highlighted = i
                break

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_select_option(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is not None:
            option = option_list.get_option_at_index(option_list.highlighted)
            self.dismiss(option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
