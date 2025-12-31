"""Theme management utilities for sqlit."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from textual.theme import Theme
from textual.timer import Timer

from sqlit.domains.shell.store.settings import SettingsStore
from sqlit.shared.core.protocols import SettingsStoreProtocol

from .omarchy import (
    DEFAULT_THEME,
    get_current_theme_name,
    get_matching_textual_theme,
    is_omarchy_installed,
)
from .themes import LIGHT_THEME_NAMES, SQLIT_TEXTAREA_THEMES, SQLIT_THEMES

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
