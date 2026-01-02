"""Protocols for screen-specific app interactions."""

from __future__ import annotations

from typing import Protocol

from sqlit.shared.ui.protocols.core import TextualAppProtocol


class ThemeScreenAppProtocol(TextualAppProtocol, Protocol):
    available_themes: set[str]

    def get_custom_theme_names(self) -> set[str]:
        ...

    def add_custom_theme(self, theme_name: str) -> str:
        ...

    def open_custom_theme_in_editor(self, theme_name: str) -> None:
        ...
