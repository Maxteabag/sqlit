"""Theme selection dialog screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ...widgets import Dialog

THEME_LABELS = {
    "sqlit": "Sqlit",
    "sqlit-light": "Sqlit Light",
    "textual-dark": "Textual Dark",
    "textual-light": "Textual Light",
    "nord": "Nord",
    "gruvbox": "Gruvbox",
    "tokyo-night": "Tokyo Night",
    "solarized-light": "Solarized Light",
    "solarized-dark": "Solarized Dark",
    "monokai": "Monokai",
    "flexoki": "Flexoki",
    "catppuccin-latte": "Catppuccin Latte",
    "rose-pine": "Rose Pine",
    "rose-pine-moon": "Rose Pine Moon",
    "rose-pine-dawn": "Rose Pine Dawn",
    "catppuccin-mocha": "Catppuccin Mocha",
    "dracula": "Dracula",
}


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
        self._theme_ids: list[str] = []

    def _build_theme_list(self) -> list[tuple[str, str]]:
        available = set(self.app.available_themes)
        available.discard("textual-ansi")
        ordered: list[tuple[str, str]] = []
        seen: set[str] = set()

        for theme_id, theme_name in THEME_LABELS.items():
            if theme_id in available:
                ordered.append((theme_id, theme_name))
                seen.add(theme_id)

        for theme_id in sorted(available - seen):
            theme_name = " ".join(part.capitalize() for part in theme_id.split("-"))
            ordered.append((theme_id, theme_name))

        return ordered

    def compose(self) -> ComposeResult:
        shortcuts = [("Select", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(id="theme-dialog", title="Select Theme", shortcuts=shortcuts):
            options = []
            themes = self._build_theme_list()
            self._theme_ids = [theme_id for theme_id, _ in themes]
            for theme_id, theme_name in themes:
                prefix = "> " if theme_id == self.current_theme else "  "
                options.append(Option(f"{prefix}{theme_name}", id=theme_id))
            yield OptionList(*options, id="theme-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        option_list.focus()
        # Highlight current theme
        for i, theme_id in enumerate(self._theme_ids):
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
