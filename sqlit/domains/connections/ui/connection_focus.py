"""Focus management for the connection configuration screen."""

from __future__ import annotations

from typing import Any

from textual.containers import Container
from textual.widgets import Button, Input, OptionList, Select, TabbedContent

from sqlit.domains.connections.ui.connection_form import ConnectionFormController
from sqlit.domains.connections.ui.fields import FieldDefinition


class ConnectionFocusController:
    """Manage focus traversal and field focus behavior."""

    def __init__(self, *, screen: Any, form: ConnectionFormController) -> None:
        self._screen = screen
        self._form = form

    def _get_active_tab(self) -> str:
        try:
            tabs_widget = self._screen.query_one("#connection-tabs", TabbedContent)
            return str(tabs_widget.active)
        except Exception:
            return "tab-general"

    def _get_focusable_fields(self) -> list[Any]:
        """Tab bar is intentionally excluded from focusable fields.
        Users can switch tabs by clicking or using keyboard shortcuts,
        but Tab key should cycle through form fields only.
        """
        active_tab = self._get_active_tab()
        fields: list[Any] = []

        def collect_tab_fields(tab_name: str) -> list[Any]:
            collected: list[Any] = []
            for name, field_def in self._form.field_definitions.items():
                if field_def.tab != tab_name:
                    continue
                try:
                    container = self._screen.query_one(f"#container-{name}", Container)
                    if "hidden" in container.classes:
                        continue
                    field_widget = self._screen.query_one(f"#field-{name}")
                    collected.append(field_widget)
                    if self._form.is_file_field(name):
                        try:
                            browse_btn = self._screen.query_one(f"#browse-{name}", Button)
                            collected.append(browse_btn)
                        except Exception:
                            pass
                except Exception:
                    pass
            return collected

        if active_tab == "tab-general":
            fields.extend(
                [
                    self._screen.query_one("#conn-name", Input),
                    self._screen.query_one("#dbtype-select", Select),
                ]
            )
            fields.extend(collect_tab_fields("general"))
            return fields

        if active_tab == "tab-ssh":
            return collect_tab_fields("ssh")

        if active_tab == "tab-tls":
            return collect_tab_fields("tls")

        return fields

    def focus_first_required(self) -> None:
        values = self._form.get_current_form_values()
        ordered_fields = list(self._form.field_definitions.keys())

        def is_visible(field_def: FieldDefinition) -> bool:
            if field_def.visible_when and not bool(field_def.visible_when(values)):
                return False
            return True

        def is_missing(widget: Any) -> bool:
            if isinstance(widget, Input):
                return not widget.value.strip()
            if isinstance(widget, OptionList):
                return widget.highlighted is None
            if isinstance(widget, Select):
                return widget.value in (None, "")
            return False

        for field_name in ordered_fields:
            field_def = self._form.field_definitions.get(field_name)
            if not field_def or not field_def.required:
                continue
            if not is_visible(field_def):
                continue
            widget = self._form.field_widgets.get(field_name)
            if widget is None:
                continue
            if is_missing(widget):
                widget.focus()
                return

        for field_name in ordered_fields:
            field_def = self._form.field_definitions.get(field_name)
            if not field_def or not is_visible(field_def):
                continue
            widget = self._form.field_widgets.get(field_name)
            if widget is None:
                continue
            widget.focus()
            return

    def focus_first_visible_field(self) -> None:
        values = self._form.get_current_form_values()
        ordered_fields = list(self._form.field_definitions.keys())

        for field_name in ordered_fields:
            field_def = self._form.field_definitions.get(field_name)
            if not field_def:
                continue
            if field_def.visible_when and not bool(field_def.visible_when(values)):
                continue
            widget = self._form.field_widgets.get(field_name)
            if widget is None:
                continue
            widget.focus()
            return

    def focus_next_field(self) -> None:
        from textual.widgets import Tabs

        fields = self._get_focusable_fields()
        focused = self._screen.focused

        if isinstance(focused, Tabs):
            if fields:
                fields[0].focus()
            return

        if focused in fields:
            idx = fields.index(focused)
            next_idx = (idx + 1) % len(fields)
            fields[next_idx].focus()
        elif fields:
            fields[0].focus()

    def focus_prev_field(self) -> None:
        from textual.widgets import Tabs

        fields = self._get_focusable_fields()
        focused = self._screen.focused

        if isinstance(focused, Tabs):
            return

        if focused in fields:
            idx = fields.index(focused)
            if idx == 0:
                try:
                    tabs_widget = self._screen.query_one("#connection-tabs", TabbedContent)
                    tab_bar = tabs_widget.query_one(Tabs)
                    tab_bar.focus()
                except Exception:
                    pass
            else:
                fields[idx - 1].focus()
        elif fields:
            fields[-1].focus()

    def focus_tab_content(self) -> None:
        from textual.widgets import Tabs

        try:
            tabs_widget = self._screen.query_one("#connection-tabs", TabbedContent)
            tab_bar = tabs_widget.query_one(Tabs)
            if self._screen.focused != tab_bar:
                return
        except Exception:
            return

        active_tab = tabs_widget.active

        if active_tab == "tab-general":
            self._screen.query_one("#conn-name", Input).focus()
        elif active_tab in {"tab-ssh", "tab-tls"}:
            fields = self._get_focusable_fields()
            if fields:
                fields[0].focus()
