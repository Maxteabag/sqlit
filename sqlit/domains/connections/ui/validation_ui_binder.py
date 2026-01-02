"""Validation UI helpers for the connection configuration screen."""

from __future__ import annotations

from typing import Any

from textual.containers import Container
from textual.widgets import Static, TabbedContent, TabPane

from sqlit.domains.connections.ui.fields import FieldDefinition
from sqlit.domains.connections.ui.validation import ValidationState


class ConnectionValidationBinder:
    """Apply validation errors to the connection screen UI."""

    def __init__(self, *, screen: Any) -> None:
        self._screen = screen

    def _clear_field_error(self, name: str) -> None:
        try:
            container = self._screen.query_one(f"#container-{name}", Container)
            container.remove_class("invalid")
        except Exception:
            pass
        try:
            error = self._screen.query_one(f"#error-{name}", Static)
            error.update("")
            error.add_class("hidden")
        except Exception:
            pass

    def _set_field_error(self, name: str, message: str) -> None:
        try:
            container = self._screen.query_one(f"#container-{name}", Container)
            container.add_class("invalid")
        except Exception:
            pass
        try:
            error = self._screen.query_one(f"#error-{name}", Static)

            error.update("" if message == "Required." else message)
            if message == "Required.":
                error.add_class("hidden")
            else:
                error.remove_class("hidden")
        except Exception:
            pass

    def _set_tab_error(self, tab_id: str) -> None:
        try:
            tabs_widget = self._screen.query_one("#connection-tabs", TabbedContent)
            pane = self._screen.query_one(f"#{tab_id}", TabPane)
            tab = tabs_widget.get_tab(pane)
            tab.add_class("has-error")
        except Exception:
            pass

    def _clear_tab_errors(self) -> None:
        try:
            tabs_widget = self._screen.query_one("#connection-tabs", TabbedContent)
            for tab_id in ["tab-general", "tab-ssh"]:
                try:
                    pane = self._screen.query_one(f"#{tab_id}", TabPane)
                    tab = tabs_widget.get_tab(pane)
                    tab.remove_class("has-error")
                except Exception:
                    pass
        except Exception:
            pass

    def apply_validation(self, *, state: ValidationState, field_definitions: dict[str, FieldDefinition]) -> None:
        self._clear_tab_errors()
        state.tab_errors.clear()

        self._clear_field_error("name")
        for field_name in field_definitions:
            self._clear_field_error(field_name)
        for ssh_field in ["ssh_host", "ssh_username", "ssh_key_path"]:
            self._clear_field_error(ssh_field)

        for field_name, message in state.errors.items():
            self._set_field_error(field_name, message)

            if field_name == "name":
                self._set_tab_error("tab-general")
                state.add_tab_error("tab-general")
            elif field_name.startswith("ssh_"):
                self._set_tab_error("tab-ssh")
                state.add_tab_error("tab-ssh")
            elif field_name in field_definitions:
                self._set_tab_error("tab-general")
                state.add_tab_error("tab-general")
            else:
                self._set_tab_error("tab-general")
                state.add_tab_error("tab-general")

    def clear_name_error(self) -> None:
        self._clear_field_error("name")

    def set_name_error(self, message: str) -> None:
        self._set_field_error("name", message)
