"""Theme management utilities for sqlit."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Mapping, Protocol

from rich.style import Style
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets.text_area import TextAreaTheme

from sqlit.domains.shell.store.settings import SettingsStore
from sqlit.shared.core.protocols import SettingsStoreProtocol
from .omarchy import (
    DEFAULT_THEME,
    get_current_theme_name,
    get_matching_textual_theme,
    is_omarchy_installed,
)

CUSTOM_THEME_SETTINGS_KEY = "custom_themes"
CUSTOM_THEME_DIR = Path.home() / ".slit" / "themes"
CUSTOM_THEME_FIELDS = {
    "name",
    "primary",
    "secondary",
    "warning",
    "error",
    "success",
    "accent",
    "foreground",
    "background",
    "surface",
    "panel",
    "boost",
    "dark",
    "luminosity_spread",
    "text_alpha",
    "variables",
}

LIGHT_THEME_NAMES = {
    "sqlit-light",
    "textual-light",
    "solarized-light",
    "catppuccin-latte",
    "rose-pine-dawn",
}

SQLIT_THEMES = [
    Theme(
        name="sqlit",
        primary="#97CB93",
        secondary="#6D8DC4",
        accent="#6D8DC4",
        warning="#f59e0b",
        error="#BE728C",
        success="#4ADE80",
        foreground="#a9b1d6",
        background="#1A1B26",
        surface="#24283B",
        panel="#414868",
        dark=True,
        variables={
            "border": "#414868",
            "footer-background": "#24283B",
            "footer-key-foreground": "#7FA1DE",
            "button-color-foreground": "#1A1B26",
            "input-selection-background": "#2a3144 40%",
        },
    ),
    Theme(
        name="sqlit-light",
        primary="#2E7D32",
        secondary="#1565C0",
        accent="#1565C0",
        warning="#F57C00",
        error="#C62828",
        success="#2E7D32",
        foreground="#37474F",
        background="#FAFAFA",
        surface="#FFFFFF",
        panel="#ECEFF1",
        dark=False,
        variables={
            "border": "#B0BEC5",
            "footer-background": "#ECEFF1",
            "footer-key-foreground": "#1565C0",
            "button-color-foreground": "#FFFFFF",
            "input-selection-background": "#1565C0 25%",
        },
    ),
    Theme(
        name="hackerman",
        primary="#00FF21",
        secondary="#149414",
        accent="#00FF21",
        warning="#FFFF33",
        error="#FF0000",
        success="#00FF21",
        foreground="#00FF21",
        background="#0D0D0D",
        surface="#171B1F",
        panel="#1E2428",
        dark=True,
        variables={
            "border": "#0e6b0e",
            "footer-background": "#0D0D0D",
            "footer-key-foreground": "#00FF21",
            "button-color-foreground": "#0D0D0D",
            "input-selection-background": "#149414 40%",
        },
    ),
    Theme(
        name="everforest",
        primary="#A7C080",
        secondary="#83C092",
        accent="#7FBBB3",
        warning="#DBBC7F",
        error="#E67E80",
        success="#A7C080",
        foreground="#D3C6AA",
        background="#232A2E",
        surface="#2D353B",
        panel="#3D484D",
        dark=True,
        variables={
            "border": "#3D484D",
            "footer-background": "#2D353B",
            "footer-key-foreground": "#A7C080",
            "button-color-foreground": "#232A2E",
            "input-selection-background": "#3D484D 40%",
        },
    ),
    Theme(
        name="kanagawa",
        primary="#7E9CD8",
        secondary="#7FB4CA",
        accent="#D27E99",
        warning="#FFA066",
        error="#E46876",
        success="#98BB6C",
        foreground="#DCD7BA",
        background="#1F1F28",
        surface="#16161D",
        panel="#223249",
        dark=True,
        variables={
            "border": "#2D4F67",
            "footer-background": "#16161D",
            "footer-key-foreground": "#7E9CD8",
            "button-color-foreground": "#1F1F28",
            "input-selection-background": "#2D4F67 40%",
        },
    ),
    Theme(
        name="matte-black",
        primary="#FFFFFF",
        secondary="#888888",
        accent="#FFFFFF",
        warning="#FFA500",
        error="#FF4444",
        success="#44FF44",
        foreground="#CCCCCC",
        background="#000000",
        surface="#0A0A0A",
        panel="#1A1A1A",
        dark=True,
        variables={
            "border": "#333333",
            "footer-background": "#0A0A0A",
            "footer-key-foreground": "#FFFFFF",
            "button-color-foreground": "#000000",
            "input-selection-background": "#333333 40%",
        },
    ),
    Theme(
        name="ristretto",
        primary="#F5D1C8",
        secondary="#C9A9A6",
        accent="#F5D1C8",
        warning="#EBD9B4",
        error="#E67E7E",
        success="#A8C4A0",
        foreground="#D5C4A1",
        background="#1C1410",
        surface="#2D2420",
        panel="#3D322C",
        dark=True,
        variables={
            "border": "#4D3C36",
            "footer-background": "#2D2420",
            "footer-key-foreground": "#F5D1C8",
            "button-color-foreground": "#1C1410",
            "input-selection-background": "#4D3C36 40%",
        },
    ),
    Theme(
        name="osaka-jade",
        primary="#7DCFB6",
        secondary="#5BA492",
        accent="#7DCFB6",
        warning="#E0C380",
        error="#D87A7A",
        success="#7DCFB6",
        foreground="#B9D7D0",
        background="#0D1512",
        surface="#1A2420",
        panel="#2D4038",
        dark=True,
        variables={
            "border": "#2D4038",
            "footer-background": "#1A2420",
            "footer-key-foreground": "#7DCFB6",
            "button-color-foreground": "#0D1512",
            "input-selection-background": "#253530 40%",
        },
    ),
    # Terminal Default - uses ANSI colors from terminal
    Theme(
        name="textual-ansi",
        primary="#FFFFFF",
        secondary="ansi_blue",
        accent="ansi_blue",
        warning="ansi_yellow",
        error="ansi_red",
        success="ansi_green",
        foreground="ansi_default",
        background="ansi_default",
        surface="ansi_default",
        panel="ansi_default",
        dark=True,
        variables={
            "border": "#555555",
        },
    ),
    # Built-in theme overrides (only adding border variable for contrast)
    Theme(
        name="dracula",
        primary="#BD93F9",
        secondary="#FF79C6",
        accent="#BD93F9",
        warning="#F1FA8C",
        error="#FF5555",
        success="#50FA7B",
        foreground="#F8F8F2",
        background="#282A36",
        surface="#2B2E3B",
        panel="#313442",
        dark=True,
        variables={
            "border": "#44475A",
            "button-color-foreground": "#282A36",
        },
    ),
    Theme(
        name="flexoki",
        primary="#205EA6",
        secondary="#DA702C",
        accent="#205EA6",
        warning="#D0A215",
        error="#D14D41",
        success="#879A39",
        foreground="#CECDC3",
        background="#100F0F",
        surface="#1C1B1A",
        panel="#282726",
        dark=True,
        variables={
            "border": "#282726",
            "input-cursor-foreground": "#5E409D",
            "input-cursor-background": "#FFFCF0",
            "input-selection-background": "#6F6E69 35%",
            "button-color-foreground": "#FFFCF0",
        },
    ),
    Theme(
        name="monokai",
        primary="#AE81FF",
        secondary="#66D9EF",
        accent="#AE81FF",
        warning="#E6DB74",
        error="#F92672",
        success="#A6E22E",
        foreground="#F8F8F2",
        background="#272822",
        surface="#2e2e2e",
        panel="#3E3D32",
        dark=True,
        variables={
            "border": "#3E3D32",
            "foreground-muted": "#797979",
            "input-selection-background": "#575b6190",
            "button-color-foreground": "#272822",
        },
    ),
    Theme(
        name="solarized-dark",
        primary="#268bd2",
        secondary="#2AA198",
        accent="#268bd2",
        warning="#B58900",
        error="#DC322F",
        success="#859900",
        foreground="#839496",
        background="#002b36",
        surface="#073642",
        panel="#073642",
        dark=True,
        variables={
            "border": "#586e75",
            "border-blurred": "#2f4a52",
            "button-color-foreground": "#fdf6e3",
            "footer-background": "#268bd2",
            "footer-key-foreground": "#fdf6e3",
            "footer-description-foreground": "#fdf6e3",
            "input-selection-background": "#073642",
        },
    ),
    Theme(
        name="tokyo-night",
        primary="#BB9AF7",
        secondary="#7AA2F7",
        accent="#BB9AF7",
        warning="#E0AF68",
        error="#F7768E",
        success="#9ECE6A",
        foreground="#C0CAF5",
        background="#1A1B26",
        surface="#24283B",
        panel="#414868",
        dark=True,
        variables={
            "border": "#414868",
            "button-color-foreground": "#24283B",
        },
    ),
    Theme(
        name="gruvbox",
        primary="#85A598",
        secondary="#FABD2F",
        accent="#85A598",
        warning="#FE8019",
        error="#FB4934",
        success="#B8BB26",
        foreground="#EBDBB2",
        background="#282828",
        surface="#3c3836",
        panel="#504945",
        dark=True,
        variables={
            "border": "#504945",
            "block-cursor-foreground": "#fbf1c7",
            "input-selection-background": "#689d6a40",
            "button-color-foreground": "#282828",
        },
    ),
    Theme(
        name="nord",
        primary="#88C0D0",
        secondary="#81A1C1",
        accent="#88C0D0",
        warning="#EBCB8B",
        error="#BF616A",
        success="#A3BE8C",
        foreground="#ECEFF4",
        background="#2E3440",
        surface="#3B4252",
        panel="#434C5E",
        dark=True,
        variables={
            "border": "#434C5E",
            "block-cursor-background": "#88C0D0",
            "block-cursor-foreground": "#2E3440",
            "block-cursor-text-style": "none",
            "footer-key-foreground": "#88C0D0",
            "input-selection-background": "#81a1c1 35%",
            "button-color-foreground": "#2E3440",
            "button-focus-text-style": "reverse",
        },
    ),
    Theme(
        name="textual-dark",
        primary="#0178D4",
        secondary="#004578",
        accent="#0178D4",
        warning="#ffa62b",
        error="#ba3c5b",
        success="#4EBF71",
        foreground="#e0e0e0",
        background="#121212",
        surface="#1e1e1e",
        panel="#2d2d2d",
        dark=True,
        variables={
            "border": "#2d2d2d",
        },
    ),
]

SQLIT_TEXTAREA_THEMES: dict[str, TextAreaTheme] = {
    "sqlit-light": TextAreaTheme(
        name="sqlit-light",
        syntax_styles={
            "keyword": Style(color="#D73A49", bold=True),
            "keyword.operator": Style(color="#D73A49"),
            "string": Style(color="#032F62"),
            "string.special": Style(color="#032F62"),
            "comment": Style(color="#6A737D", italic=True),
            "number": Style(color="#005CC5"),
            "float": Style(color="#005CC5"),
            "operator": Style(color="#D73A49"),
            "punctuation": Style(color="#24292E"),
            "punctuation.bracket": Style(color="#24292E"),
            "punctuation.delimiter": Style(color="#24292E"),
            "function": Style(color="#6F42C1"),
            "function.call": Style(color="#6F42C1"),
            "type": Style(color="#005CC5"),
            "variable": Style(color="#24292E"),
            "constant": Style(color="#005CC5"),
            "identifier": Style(color="#24292E"),
        },
    ),
    "hackerman": TextAreaTheme(
        name="hackerman",
        syntax_styles={
            "keyword": Style(color="#00FF21", bold=True),
            "keyword.operator": Style(color="#00FF21"),
            "string": Style(color="#7CFC00"),
            "string.special": Style(color="#7CFC00"),
            "comment": Style(color="#228B22", italic=True),
            "number": Style(color="#00FA9A"),
            "float": Style(color="#00FA9A"),
            "operator": Style(color="#32CD32"),
            "punctuation": Style(color="#149414"),
            "punctuation.bracket": Style(color="#149414"),
            "punctuation.delimiter": Style(color="#149414"),
            "function": Style(color="#39FF14"),
            "function.call": Style(color="#39FF14"),
            "type": Style(color="#00FF7F"),
            "variable": Style(color="#90EE90"),
            "constant": Style(color="#00FA9A"),
            "identifier": Style(color="#00FF21"),
        },
    ),
}


class ThemeAppProtocol(Protocol):
    theme: str

    @property
    def available_themes(self) -> Mapping[str, Theme]: ...

    @property
    def query_input(self) -> Any: ...

    def register_theme(self, theme: Theme) -> None: ...

    def _apply_theme_safe(self, theme_name: str) -> None: ...

    def set_interval(
        self,
        interval: float,
        callback: Any,
        *,
        name: str | None = None,
        repeat: int = 0,
        pause: bool = False,
    ) -> Any: ...

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None: ...

    def suspend(self) -> AbstractContextManager[None]: ...


class ThemeManager:
    """Centralized theme handling for the app."""

    def __init__(self, app: ThemeAppProtocol, settings_store: SettingsStoreProtocol | None = None) -> None:
        self._app = app
        self._settings_store = settings_store or SettingsStore.get_instance()
        self._custom_theme_names: set[str] = set()
        self._custom_theme_paths: dict[str, Path] = {}
        self._light_theme_names: set[str] = set(LIGHT_THEME_NAMES)
        self._omarchy_theme_watcher: Timer | None = None
        self._omarchy_last_theme_name: str | None = None

    def register_builtin_themes(self) -> None:
        for theme in SQLIT_THEMES:
            self._app.register_theme(theme)

    def register_textarea_themes(self) -> None:
        for textarea_theme in SQLIT_TEXTAREA_THEMES.values():
            self._app.query_input.register_theme(textarea_theme)

    def initialize(self) -> dict:
        settings = self._settings_store.load_all()
        self.load_custom_themes(settings)
        self._init_omarchy_theme(settings)
        self.apply_textarea_theme(self._app.theme)
        return settings

    def on_theme_changed(self, new_theme: str) -> None:
        settings = self._settings_store.load_all()
        settings["theme"] = new_theme
        self._settings_store.save_all(settings)
        self.apply_textarea_theme(new_theme)

    def apply_omarchy_theme(self) -> None:
        matched_theme = get_matching_textual_theme(set(self._app.available_themes))
        self._app._apply_theme_safe(matched_theme)

    def on_omarchy_theme_change(self) -> None:
        current_name = get_current_theme_name()
        if current_name is None:
            return

        if current_name != self._omarchy_last_theme_name:
            self._omarchy_last_theme_name = current_name
            self.apply_omarchy_theme()

    def apply_textarea_theme(self, theme_name: str) -> None:
        try:
            if theme_name in SQLIT_TEXTAREA_THEMES:
                self._app.query_input.theme = theme_name
            elif theme_name in self._light_theme_names:
                self._app.query_input.theme = "sqlit-light"
            else:
                self._app.query_input.theme = "css"
        except Exception:
            pass

    def get_custom_theme_names(self) -> set[str]:
        return set(self._custom_theme_names)

    def add_custom_theme(self, theme_name: str) -> str:
        path, expected_name = self._resolve_custom_theme_entry(theme_name)
        CUSTOM_THEME_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self._write_custom_theme_template(path, expected_name or path.stem)
            self._app.notify(
                f"Created theme template: {path}",
                title="Theme Template",
                severity="information",
            )
        path = path.resolve()

        theme_name = self._register_custom_theme_path(path, expected_name)
        settings = self._settings_store.load_all()
        theme_paths = settings.get(CUSTOM_THEME_SETTINGS_KEY, [])
        if not isinstance(theme_paths, list):
            theme_paths = []
        entry_value = theme_name if expected_name else str(path)
        theme_paths = self._dedupe_custom_theme_entries(theme_paths, theme_name)
        if entry_value not in theme_paths:
            theme_paths.append(entry_value)
        settings[CUSTOM_THEME_SETTINGS_KEY] = theme_paths
        self._settings_store.save_all(settings)
        return theme_name

    def open_custom_theme_in_editor(self, theme_name: str) -> None:
        path = self.get_custom_theme_path(theme_name)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor:
            command = shlex.split(editor) + [str(path)]
            try:
                with self._app.suspend():
                    subprocess.run(command, check=False)
            except Exception as exc:
                raise ValueError(f"Failed to open editor '{editor}': {exc}") from exc
            self._reload_custom_theme(path, theme_name)
            return

        if sys.platform.startswith("darwin"):
            command = ["open", str(path)]
        elif os.name == "nt":
            command = ["cmd", "/c", "start", "", str(path)]
        else:
            command = ["xdg-open", str(path)]

        try:
            subprocess.Popen(command)
        except Exception as exc:
            raise ValueError(f"Failed to open {path}: {exc}") from exc
        self._app.notify(
            "Theme file opened. Reselect the theme after saving to reload.",
            title="Theme Edit",
            severity="information",
        )

    def get_custom_theme_path(self, theme_name: str) -> Path:
        path = self._custom_theme_paths.get(theme_name)
        if path is None:
            raise ValueError(f'"{theme_name}" is not a custom theme.')
        return path

    def load_custom_themes(self, settings: dict) -> None:
        theme_paths = settings.get(CUSTOM_THEME_SETTINGS_KEY, [])
        if not isinstance(theme_paths, list):
            return
        for theme_path in theme_paths:
            if not isinstance(theme_path, str) or not theme_path.strip():
                continue
            try:
                path, expected_name = self._resolve_custom_theme_entry(theme_path)
                self._register_custom_theme_path(path, expected_name)
            except Exception as exc:
                print(
                    f"[sqlit] Failed to load custom theme {theme_path}: {exc}",
                    file=sys.stderr,
                )

    def _register_custom_theme_path(self, path: Path, expected_name: str | None = None) -> str:
        path = path.expanduser()
        if not path.exists():
            raise ValueError(f"Theme file not found: {path}")
        theme = self._load_custom_theme(path, expected_name)
        self._app.register_theme(theme)
        self._custom_theme_names.add(theme.name)
        self._custom_theme_paths[theme.name] = path.resolve()
        if not theme.dark:
            self._light_theme_names.add(theme.name)
        return theme.name

    def _init_omarchy_theme(self, settings: dict) -> None:
        saved_theme = settings.get("theme")
        if not is_omarchy_installed():
            self._app._apply_theme_safe(saved_theme or DEFAULT_THEME)
            return

        matched_theme = get_matching_textual_theme(set(self._app.available_themes))
        self._omarchy_last_theme_name = get_current_theme_name()
        if (
            isinstance(saved_theme, str)
            and saved_theme in self._app.available_themes
            and saved_theme != matched_theme
        ):
            self._app._apply_theme_safe(saved_theme)
            return

        self._app._apply_theme_safe(matched_theme)
        self._start_omarchy_watcher()

    def _start_omarchy_watcher(self) -> None:
        if self._omarchy_theme_watcher is not None:
            return
        self._omarchy_theme_watcher = self._app.set_interval(2.0, self.on_omarchy_theme_change)

    def _stop_omarchy_watcher(self) -> None:
        if self._omarchy_theme_watcher is not None:
            self._omarchy_theme_watcher.stop()
            self._omarchy_theme_watcher = None

    def _reload_custom_theme(self, path: Path, theme_name: str) -> None:
        expected_name = theme_name if theme_name in self._custom_theme_names else None
        theme = self._load_custom_theme(path, expected_name)
        self._app.register_theme(theme)
        self._custom_theme_names.add(theme.name)
        self._custom_theme_paths[theme.name] = path.resolve()
        if not theme.dark:
            self._light_theme_names.add(theme.name)
        elif theme.name in self._light_theme_names:
            self._light_theme_names.remove(theme.name)

        if self._app.theme == theme.name:
            self._app.theme = theme.name
        else:
            self.apply_textarea_theme(self._app.theme)

    def _load_custom_theme(self, path: Path, expected_name: str | None) -> Theme:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to read theme JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Theme file must contain a JSON object.")

        theme_data = payload.get("theme", payload)
        if not isinstance(theme_data, dict):
            raise ValueError('Theme file "theme" must be a JSON object.')

        theme_kwargs = {key: theme_data[key] for key in CUSTOM_THEME_FIELDS if key in theme_data}
        name = theme_kwargs.get("name")
        primary = theme_kwargs.get("primary")

        if not isinstance(name, str) or not name.strip():
            raise ValueError('Theme JSON must include a non-empty "name".')
        if not isinstance(primary, str) or not primary.strip():
            raise ValueError('Theme JSON must include a non-empty "primary" color.')

        theme_kwargs["name"] = name.strip()
        if "variables" in theme_kwargs and not isinstance(theme_kwargs["variables"], dict):
            raise ValueError('Theme "variables" must be a JSON object.')
        if expected_name and theme_kwargs["name"] != expected_name:
            raise ValueError(
                f'Theme name "{theme_kwargs["name"]}" does not match file name "{expected_name}".'
            )

        try:
            return Theme(**theme_kwargs)
        except Exception as exc:
            raise ValueError(f"Failed to create theme: {exc}") from exc

    def _resolve_custom_theme_entry(self, theme_entry: str) -> tuple[Path, str | None]:
        entry = theme_entry.strip()
        if not entry:
            raise ValueError("Theme name is required.")

        if entry.startswith(("~", "/")) or Path(entry).is_absolute():
            return Path(entry).expanduser(), None

        name = Path(entry).stem
        file_name = f"{name}.json"
        return CUSTOM_THEME_DIR / file_name, name

    def _write_custom_theme_template(self, path: Path, theme_name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        template = {
            "_note": "Customize colors in the theme object then reselect the theme.",
            "theme": {
                "name": theme_name,
                "dark": True,
                "primary": "#3b82f6",
                "secondary": "#22c55e",
                "accent": "#38bdf8",
                "warning": "#f59e0b",
                "error": "#ef4444",
                "success": "#22c55e",
                "foreground": "#e2e8f0",
                "background": "#0f172a",
                "surface": "#111827",
                "panel": "#1f2937",
                "variables": {
                    "border": "#334155",
                    "input-selection-background": "#3b82f6 25%",
                },
            },
        }
        path.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _dedupe_custom_theme_entries(entries: list, theme_name: str) -> list[str]:
        cleaned: list[str] = []
        for entry in entries:
            if not isinstance(entry, str):
                continue
            value = entry.strip()
            if not value:
                continue
            entry_name = None
            if not value.startswith(("~", "/")) and not Path(value).is_absolute():
                entry_name = Path(value).stem
            if entry_name == theme_name:
                continue
            if value not in cleaned:
                cleaned.append(value)
        return cleaned
