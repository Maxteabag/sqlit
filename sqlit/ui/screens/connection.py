"""Connection configuration screen."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.events import ScreenResume, ScreenSuspend
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    OptionList,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual.widgets.option_list import Option

from ...config import (
    DATABASE_TYPE_LABELS,
    ConnectionConfig,
    DatabaseType,
)
from ...db import (
    create_ssh_tunnel,
    get_adapter,
    get_connection_schema,
    has_advanced_auth,
    is_file_based,
    supports_ssh,
)
from ...fields import (
    FieldDefinition,
    FieldGroup,
    FieldType,
    schema_to_field_definitions,
)
from ...validation import ValidationState, validate_connection_form
from ...widgets import Dialog


class ConnectionScreen(ModalScreen):
    """Modal screen for adding/editing a connection."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+t", "test_connection", "Test", priority=True),
        Binding("ctrl+i", "install_driver", "Install driver", show=False, priority=True),
        Binding("tab", "next_field", "Next field", priority=True),
        Binding("shift+tab", "prev_field", "Previous field", priority=True),
        Binding("down", "focus_tab_content", "Focus content", show=False),
    ]

    CSS = """
    ConnectionScreen {
        align: center middle;
        background: transparent;
    }

    #connection-dialog {
        width: 62;
        height: auto;
        max-height: 85%;
        border: solid $primary;
        background: $surface;
        padding: 1;
        border-title-align: left;
        border-title-color: $text-muted;
        border-title-background: $surface;
        border-title-style: bold;
        border-subtitle-align: right;
        border-subtitle-color: $primary;
        border-subtitle-background: $surface;
        border-subtitle-style: bold;
    }

    #connection-title {
        display: none;
    }

    #connection-dialog Input, #connection-dialog Select {
        margin-bottom: 0;
    }

    #btn-odbc-setup {
        width: auto;
        border: solid $primary;
        background: transparent;
        color: $primary;
        margin-top: 1;
    }

    .field-container {
        position: relative;
        height: auto;
        border: solid $primary-darken-2;
        background: $surface;
        padding: 0;
        margin-top: 0;
        border-title-align: left;
        border-title-color: $text-muted;
        border-title-background: $surface;
        border-title-style: none;
    }

    .field-container.hidden {
        display: none;
    }

    .field-container.invalid {
        border: solid $error;
    }

    .field-container.focused {
        border: solid $primary;
    }

    .field-container.invalid.focused {
        border: solid $error;
    }

    .field-container Input {
        border: none;
        height: 1;
        padding: 0;
        background: $surface;
    }

    .field-container Input:focus {
        border: none;
        background-tint: $foreground 5%;
    }

    .field-container Select {
        border: none;
        background: $surface;
        padding: 0;
    }

    .field-container .select-field {
        border: none;
        background: $surface;
        padding: 0;
    }

    #connection-tabs {
        height: auto;
    }

    TabbedContent {
        height: auto;
    }

    TabbedContent > ContentSwitcher {
        height: auto;
    }

    TabPane {
        height: auto;
        min-height: 18;
    }

    Tab:disabled {
        text-style: strike;
    }

    Tab.has-error {
        color: $error;
    }

    #dynamic-fields-general,
    #dynamic-fields-advanced {
        height: auto;
    }

    .field-group {
        height: auto;
    }

    .field-group.hidden {
        display: none;
    }

    .field-row {
        height: auto;
        width: 100%;
    }

    .field-flex {
        width: 1fr;
        height: auto;
    }

    .field-fixed {
        width: 10;
        height: auto;
        margin-left: 1;
    }

    .select-field {
        height: auto;
        max-height: 6;
        padding: 0;
        margin-bottom: 0;
    }

    .select-field > .option-list--option {
        padding: 0 1;
    }

    .error-text {
        color: $error;
        height: auto;
    }

    .error-text.hidden {
        display: none;
    }

    #test-status {
        height: auto;
        color: $text-muted;
        margin-top: 0;
    }

    #test-error {
        height: 6;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
        margin-top: 1;
    }

    #test-error.hidden {
        display: none;
    }
    """

    def __init__(self, config: ConnectionConfig | None = None, editing: bool = False):
        super().__init__()
        self.config = config
        self.editing = editing
        self._field_widgets: dict[str, Input | OptionList | Select[str]] = {}
        self._field_definitions: dict[str, FieldDefinition] = {}
        self._current_db_type: DatabaseType = self._get_initial_db_type()
        self._last_test_error: str = ""
        self._last_test_ok: bool | None = None
        self._focused_container_id: str | None = None
        self.validation_state: ValidationState = ValidationState()
        self._saved_dialog_subtitle: str | None = None
        self._missing_driver_error: Any = None  # Stores MissingDriverError if driver is missing

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Prevent underlying screens from receiving actions when another modal is on top.
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)

    def on_screen_suspend(self, event: ScreenSuspend) -> None:
        # Hide this dialog's shortcut subtitle when another modal overlays it.
        try:
            dialog = self.query_one("#connection-dialog", Dialog)
            self._saved_dialog_subtitle = dialog.border_subtitle
            dialog.border_subtitle = ""
        except Exception:
            pass

    def on_screen_resume(self, event: ScreenResume) -> None:
        try:
            dialog = self.query_one("#connection-dialog", Dialog)
            if self._saved_dialog_subtitle is not None:
                dialog.border_subtitle = self._saved_dialog_subtitle
        except Exception:
            pass

    def _get_initial_db_type(self) -> DatabaseType:
        """Get the initial database type from config."""
        if self.config:
            return self.config.get_db_type()
        return DatabaseType.MSSQL  # type: ignore[attr-defined, no-any-return]

    def _get_adapter_for_type(self, db_type: DatabaseType) -> Any:
        """Get the adapter instance for a database type."""
        return get_adapter(db_type.value)

    def _get_field_groups_for_type(self, db_type: DatabaseType, tab: str | None = None) -> list[FieldGroup]:
        """Get field groups for a database type from the schema registry."""
        schema = get_connection_schema(db_type.value)
        definitions = schema_to_field_definitions(schema)
        if tab:
            definitions = [d for d in definitions if d.tab == tab]
        return [FieldGroup(name="connection", fields=definitions)]

    def _get_field_value(self, field_name: str) -> str:
        """Get the current value of a field from config or default."""
        if self.config and hasattr(self.config, field_name):
            return getattr(self.config, field_name) or ""
        return ""

    def _get_current_form_values(self) -> dict:
        """Get all current form values as a dictionary."""
        values = {}
        for name, widget in self._field_widgets.items():
            if isinstance(widget, Input):
                values[name] = widget.value
            elif isinstance(widget, OptionList):
                field_def = self._field_definitions.get(name)
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

    def _create_field_widget(self, field_def: FieldDefinition, group_name: str) -> ComposeResult:
        """Create widgets for a field definition."""
        field_id = f"field-{field_def.name}"
        container_id = f"container-{field_def.name}"

        # Determine initial visibility
        initial_visible = True
        if field_def.visible_when:
            # Use config values for initial visibility check
            initial_values = {}
            if self.config:
                for attr in ["auth_type", "driver", "server", "port", "database", "username", "password", "file_path"]:
                    if hasattr(self.config, attr):
                        initial_values[attr] = getattr(self.config, attr) or ""
            initial_visible = field_def.visible_when(initial_values)

        hidden_class = "" if initial_visible else " hidden"

        if field_def.field_type == FieldType.DROPDOWN:
            container = Container(id=container_id, classes=f"field-container{hidden_class}")
            container.border_title = field_def.label
            with container:
                select = Select(
                    options=[(opt.label, opt.value) for opt in field_def.options],
                    value=(self._get_field_value(field_def.name) or field_def.default),
                    allow_blank=False,
                    compact=True,
                    id=field_id,
                )
                self._field_widgets[field_def.name] = select
                self._field_definitions[field_def.name] = field_def
                yield select
                yield Static("", id=f"error-{field_def.name}", classes="error-text hidden")
        elif field_def.field_type == FieldType.SELECT:
            container = Container(id=container_id, classes=f"field-container{hidden_class}")
            container.border_title = field_def.label
            with container:
                options = [Option(opt.label, id=opt.value) for opt in field_def.options]
                option_list = OptionList(*options, id=field_id, classes="select-field")
                self._field_widgets[field_def.name] = option_list
                self._field_definitions[field_def.name] = field_def
                yield option_list
                yield Static("", id=f"error-{field_def.name}", classes="error-text hidden")
        else:
            value = self._get_field_value(field_def.name) or field_def.default
            container = Container(id=container_id, classes=f"field-container{hidden_class}")
            container.border_title = field_def.label
            with container:
                input_widget = Input(
                    value=value,
                    placeholder=field_def.placeholder,
                    id=field_id,
                    password=False,
                )
                self._field_widgets[field_def.name] = input_widget
                self._field_definitions[field_def.name] = field_def
                yield input_widget
                yield Static("", id=f"error-{field_def.name}", classes="error-text hidden")

    def _create_field_group(self, group: FieldGroup) -> ComposeResult:
        """Create widgets for a field group."""
        # Group fields by row_group
        row_groups: dict[str | None, list[FieldDefinition]] = {}
        for field_def in group.fields:
            row_key = field_def.row_group
            if row_key not in row_groups:
                row_groups[row_key] = []
            row_groups[row_key].append(field_def)

        with Container(classes="field-group"):
            for row_key, fields in row_groups.items():
                if row_key is None:
                    # Single field, not in a row
                    for field_def in fields:
                        yield from self._create_field_widget(field_def, group.name)
                else:
                    # Multiple fields in a horizontal row
                    with Horizontal(classes="field-row"):
                        for field_def in fields:
                            width_class = "field-flex" if field_def.width == "flex" else "field-fixed"
                            with Container(classes=width_class):
                                yield from self._create_field_widget(field_def, group.name)

    def _split_groups_by_advanced(self, groups: list[FieldGroup]) -> tuple[list[FieldGroup], list[FieldGroup]]:
        general: list[FieldGroup] = []
        advanced: list[FieldGroup] = []
        for group in groups:
            general_fields = [f for f in group.fields if not f.advanced]
            advanced_fields = [f for f in group.fields if f.advanced]
            if general_fields:
                general.append(
                    FieldGroup(
                        name=group.name,
                        fields=general_fields,
                        visible_when=group.visible_when,
                    )
                )
            if advanced_fields:
                advanced.append(
                    FieldGroup(
                        name=group.name,
                        fields=advanced_fields,
                        visible_when=group.visible_when,
                    )
                )
        return general, advanced

    def _set_advanced_tab_enabled(self, enabled: bool) -> None:
        """Enable/disable the Advanced tab (disabled tabs are struck through)."""
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
            advanced_pane = self.query_one("#tab-advanced", TabPane)
        except Exception:
            return

        advanced_pane.disabled = not enabled
        try:
            tab = tabs.get_tab(advanced_pane)
            tab.disabled = not enabled
        except Exception:
            pass

        if not enabled:
            try:
                if tabs.active == advanced_pane.id:
                    tabs.active = "tab-general"
            except Exception:
                pass

    def _update_ssh_tab_enabled(self, db_type: DatabaseType) -> None:
        """Enable/disable the SSH tab based on database type."""
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
            ssh_pane = self.query_one("#tab-ssh", TabPane)
        except Exception:
            return

        enabled = supports_ssh(db_type.value)

        ssh_pane.disabled = not enabled
        try:
            tab = tabs.get_tab(ssh_pane)
            tab.disabled = not enabled
        except Exception:
            pass

        if not enabled:
            try:
                if tabs.active == ssh_pane.id:
                    tabs.active = "tab-general"
            except Exception:
                pass

    def _check_driver_availability(self, db_type: DatabaseType) -> None:
        """Check if the driver for the database type is available and update UI."""
        from ...db.exceptions import MissingDriverError

        self._missing_driver_error = None
        try:
            adapter = get_adapter(db_type.value)
            adapter.ensure_driver_available()
        except MissingDriverError as e:
            self._missing_driver_error = e

        self._update_driver_status_ui()

    def _update_driver_status_ui(self) -> None:
        """Update UI based on driver availability."""
        try:
            test_status = self.query_one("#test-status", Static)
            dialog = self.query_one("#connection-dialog", Dialog)
        except Exception:
            return

        if self._missing_driver_error:
            # Show warning about missing driver
            error = self._missing_driver_error
            test_status.update(
                f"[yellow]⚠ Missing driver:[/] {error.package_name}\n"
                f'[dim]Install with:[/] pip install "sqlit-tui[{error.extra_name}]"'
            )
            # Update footer to show Install driver instead of Test/Save
            dialog.border_subtitle = "[bold]Install ^i[/]  Cancel <esc>"
        else:
            # Clear warning and restore normal footer
            if not self._last_test_ok and self._last_test_ok is not None:
                pass  # Keep existing error message
            else:
                test_status.update("")
            dialog.border_subtitle = "[bold]Test ^t[/]  Save ^s  Cancel <esc>"

    def compose(self) -> ComposeResult:
        title = "Edit Connection" if self.editing else "New Connection"
        db_type = self._get_initial_db_type()

        shortcuts = [("Test", "^t"), ("Save", "^s"), ("Cancel", "<esc>")]

        with Dialog(id="connection-dialog", title=title, shortcuts=shortcuts):
            with TabbedContent(id="connection-tabs"):
                with TabPane("General", id="tab-general"):
                    name_container = Container(id="container-name", classes="field-container")
                    name_container.border_title = "Name"
                    with name_container:
                        yield Input(
                            value=self.config.name if self.config else "",
                            placeholder="",
                            id="conn-name",
                        )
                        yield Static("", id="error-name", classes="error-text hidden")

                    db_types = list(DatabaseType)
                    dbtype_container = Container(id="container-dbtype", classes="field-container")
                    dbtype_container.border_title = "Database Type"
                    with dbtype_container:
                        yield Select(
                            options=[(DATABASE_TYPE_LABELS[dt], dt.value) for dt in db_types],
                            value=db_type.value,
                            allow_blank=False,
                            compact=True,
                            id="dbtype-select",
                        )

                    with Container(id="dynamic-fields-general"):
                        field_groups = self._get_field_groups_for_type(db_type, tab="general")
                        general_groups, _advanced_groups = self._split_groups_by_advanced(field_groups)
                        for group in general_groups:
                            yield from self._create_field_group(group)

                with TabPane("Advanced", id="tab-advanced"):
                    with Container(id="dynamic-fields-advanced"):
                        field_groups = self._get_field_groups_for_type(db_type, tab="general")
                        _general_groups, advanced_groups = self._split_groups_by_advanced(field_groups)
                        for group in advanced_groups:
                            yield from self._create_field_group(group)
                    with Container(id="mssql-driver-setup", classes="hidden"):
                        yield Button("ODBC driver setup…", id="btn-odbc-setup")

                with TabPane("SSH", id="tab-ssh"):
                    with Container(id="dynamic-fields-ssh"):
                        ssh_groups = self._get_field_groups_for_type(db_type, tab="ssh")
                        for group in ssh_groups:
                            yield from self._create_field_group(group)

            yield Static("", id="test-status")
            yield TextArea("", id="test-error", read_only=True, classes="hidden")

    def on_mount(self) -> None:
        self.query_one("#conn-name", Input).focus()

        # Set initial values for select fields
        self._set_initial_select_values()
        self._update_field_visibility()
        self._validate_name_unique()
        field_groups = self._get_field_groups_for_type(self._current_db_type, tab="general")
        _general, advanced = self._split_groups_by_advanced(field_groups)
        self._set_advanced_tab_enabled(bool(advanced))
        self._update_ssh_tab_enabled(self._current_db_type)
        self._update_mssql_driver_setup_visibility(self._current_db_type)
        self._check_driver_availability(self._current_db_type)

    def on_descendant_focus(self, event: Any) -> None:
        focused = self.focused
        if focused is None:
            return

        container_id: str | None = None
        focused_id = getattr(focused, "id", None)
        if focused_id == "conn-name":
            container_id = "container-name"
        elif focused_id == "dbtype-select":
            container_id = "container-dbtype"
        elif focused_id and str(focused_id).startswith("field-"):
            field_name = str(focused_id).removeprefix("field-")
            container_id = f"container-{field_name}"

        if container_id is None:
            return

        if self._focused_container_id and self._focused_container_id != container_id:
            try:
                self.query_one(f"#{self._focused_container_id}", Container).remove_class("focused")
            except Exception:
                pass

        self._focused_container_id = container_id
        try:
            self.query_one(f"#{container_id}", Container).add_class("focused")
        except Exception:
            pass

    def _set_initial_select_values(self) -> None:
        """Set initial highlighted values for select fields based on config."""
        for name, widget in self._field_widgets.items():
            if isinstance(widget, OptionList):
                field_def = self._field_definitions.get(name)
                if not field_def:
                    continue

                value = self._get_field_value(name) or field_def.default

                for i, opt in enumerate(field_def.options):
                    if opt.value == value:
                        widget.highlighted = i
                        break
            elif isinstance(widget, Select):
                field_def = self._field_definitions.get(name)
                if not field_def:
                    continue
                value = self._get_field_value(name) or field_def.default
                widget.value = value

    def _rebuild_dynamic_fields(self, db_type: DatabaseType) -> None:
        """Rebuild the dynamic fields for a new database type."""
        self._current_db_type = db_type
        self._field_widgets.clear()
        self._field_definitions.clear()

        general_container = self.query_one("#dynamic-fields-general", Container)
        advanced_container = self.query_one("#dynamic-fields-advanced", Container)
        ssh_container = self.query_one("#dynamic-fields-ssh", Container)
        general_container.remove_children()
        advanced_container.remove_children()
        ssh_container.remove_children()

        field_groups = self._get_field_groups_for_type(db_type, tab="general")
        general_groups, advanced_groups = self._split_groups_by_advanced(field_groups)
        self._set_advanced_tab_enabled(bool(advanced_groups))
        for group in general_groups:
            for widget in self._create_field_group_widgets(group):
                general_container.mount(widget)
        for group in advanced_groups:
            for widget in self._create_field_group_widgets(group):
                advanced_container.mount(widget)

        ssh_groups = self._get_field_groups_for_type(db_type, tab="ssh")
        for group in ssh_groups:
            for widget in self._create_field_group_widgets(group):
                ssh_container.mount(widget)

    def _create_field_group_widgets(self, group: FieldGroup) -> list:
        """Create widget instances for a field group (for mounting)."""
        widgets = []

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
                    for w in self._create_field_widget_instances(field_def, group.name):
                        group_container.compose_add_child(w)
            else:
                row = Horizontal(classes="field-row")
                for field_def in fields:
                    width_class = "field-flex" if field_def.width == "flex" else "field-fixed"
                    field_container = Container(classes=width_class)
                    for w in self._create_field_widget_instances(field_def, group.name):
                        field_container.compose_add_child(w)
                    row.compose_add_child(field_container)
                group_container.compose_add_child(row)

        widgets.append(group_container)
        return widgets

    def _create_field_widget_instances(self, field_def: FieldDefinition, group_name: str) -> list:
        """Create widget instances for a field (for mounting)."""
        widgets = []
        field_id = f"field-{field_def.name}"
        container_id = f"container-{field_def.name}"

        initial_visible = True
        if field_def.visible_when:
            initial_values = self._get_current_form_values()
            initial_visible = field_def.visible_when(initial_values)

        hidden_class = "" if initial_visible else " hidden"

        container = Container(id=container_id, classes=f"field-container{hidden_class}")
        container.border_title = field_def.label

        if field_def.field_type == FieldType.DROPDOWN:
            select = Select(
                options=[(opt.label, opt.value) for opt in field_def.options],
                value=(self._get_field_value(field_def.name) or field_def.default),
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

        widgets.append(container)
        return widgets

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "dbtype-select":
            try:
                db_type = DatabaseType(str(event.value))
            except Exception:
                return
            if db_type != self._current_db_type:
                self._rebuild_dynamic_fields(db_type)
                self._set_initial_select_values()
                self._update_field_visibility()
                self._focus_first_required()
                self._update_ssh_tab_enabled(db_type)
                self._update_mssql_driver_setup_visibility(db_type)
                self._check_driver_availability(db_type)
            return

        if event.select.id and str(event.select.id).startswith("field-"):
            self._update_field_visibility()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        # A select field changed - update visibility of dependent fields
        if event.option_list.id and event.option_list.id.startswith("field-"):
            self._update_field_visibility()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "conn-name":
            self._validate_name_unique()

    def _update_field_visibility(self) -> None:
        """Update visibility of fields based on current form values."""
        values = self._get_current_form_values()

        for name, field_def in self._field_definitions.items():
            container = self.query_one(f"#container-{name}", Container)
            should_show = True
            if field_def.visible_when:
                should_show = bool(field_def.visible_when(values))
            if should_show:
                container.remove_class("hidden")
            else:
                container.add_class("hidden")

    def _get_focusable_fields(self) -> list:
        """Get list of focusable fields in order, based on active tab.

        Note: Tab bar is intentionally excluded from focusable fields.
        Users can switch tabs by clicking or using keyboard shortcuts,
        but Tab key should cycle through form fields only.
        """
        fields = []

        try:
            tabs_widget = self.query_one("#connection-tabs", TabbedContent)
            active_tab = tabs_widget.active
        except Exception:
            active_tab = "tab-general"

        if active_tab == "tab-ssh":
            ssh_fields = [
                "ssh_enabled",
                "ssh_host",
                "ssh_port",
                "ssh_username",
                "ssh_auth_type",
                "ssh_key_path",
                "ssh_password",
            ]
            for field in ssh_fields:
                try:
                    container = self.query_one(f"#container-{field}", Container)
                    if "hidden" not in container.classes:
                        widget = self.query_one(f"#field-{field}")
                        fields.append(widget)
                except Exception:
                    pass
            return fields

        if active_tab == "tab-general":
            fields.extend(
                [
                    self.query_one("#conn-name", Input),
                    self.query_one("#dbtype-select", Select),
                ]
            )
            for name, widget in self._field_widgets.items():
                if name.startswith("ssh_"):
                    continue
                field_def = self._field_definitions.get(name)
                if field_def and field_def.advanced:
                    continue
                try:
                    container = self.query_one(f"#container-{name}", Container)
                    if "hidden" not in container.classes:
                        fields.append(widget)
                except Exception:
                    pass

        elif active_tab == "tab-advanced":
            for name, widget in self._field_widgets.items():
                field_def = self._field_definitions.get(name)
                if field_def and field_def.advanced:
                    try:
                        container = self.query_one(f"#container-{name}", Container)
                        if "hidden" not in container.classes:
                            fields.append(widget)
                    except Exception:
                        pass
            try:
                container = self.query_one("#mssql-driver-setup", Container)
                if "hidden" not in container.classes:
                    fields.append(self.query_one("#btn-odbc-setup", Button))
            except Exception:
                pass

        return fields

    def _update_mssql_driver_setup_visibility(self, db_type: DatabaseType) -> None:
        try:
            container = self.query_one("#mssql-driver-setup", Container)
        except Exception:
            return
        if db_type.value == "mssql":
            container.remove_class("hidden")
        else:
            container.add_class("hidden")

    def _set_select_field_value(self, field_name: str, value: str) -> None:
        widget = self._field_widgets.get(field_name)
        field_def = self._field_definitions.get(field_name)
        if not isinstance(widget, OptionList) or not field_def or not field_def.options:
            return
        for i, opt in enumerate(field_def.options):
            if opt.value == value:
                widget.highlighted = i
                return

    def _open_odbc_driver_setup(self, installed_drivers: list[str] | None = None) -> None:
        from ...db.exceptions import MissingDriverError
        from ...drivers import get_installed_drivers
        from ...terminal import run_in_terminal
        from ..screens import DriverSetupScreen, MessageScreen

        try:
            get_adapter("mssql").ensure_driver_available()
        except MissingDriverError as e:
            self._prompt_install_missing_driver(e)
            return

        installed = installed_drivers if installed_drivers is not None else get_installed_drivers()

        def on_result(result: Any) -> None:
            if not result:
                return
            action = result[0]
            if action == "select":
                driver = result[1]
                self._set_select_field_value("driver", driver)
                return
            if action == "install":
                commands = result[1]
                res = run_in_terminal(commands)
                if res.success:
                    self.app.push_screen(
                        MessageScreen(
                            "Driver install",
                            "Installation started in a new terminal.\n\nPlease restart to apply.",
                        )
                    )
                else:

                    def reopen(_: Any = None) -> None:
                        self._open_odbc_driver_setup(installed_drivers=installed)

                    self.app.push_screen(
                        MessageScreen(
                            "Couldn't install automatically",
                            "Couldn't install automatically, please install manually.",
                        ),
                        reopen,
                    )

        self.app.push_screen(DriverSetupScreen(installed), on_result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-odbc-setup":
            self._open_odbc_driver_setup()

    def action_open_odbc_setup(self) -> None:
        if self._current_db_type.value != "mssql":
            return
        self._open_odbc_driver_setup()

    def action_install_driver(self) -> None:
        """Install the missing driver for the current database type."""
        if self._missing_driver_error:
            self._prompt_install_missing_driver(self._missing_driver_error)
        elif self._current_db_type.value == "mssql":
            # For MSSQL, open ODBC setup
            self._open_odbc_driver_setup()

    def _clear_field_error(self, name: str) -> None:
        try:
            container = self.query_one(f"#container-{name}", Container)
            container.remove_class("invalid")
        except Exception:
            pass
        try:
            error = self.query_one(f"#error-{name}", Static)
            error.update("")
            error.add_class("hidden")
        except Exception:
            pass

    def _set_field_error(self, name: str, message: str) -> None:
        try:
            container = self.query_one(f"#container-{name}", Container)
            container.add_class("invalid")
        except Exception:
            pass
        try:
            error = self.query_one(f"#error-{name}", Static)

            error.update("" if message == "Required." else message)
            if message == "Required.":
                error.add_class("hidden")
            else:
                error.remove_class("hidden")
        except Exception:
            pass

    def _set_tab_error(self, tab_id: str) -> None:
        """Mark a tab as having an error."""
        try:
            tabs_widget = self.query_one("#connection-tabs", TabbedContent)
            pane = self.query_one(f"#{tab_id}", TabPane)
            tab = tabs_widget.get_tab(pane)
            tab.add_class("has-error")
        except Exception:
            pass

    def _clear_tab_errors(self) -> None:
        """Clear error styling from all tabs."""
        try:
            tabs_widget = self.query_one("#connection-tabs", TabbedContent)
            for tab_id in ["tab-general", "tab-advanced", "tab-ssh"]:
                try:
                    pane = self.query_one(f"#{tab_id}", TabPane)
                    tab = tabs_widget.get_tab(pane)
                    tab.remove_class("has-error")
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_validation_to_ui(self) -> None:
        """Apply validation_state to UI elements."""
        self._clear_tab_errors()
        self.validation_state.tab_errors.clear()

        # Clear all field errors first
        self._clear_field_error("name")
        for field_name in self._field_definitions:
            self._clear_field_error(field_name)
        for ssh_field in ["ssh_host", "ssh_username", "ssh_key_path"]:
            self._clear_field_error(ssh_field)

        # Apply errors from validation state
        for field_name, message in self.validation_state.errors.items():
            self._set_field_error(field_name, message)

            # Determine which tab to mark
            if field_name == "name":
                self._set_tab_error("tab-general")
                self.validation_state.add_tab_error("tab-general")
            elif field_name.startswith("ssh_"):
                self._set_tab_error("tab-ssh")
                self.validation_state.add_tab_error("tab-ssh")
            elif field_name in self._field_definitions:
                field_def = self._field_definitions[field_name]
                if field_def.advanced:
                    self._set_tab_error("tab-advanced")
                    self.validation_state.add_tab_error("tab-advanced")
                else:
                    self._set_tab_error("tab-general")
                    self.validation_state.add_tab_error("tab-general")
            else:
                self._set_tab_error("tab-general")
                self.validation_state.add_tab_error("tab-general")

    def _get_existing_names(self) -> set[str]:
        """Get set of existing connection names."""
        try:
            connections = getattr(self.app, "connections", []) or []
            names: set[str] = set()
            for conn in connections:
                name = getattr(conn, "name", None)
                if isinstance(name, str) and name:
                    names.add(name)
            return names
        except Exception:
            return set()

    def _validate_name_unique(self) -> None:
        self._clear_field_error("name")
        name = self.query_one("#conn-name", Input).value.strip()
        if not name:
            return
        existing: list[Any] = []
        try:
            existing = getattr(self.app, "connections", []) or []
        except Exception:
            existing = []

        if self.editing and self.config and name == self.config.name:
            return
        if any(getattr(c, "name", None) == name for c in existing):
            self._set_field_error("name", "Name already exists.")

    def _focus_first_required(self) -> None:
        values = self._get_current_form_values()
        for field_name, field_def in self._field_definitions.items():
            if not field_def.required:
                continue
            is_visible = True
            if field_def.visible_when:
                is_visible = bool(field_def.visible_when(values))
            if field_def.advanced and not self._show_advanced:
                is_visible = False
            if not is_visible:
                continue
            widget = self._field_widgets.get(field_name)
            if widget is None:
                continue
            if isinstance(widget, Input):
                if not widget.value.strip():
                    widget.focus()
                    return
            if isinstance(widget, OptionList):
                if widget.highlighted is None:
                    widget.focus()
                    return

    def action_next_field(self) -> None:
        from textual.widgets import Tabs

        fields = self._get_focusable_fields()
        focused = self.focused

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

    def action_prev_field(self) -> None:
        from textual.widgets import Tabs

        fields = self._get_focusable_fields()
        focused = self.focused

        if isinstance(focused, Tabs):
            return

        if focused in fields:
            idx = fields.index(focused)
            if idx == 0:
                try:
                    tabs_widget = self.query_one("#connection-tabs", TabbedContent)
                    tab_bar = tabs_widget.query_one(Tabs)
                    tab_bar.focus()
                except Exception:
                    pass
            else:
                fields[idx - 1].focus()
        elif fields:
            fields[-1].focus()

    def action_focus_tab_content(self) -> None:
        """Focus the first field of the active tab when pressing down on tab bar."""
        from textual.widgets import Tabs

        # Only handle if tab bar is focused
        try:
            tabs_widget = self.query_one("#connection-tabs", TabbedContent)
            tab_bar = tabs_widget.query_one(Tabs)
            if self.focused != tab_bar:
                return  # Let default down arrow behavior work
        except Exception:
            return

        active_tab = tabs_widget.active

        if active_tab == "tab-general":
            self.query_one("#conn-name", Input).focus()
        elif active_tab == "tab-advanced":
            # Focus first visible advanced field
            for name, widget in self._field_widgets.items():
                field_def = self._field_definitions.get(name)
                if field_def and field_def.advanced:
                    try:
                        container = self.query_one(f"#container-{name}", Container)
                        if "hidden" not in container.classes:
                            widget.focus()
                            return
                    except Exception:
                        pass
        elif active_tab == "tab-ssh":
            ssh_widget = self._field_widgets.get("ssh_enabled")
            if ssh_widget:
                ssh_widget.focus()

    def _get_config(self) -> ConnectionConfig | None:
        """Build a ConnectionConfig from the current form values."""
        name_input = self.query_one("#conn-name", Input)
        name = name_input.value.strip()

        # Get selected database type
        db_type_value = self.query_one("#dbtype-select", Select).value
        try:
            db_type = DatabaseType(str(db_type_value))
        except Exception:
            db_type = DatabaseType.MSSQL  # type: ignore[attr-defined]

        values = self._get_current_form_values()

        # Name suggestion
        if not name:
            suggestion = ""
            if is_file_based(db_type.value):
                fp = values.get("file_path", "").strip()
                suggestion = fp.split("/")[-1] if fp else db_type.value
            else:
                server = values.get("server", "").strip()
                suggestion = f"{db_type.value}-{server}" if server else db_type.value
            suggestion = suggestion.replace(" ", "-")[:40] or "connection"
            name_input.value = suggestion
            name = suggestion

        # Run validation
        editing_name = self.config.name if self.editing and self.config else None
        self.validation_state = validate_connection_form(
            name=name,
            db_type=db_type.value,
            values=values,
            field_definitions=self._field_definitions,
            existing_names=self._get_existing_names(),
            editing_name=editing_name,
        )

        # Apply validation to UI
        self._apply_validation_to_ui()

        if not self.validation_state.is_valid():
            # Focus the first field with an error
            for field_name in self.validation_state.errors:
                if field_name == "name":
                    name_input.focus()
                    break
                try:
                    self.query_one(f"#field-{field_name}").focus()
                    break
                except Exception:
                    pass
            return None

        # Build config
        config_kwargs = {
            "name": name,
            "db_type": db_type.value,
        }

        # Add all field values to config
        for field_name, value in values.items():
            if not field_name.startswith("ssh_"):
                config_kwargs[field_name] = value

        if has_advanced_auth(db_type.value):
            auth_type = values.get("auth_type", "sql")
            config_kwargs["trusted_connection"] = auth_type == "windows"

        if supports_ssh(db_type.value):
            config_kwargs["ssh_enabled"] = values.get("ssh_enabled") == "enabled"
            config_kwargs["ssh_host"] = values.get("ssh_host", "")
            config_kwargs["ssh_port"] = values.get("ssh_port", "22")
            config_kwargs["ssh_username"] = values.get("ssh_username", "")
            config_kwargs["ssh_auth_type"] = values.get("ssh_auth_type", "key")
            config_kwargs["ssh_key_path"] = values.get("ssh_key_path", "")
            config_kwargs["ssh_password"] = values.get("ssh_password", "")

        return ConnectionConfig(**config_kwargs)

    def _get_package_install_hint(self, db_type: str) -> str | None:
        """Get pip install command for missing database packages."""
        try:
            adapter = get_adapter(db_type)
            return adapter.install_hint
        except (ValueError, ImportError):
            return None

    def _prompt_install_missing_driver(self, error: Exception) -> None:
        from ...db.exceptions import MissingDriverError
        from ...services.installer import Installer
        from ..screens import PackageSetupScreen

        if not isinstance(error, MissingDriverError):
            return

        self.app.push_screen(
            PackageSetupScreen(error, on_install=lambda err: Installer(self.app).install(err)),
        )

    def action_test_connection(self) -> None:
        from dataclasses import replace

        from ...db.exceptions import MissingDriverError, MissingODBCDriverError

        # If driver is missing, show install dialog instead
        if self._missing_driver_error:
            self._prompt_install_missing_driver(self._missing_driver_error)
            return

        config = self._get_config()
        if not config:
            return

        self.query_one("#test-error", TextArea).add_class("hidden")
        self.query_one("#test-status", Static).update("Testing…")
        self._last_test_ok = None
        self._last_test_error = ""
        tunnel = None

        # Check if we're in mock mode
        mock_profile = getattr(self.app, "_mock_profile", None)

        try:
            if mock_profile:
                # Use mock adapter and skip SSH tunnel in mock mode
                adapter = mock_profile.get_adapter(config.db_type)
                connect_config = config
            else:
                tunnel, host, port = create_ssh_tunnel(config)
                if tunnel:
                    connect_config = replace(config, server=host, port=str(port))
                else:
                    connect_config = config
                adapter = get_adapter(config.db_type)

            conn = adapter.connect(connect_config)
            conn.close()

            # Close tunnel after test
            if tunnel:
                tunnel.stop()
            try:
                set_health = getattr(self.app, "_set_connection_health", None)
                if callable(set_health):
                    set_health(config.name, True)
            except Exception:
                pass
            self._last_test_ok = True
            self.query_one("#test-status", Static).update("Last test: OK")
        except MissingDriverError as e:
            self._prompt_install_missing_driver(e)
            self._last_test_ok = False
            self.query_one("#test-status", Static).update("Last test: failed (missing driver)")
        except MissingODBCDriverError as e:
            self._open_odbc_driver_setup(e.installed_drivers)
            self._last_test_ok = False
            self.query_one("#test-status", Static).update("Last test: failed (missing ODBC driver)")
        except (ModuleNotFoundError, ImportError) as e:
            hint = self._get_package_install_hint(config.db_type)
            if hint:
                self.query_one("#test-status", Static).update("Last test: failed (missing package)")
                err = self.query_one("#test-error", TextArea)
                err.text = f"{e}\n\nInstall with:\n  {hint}"
                err.remove_class("hidden")
                self._last_test_error = err.text
            else:
                self.query_one("#test-status", Static).update("Last test: failed")
                err = self.query_one("#test-error", TextArea)
                err.text = f"{e}"
                err.remove_class("hidden")
                self._last_test_error = err.text
            self._last_test_ok = False
        except Exception as e:
            try:
                set_health = getattr(self.app, "_set_connection_health", None)
                if callable(set_health):
                    set_health(config.name, False)
            except Exception:
                pass
            self._last_test_ok = False
            self.query_one("#test-status", Static).update("Last test: failed")
            err = self.query_one("#test-error", TextArea)
            err.text = str(e)
            err.remove_class("hidden")
            self._last_test_error = err.text
        finally:
            # Ensure tunnel is closed on any failure
            if tunnel:
                try:
                    tunnel.stop()
                except Exception:
                    pass

    def action_save(self) -> None:
        config = self._get_config()
        if not config:
            return

        from ...db.exceptions import MissingDriverError

        try:
            get_adapter(config.db_type).ensure_driver_available()
        except MissingDriverError as e:
            self._prompt_install_missing_driver(e)
            return

        self.dismiss(("save", config))

    def action_cancel(self) -> None:
        self.dismiss(None)

    @property
    def _show_advanced(self) -> bool:
        """Check if advanced tab is currently active."""
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
            return tabs.active == "tab-advanced"
        except Exception:
            return False
