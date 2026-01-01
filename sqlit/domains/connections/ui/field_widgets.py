"""Shared helpers for building connection form fields."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, OptionList, Select, Static
from textual.widgets.option_list import Option

from sqlit.domains.connections.ui.fields import FieldDefinition, FieldGroup, FieldType


class FieldWidgetBuilder:
    """Build field widgets with shared state updates."""

    def __init__(
        self,
        *,
        field_widgets: dict[str, Any],
        field_definitions: dict[str, FieldDefinition],
        get_field_value: Callable[[str], str],
        resolve_select_value: Callable[[FieldDefinition], str],
        get_current_form_values: Callable[[], dict[str, Any]],
        on_browse_file: Callable[[str], None] | None = None,
    ) -> None:
        self._field_widgets = field_widgets
        self._field_definitions = field_definitions
        self._get_field_value = get_field_value
        self._resolve_select_value = resolve_select_value
        self._get_current_form_values = get_current_form_values
        self._on_browse_file = on_browse_file

    def build_field_container(
        self,
        field_def: FieldDefinition,
        *,
        initial_values: dict[str, Any] | None = None,
    ) -> Container:
        field_id = f"field-{field_def.name}"
        container_id = f"container-{field_def.name}"

        initial_visible = True
        if field_def.visible_when:
            values = initial_values if initial_values is not None else self._get_current_form_values()
            initial_visible = field_def.visible_when(values)

        hidden_class = "" if initial_visible else " hidden"

        container = Container(id=container_id, classes=f"field-container{hidden_class}")
        container.border_title = field_def.label

        if field_def.field_type == FieldType.DROPDOWN:
            select = Select(
                options=[(opt.label, opt.value) for opt in field_def.options],
                value=self._resolve_select_value(field_def),
                allow_blank=False,
                compact=True,
                id=field_id,
            )
            self._field_widgets[field_def.name] = select
            self._field_definitions[field_def.name] = field_def
            container.compose_add_child(select)
            container.compose_add_child(Static("", id=f"error-{field_def.name}", classes="error-text hidden"))
        elif field_def.field_type == FieldType.SELECT:
            options = [Option(opt.label, id=opt.value) for opt in field_def.options]
            option_list = OptionList(*options, id=field_id, classes="select-field")
            self._field_widgets[field_def.name] = option_list
            self._field_definitions[field_def.name] = field_def
            container.compose_add_child(option_list)
            container.compose_add_child(Static("", id=f"error-{field_def.name}", classes="error-text hidden"))
        elif field_def.field_type == FieldType.FILE:
            value = self._get_field_value(field_def.name) or field_def.default
            input_widget = Input(
                value=value,
                placeholder=field_def.placeholder,
                id=field_id,
                password=False,
            )
            self._field_widgets[field_def.name] = input_widget
            self._field_definitions[field_def.name] = field_def

            # Create horizontal container with input and browse button
            file_row = Horizontal(classes="file-field-row")
            file_row.compose_add_child(input_widget)
            browse_btn = Button("...", id=f"browse-{field_def.name}", classes="browse-button")
            file_row.compose_add_child(browse_btn)
            container.compose_add_child(file_row)
            container.compose_add_child(Static("", id=f"error-{field_def.name}", classes="error-text hidden"))
        else:
            value = self._get_field_value(field_def.name) or field_def.default
            input_widget = Input(
                value=value,
                placeholder=field_def.placeholder,
                id=field_id,
                password=False,
            )
            self._field_widgets[field_def.name] = input_widget
            self._field_definitions[field_def.name] = field_def
            container.compose_add_child(input_widget)
            container.compose_add_child(Static("", id=f"error-{field_def.name}", classes="error-text hidden"))

        return container

    def build_group_container(
        self,
        group: FieldGroup,
        *,
        initial_values: dict[str, Any] | None = None,
    ) -> Container:
        row_groups: dict[str | None, list[FieldDefinition]] = {}
        for field_def in group.fields:
            row_key = field_def.row_group
            if row_key not in row_groups:
                row_groups[row_key] = []
            row_groups[row_key].append(field_def)

        group_container = Container(classes="field-group")

        for row_key, fields in row_groups.items():
            if row_key is None:
                for field_def in fields:
                    group_container.compose_add_child(
                        self.build_field_container(field_def, initial_values=initial_values)
                    )
            else:
                row = Horizontal(classes="field-row")
                for field_def in fields:
                    width_class = "field-flex" if field_def.width == "flex" else "field-fixed"
                    field_wrapper = Container(classes=width_class)
                    field_wrapper.compose_add_child(
                        self.build_field_container(field_def, initial_values=initial_values)
                    )
                    row.compose_add_child(field_wrapper)
                group_container.compose_add_child(row)

        return group_container
