"""Form state and helpers for the connection configuration screen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Input, OptionList, Select, TabbedContent

from sqlit.domains.connections.domain.config import DATABASE_TYPE_DISPLAY_ORDER, ConnectionConfig, DatabaseType
from sqlit.domains.connections.providers.catalog import get_provider_schema
from sqlit.domains.connections.ui.field_widgets import FieldWidgetBuilder
from sqlit.domains.connections.ui.fields import FieldDefinition, FieldGroup, FieldType, schema_to_field_definitions


class ConnectionFormController:
    """Manage dynamic form fields and values for the connection screen."""

    def __init__(
        self,
        *,
        config: ConnectionConfig | None,
        prefill_values: dict[str, Any] | None,
        on_browse_file: Callable[[str], None],
    ) -> None:
        self._config = config
        self._prefill_values = prefill_values or {}
        self._on_browse_file = on_browse_file
        self.field_widgets: dict[str, Widget] = {}
        self.field_definitions: dict[str, FieldDefinition] = {}
        self.current_db_type: DatabaseType = self._get_initial_db_type()

    def _get_initial_db_type(self) -> DatabaseType:
        prefill_db_type = self._prefill_values.get("db_type")
        if isinstance(prefill_db_type, str) and prefill_db_type:
            try:
                return DatabaseType(prefill_db_type)
            except Exception:
                pass
        if self._config:
            return self._config.get_db_type()
        return DATABASE_TYPE_DISPLAY_ORDER[0]

    def get_field_groups_for_type(self, db_type: DatabaseType, tab: str | None = None) -> list[FieldGroup]:
        schema = get_provider_schema(db_type.value)
        definitions = schema_to_field_definitions(schema)
        if tab:
            definitions = [d for d in definitions if d.tab == tab]
        return [FieldGroup(name="connection", fields=definitions)]

    def get_field_value(self, field_name: str) -> str:
        if self._config:
            return str(self._config.get_field_value(field_name, ""))
        return ""

    def _select_value_in_options(self, field_def: FieldDefinition, value: str | None) -> bool:
        return any(opt.value == value for opt in field_def.options)

    def resolve_select_value(self, field_def: FieldDefinition) -> str:
        value = self.get_field_value(field_def.name)
        if self._select_value_in_options(field_def, value):
            return value
        if self._select_value_in_options(field_def, field_def.default):
            return field_def.default
        if field_def.options:
            return field_def.options[0].value
        return ""

    def get_current_form_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, widget in self.field_widgets.items():
            if isinstance(widget, Input):
                values[name] = widget.value
            elif isinstance(widget, OptionList):
                field_def = self.field_definitions.get(name)
                if field_def and field_def.options and widget.highlighted is not None:
                    idx = widget.highlighted
                    if idx < len(field_def.options):
                        values[name] = field_def.options[idx].value
                    else:
                        values[name] = field_def.default
                else:
                    values[name] = field_def.default if field_def else ""
            elif isinstance(widget, Select):
                values[name] = str(widget.value) if widget.value is not None else ""
        return values

    def _get_field_builder(self) -> FieldWidgetBuilder:
        return FieldWidgetBuilder(
            field_widgets=self.field_widgets,
            field_definitions=self.field_definitions,
            get_field_value=self.get_field_value,
            resolve_select_value=self.resolve_select_value,
            get_current_form_values=self.get_current_form_values,
            on_browse_file=self._on_browse_file,
        )

    def get_initial_visibility_values(self) -> dict[str, Any]:
        initial_values: dict[str, Any] = {}
        if self._config:
            for attr in [
                "auth_type",
                "driver",
                "server",
                "port",
                "database",
                "username",
                "password",
                "file_path",
                "tls_mode",
            ]:
                initial_values[attr] = self._config.get_field_value(attr, "")
        return initial_values

    def create_field_group(
        self,
        group: FieldGroup,
        *,
        initial_values: dict[str, Any] | None = None,
    ) -> Container:
        builder = self._get_field_builder()
        return builder.build_group_container(group, initial_values=initial_values)

    def create_field_group_widgets(self, group: FieldGroup) -> list[Widget]:
        builder = self._get_field_builder()
        return [builder.build_group_container(group)]

    def set_initial_select_values(self) -> None:
        for name, widget in self.field_widgets.items():
            if isinstance(widget, OptionList):
                field_def = self.field_definitions.get(name)
                if not field_def:
                    continue

                value = self.resolve_select_value(field_def)

                for i, opt in enumerate(field_def.options):
                    if opt.value == value:
                        widget.highlighted = i
                        break

    def rebuild_dynamic_fields(
        self,
        db_type: DatabaseType,
        *,
        general_container: Container,
        advanced_container: Container,
        ssh_container: Container,
    ) -> None:
        self.current_db_type = db_type
        self.field_widgets.clear()
        self.field_definitions.clear()

        general_container.remove_children()
        advanced_container.remove_children()
        ssh_container.remove_children()

        field_groups = self.get_field_groups_for_type(db_type, tab="general")
        for group in field_groups:
            for widget in self.create_field_group_widgets(group):
                general_container.mount(widget)

        advanced_groups = self.get_field_groups_for_type(db_type, tab="tls")
        for group in advanced_groups:
            for widget in self.create_field_group_widgets(group):
                advanced_container.mount(widget)

        ssh_groups = self.get_field_groups_for_type(db_type, tab="ssh")
        for group in ssh_groups:
            for widget in self.create_field_group_widgets(group):
                ssh_container.mount(widget)

    def apply_prefill_values(
        self,
        *,
        name_input: Input | None,
        tabs: TabbedContent | None,
    ) -> None:
        if not self._prefill_values:
            return

        values = self._prefill_values.get("values") if "values" in self._prefill_values else self._prefill_values
        if not isinstance(values, dict):
            return

        name_value = values.get("name")
        if isinstance(name_value, str) and name_input is not None:
            name_input.value = name_value

        for field_name, widget in self.field_widgets.items():
            value = values.get(field_name)
            if value is None:
                continue
            if isinstance(widget, Input) or isinstance(widget, Select):
                widget.value = str(value)
            elif isinstance(widget, OptionList):
                try:
                    for idx, opt in enumerate(widget.options):
                        if getattr(opt, "id", None) == value:
                            widget.highlighted = idx
                            break
                except Exception:
                    pass

        active_tab = self._prefill_values.get("active_tab")
        if isinstance(active_tab, str) and active_tab and tabs is not None:
            tabs.active = active_tab

    def update_field_visibility(self, get_container: Callable[[str], Container | None]) -> None:
        values = self.get_current_form_values()

        for name, field_def in self.field_definitions.items():
            container = get_container(name)
            if container is None:
                continue
            should_show = True
            if field_def.visible_when:
                should_show = bool(field_def.visible_when(values))
            if should_show:
                container.remove_class("hidden")
            else:
                container.add_class("hidden")

    def is_file_field(self, field_name: str) -> bool:
        field_def = self.field_definitions.get(field_name)
        return bool(field_def and field_def.field_type == FieldType.FILE)
