"""Theme selection dialog screen."""

from __future__ import annotations

from typing import Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from sqlit.shared.ui.protocols import ThemeScreenAppProtocol
from sqlit.shared.ui.widgets import Dialog

# Light themes (listed first)
LIGHT_THEMES = {
    "sqlit-light": "Sqlit Light",
    "textual-light": "Textual Light",
    "solarized-light": "Solarized Light",
    "catppuccin-latte": "Catppuccin Latte",
    "rose-pine-dawn": "Rose Pine Dawn",
}

# Dark themes
DARK_THEMES = {
    "textual-ansi": "Terminal Default",
    "sqlit": "Sqlit",
    "textual-dark": "Textual Dark",
    "nord": "Nord",
    "gruvbox": "Gruvbox",
    "tokyo-night": "Tokyo Night",
    "solarized-dark": "Solarized Dark",
    "monokai": "Monokai",
    "flexoki": "Flexoki",
    "catppuccin-mocha": "Catppuccin Mocha",
    "rose-pine": "Rose Pine",
    "rose-pine-moon": "Rose Pine Moon",
    "dracula": "Dracula",
    "hackerman": "Hackerman",
    "everforest": "Everforest",
    "kanagawa": "Kanagawa",
    "matte-black": "Matte Black",
    "ristretto": "Ristretto",
    "osaka-jade": "Osaka Jade",
}

# Combined theme list for selection and previews.
THEME_LABELS = {**LIGHT_THEMES, **DARK_THEMES}


class CustomThemeScreen(ModalScreen[str | None]):
    """Modal screen for adding a custom theme by name."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Add", show=False),
    ]

    CSS = """
    CustomThemeScreen {
        align: center middle;
        background: transparent;
    }

    #custom-theme-dialog {
        width: 60;
        height: auto;
        max-height: 14;
    }

    #custom-theme-description {
        margin-bottom: 1;
        color: $text-muted;
        height: auto;
    }

    #custom-theme-container {
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

    #custom-theme-container.focused {
        border: solid $primary;
        border-title-color: $primary;
    }

    #custom-theme-container Input {
        border: none;
        height: 1;
        padding: 0;
        background: $surface;
    }

    #custom-theme-container Input:focus {
        border: none;
        background-tint: $foreground 5%;
    }
    """

    def __init__(self, *, initial_name: str = ""):
        super().__init__()
        self.initial_name = initial_name

    def compose(self) -> ComposeResult:
        shortcuts = [("Add", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(id="custom-theme-dialog", title="Add Theme", shortcuts=shortcuts):
            yield Static(
                "Enter theme name (template created in ~/.slit/themes/<name>.json):",
                id="custom-theme-description",
            )
            container = Container(id="custom-theme-container")
            container.border_title = "Theme Name"
            with container:
                yield Input(
                    value=self.initial_name,
                    placeholder="my-theme",
                    id="custom-theme-input",
                )

    def on_mount(self) -> None:
        self.query_one("#custom-theme-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "custom-theme-input":
            value = event.value.strip()
            self.dismiss(value or None)

    def on_descendant_focus(self, event: Any) -> None:
        try:
            container = self.query_one("#custom-theme-container")
            container.add_class("focused")
        except Exception:
            pass

    def on_descendant_blur(self, event: Any) -> None:
        try:
            container = self.query_one("#custom-theme-container")
            container.remove_class("focused")
        except Exception:
            pass

    def action_submit(self) -> None:
        value = self.query_one("#custom-theme-input", Input).value.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)


class ThemeScreen(ModalScreen[str | None]):
    """Modal screen for theme selection with live preview."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "select_option", "Select"),
        Binding("n", "new_theme", "New"),
        Binding("e", "edit_theme", "Edit"),
    ]

    CSS = """
    ThemeScreen {
        align: center middle;
        background: transparent;
    }

    #theme-dialog {
        width: 52;
        overflow-y: hidden;
    }

    #theme-list {
        height: 16;
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
        self._original_theme = current_theme  # Store for restore on cancel

    def _format_theme_label(self, theme_id: str) -> str:
        return THEME_LABELS.get(theme_id) or " ".join(part.capitalize() for part in theme_id.split("-"))

    def _build_theme_list(
        self,
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
        """Build categorized theme lists.

        Returns:
            Tuple of (custom_themes, light_themes, dark_themes) where each is a list of (id, name) tuples.
        """
        available = set(self.app.available_themes)
        custom: list[tuple[str, str]] = []
        light: list[tuple[str, str]] = []
        dark: list[tuple[str, str]] = []
        seen: set[str] = set()

        # Add custom themes first
        try:
            app = cast(ThemeScreenAppProtocol, self.app)
            custom_ids = sorted(app.get_custom_theme_names())
        except Exception:
            custom_ids = []
        for theme_id in custom_ids:
            if theme_id in available:
                custom.append((theme_id, self._format_theme_label(theme_id)))
                seen.add(theme_id)

        # Add light themes first
        for theme_id, theme_name in LIGHT_THEMES.items():
            if theme_id in available:
                light.append((theme_id, theme_name))
                seen.add(theme_id)

        # Add dark themes
        for theme_id, theme_name in DARK_THEMES.items():
            if theme_id in available:
                dark.append((theme_id, theme_name))
                seen.add(theme_id)

        # Add any unknown themes to dark section
        for theme_id in sorted(available - seen):
            dark.append((theme_id, self._format_theme_label(theme_id)))

        return custom, light, dark

    def compose(self) -> ComposeResult:
        shortcuts = [("New", "n"), ("Select", "<enter>")]
        with Dialog(id="theme-dialog", title="Select Theme", shortcuts=shortcuts):
            options: list[Option] = []
            custom_themes, light_themes, dark_themes = self._build_theme_list()

            # Add custom themes section
            if custom_themes:
                options.append(Option("─ Custom ─", disabled=True))
                for theme_id, theme_name in custom_themes:
                    prefix = "> " if theme_id == self.current_theme else "  "
                    options.append(Option(f"{prefix}{theme_name}", id=theme_id))

            # Add light themes section
            if light_themes:
                options.append(Option("─ Light ─", disabled=True))
                for theme_id, theme_name in light_themes:
                    prefix = "> " if theme_id == self.current_theme else "  "
                    options.append(Option(f"{prefix}{theme_name}", id=theme_id))

            # Add dark themes section
            if dark_themes:
                options.append(Option("─ Dark ─", disabled=True))
                for theme_id, theme_name in dark_themes:
                    prefix = "> " if theme_id == self.current_theme else "  "
                    options.append(Option(f"{prefix}{theme_name}", id=theme_id))

            yield OptionList(*options, id="theme-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        option_list.focus()
        # Highlight current theme
        self._highlight_current_theme(option_list)
        self._update_shortcuts()

    def _highlight_current_theme(self, option_list: OptionList) -> None:
        try:
            option_list.highlighted = option_list.get_option_index(self.current_theme)
        except Exception:
            pass

    def _rebuild_options(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        options: list[Option] = []
        custom_themes, light_themes, dark_themes = self._build_theme_list()

        if custom_themes:
            options.append(Option("─ Custom ─", disabled=True))
            for theme_id, theme_name in custom_themes:
                prefix = "> " if theme_id == self.current_theme else "  "
                options.append(Option(f"{prefix}{theme_name}", id=theme_id))

        if light_themes:
            options.append(Option("─ Light ─", disabled=True))
            for theme_id, theme_name in light_themes:
                prefix = "> " if theme_id == self.current_theme else "  "
                options.append(Option(f"{prefix}{theme_name}", id=theme_id))

        if dark_themes:
            options.append(Option("─ Dark ─", disabled=True))
            for theme_id, theme_name in dark_themes:
                prefix = "> " if theme_id == self.current_theme else "  "
                options.append(Option(f"{prefix}{theme_name}", id=theme_id))

        option_list.set_options(options)
        self._highlight_current_theme(option_list)
        self._update_shortcuts()

    def _update_shortcuts(self, theme_id: str | None = None) -> None:
        dialog = self.query_one("#theme-dialog", Dialog)
        if theme_id is None:
            option_list = self.query_one("#theme-list", OptionList)
            if option_list.highlighted is not None:
                try:
                    option = option_list.get_option_at_index(option_list.highlighted)
                    theme_id = option.id
                except Exception:
                    theme_id = None

        show_edit = False
        if theme_id:
            try:
                app = cast(ThemeScreenAppProtocol, self.app)
                show_edit = theme_id in app.get_custom_theme_names()
            except Exception:
                show_edit = False

        shortcuts = [("New", "n"), ("Select", "<enter>")]
        if show_edit:
            shortcuts.insert(1, ("Edit", "e"))

        def format_key(key: str) -> str:
            if key.startswith("<") and key.endswith(">"):
                return key
            return f"<{key}>"

        dialog.border_subtitle = "\u00a0·\u00a0".join(
            f"{action}: [bold]{format_key(key)}[/]" for action, key in shortcuts
        )

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """Apply theme live as user browses options."""
        theme_id = event.option.id
        if theme_id and theme_id in self.app.available_themes:
            try:
                self.app.theme = theme_id
            except Exception:
                pass  # Ignore errors during preview
        self._update_shortcuts(theme_id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_select_option(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is not None:
            option = option_list.get_option_at_index(option_list.highlighted)
            self.dismiss(option.id)

    def action_new_theme(self) -> None:
        def on_theme_name_selected(name: str | None) -> None:
            if not name:
                return
            try:
                app = cast(ThemeScreenAppProtocol, self.app)
                theme_name = app.add_custom_theme(name)
            except Exception as exc:
                from sqlit.shared.ui.screens.error import ErrorScreen

                self.app.push_screen(ErrorScreen("Theme Load Failed", str(exc)))
                return

            self.current_theme = theme_name
            try:
                self.app.theme = theme_name
            except Exception:
                pass
            self._rebuild_options()

        self.app.push_screen(CustomThemeScreen(), on_theme_name_selected)

    def action_edit_theme(self) -> None:
        option_list = self.query_one("#theme-list", OptionList)
        if option_list.highlighted is None:
            return
        try:
            option = option_list.get_option_at_index(option_list.highlighted)
        except Exception:
            return
        theme_id = option.id
        if not theme_id or option.disabled:
            return
        try:
            app = cast(ThemeScreenAppProtocol, self.app)
            app.open_custom_theme_in_editor(theme_id)
        except Exception as exc:
            from sqlit.shared.ui.screens.error import ErrorScreen

            self.app.push_screen(ErrorScreen("Theme Edit Failed", str(exc)))

    def action_cancel(self) -> None:
        # Restore original theme on cancel
        if self._original_theme in self.app.available_themes:
            try:
                self.app.theme = self._original_theme
            except Exception:
                pass
        self.dismiss(None)
