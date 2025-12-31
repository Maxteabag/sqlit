"""Connection configuration screen."""

from __future__ import annotations

import os
from typing import Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import ScreenResume, ScreenSuspend
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Input,
    OptionList,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from sqlit.domains.connections.domain.config import (
    ConnectionConfig,
    DatabaseType,
    get_database_type_labels,
)
from sqlit.domains.connections.providers.catalog import get_provider_schema
from sqlit.domains.connections.providers.driver import ensure_provider_driver_available
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.providers.metadata import has_advanced_auth, is_file_based, supports_ssh
from sqlit.domains.connections.ui.driver_status import build_driver_status_display
from sqlit.domains.connections.ui.field_widgets import FieldWidgetBuilder
from sqlit.domains.connections.ui.fields import FieldDefinition, FieldGroup, schema_to_field_definitions
from sqlit.domains.connections.ui.restart_cache import clear_restart_cache, write_restart_cache
from sqlit.domains.connections.ui.validation import ValidationState, validate_connection_form
from sqlit.shared.ui.protocols import AppProtocol
from sqlit.shared.ui.spinner import SPINNER_FRAMES, Spinner
from sqlit.shared.ui.widgets import Dialog


class ConnectionScreen(ModalScreen):
    """Modal screen for adding/editing a connection."""

    AUTO_FOCUS = "#conn-name"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
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
        max-height: 38;
        border: solid $primary;
        background: $surface;
        padding: 1;
        border-title-align: left;
        border-title-color: $primary;
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

    .field-container {
        position: relative;
        height: auto;
        border: solid $panel;
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
        border-title-color: $error;
    }

    .field-container.focused {
        border: solid $primary;
        border-title-color: $primary;
    }

    .field-container.invalid.focused {
        border: solid $error;
        border-title-color: $error;
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
        height: 1fr;
    }

    TabbedContent {
        height: 1fr;
    }

    TabbedContent > ContentSwitcher {
        height: 1fr;
    }

    TabPane {
        height: 1fr;
        min-height: 18;
        overflow-y: auto;
    }

    Tab:disabled {
        text-style: strike;
    }

    Tab.has-error {
        color: $error;
    }

    #dynamic-fields-general {
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

    #test-status.success {
        color: $success;
    }
    """

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        editing: bool = False,
        *,
        prefill_values: dict[str, Any] | None = None,
        post_install_message: str | None = None,
    ):
        super().__init__()
        self.config = config
        self.editing = editing
        self._prefill_values = prefill_values or {}
        self._post_install_message = post_install_message
        self._field_widgets: dict[str, Widget] = {}
        self._field_definitions: dict[str, FieldDefinition] = {}
        self._current_db_type: DatabaseType = self._get_initial_db_type()
        self._last_test_error: str = ""
        self._last_test_ok: bool | None = None
        self._focused_container_id: str | None = None
        self.validation_state: ValidationState = ValidationState()
        self._saved_dialog_subtitle: str | None = None
        self._missing_driver_error: Any = None  # Stores MissingDriverError if driver is missing
        self._missing_ssh_driver_error: Any = None  # Stores MissingDriverError for SSH tunnel
        # Test connection spinner state
        self._test_in_progress: bool = False
        self._test_spinner: Spinner | None = None
        self._test_start_time: float = 0.0

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)

    def on_screen_suspend(self, event: ScreenSuspend) -> None:
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
        prefill_db_type = self._prefill_values.get("db_type")
        if isinstance(prefill_db_type, str) and prefill_db_type:
            try:
                return DatabaseType(prefill_db_type)
            except Exception:
                pass
        if self.config:
            return self.config.get_db_type()
        return next(iter(DatabaseType))

    def _app(self) -> AppProtocol:
        return cast(AppProtocol, self.app)

    def _get_provider_for_type(self, db_type: DatabaseType) -> Any:
        return self._app().services.provider_factory(db_type.value)

    def _get_field_groups_for_type(self, db_type: DatabaseType, tab: str | None = None) -> list[FieldGroup]:
        schema = get_provider_schema(db_type.value)
        definitions = schema_to_field_definitions(schema)
        if tab:
            definitions = [d for d in definitions if d.tab == tab]
        return [FieldGroup(name="connection", fields=definitions)]

    def _get_field_value(self, field_name: str) -> str:
        if self.config:
            return str(self.config.get_field_value(field_name, ""))
        return ""

    def _select_value_in_options(self, field_def: FieldDefinition, value: str | None) -> bool:
        return any(opt.value == value for opt in field_def.options)

    def _resolve_select_value(self, field_def: FieldDefinition) -> str:
        value = self._get_field_value(field_def.name)
        if self._select_value_in_options(field_def, value):
            return value
        if self._select_value_in_options(field_def, field_def.default):
            return field_def.default
        if field_def.options:
            return field_def.options[0].value
        return ""

    def _get_current_form_values(self) -> dict:
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

    def _get_field_builder(self) -> FieldWidgetBuilder:
        return FieldWidgetBuilder(
            field_widgets=self._field_widgets,
            field_definitions=self._field_definitions,
            get_field_value=self._get_field_value,
            resolve_select_value=self._resolve_select_value,
            get_current_form_values=self._get_current_form_values,
        )

    def _get_initial_visibility_values(self) -> dict[str, Any]:
        initial_values: dict[str, Any] = {}
        if self.config:
            for attr in ["auth_type", "driver", "server", "port", "database", "username", "password", "file_path"]:
                initial_values[attr] = self.config.get_field_value(attr, "")
        return initial_values

    def _create_field_group(
        self,
        group: FieldGroup,
        *,
        initial_values: dict[str, Any] | None = None,
    ) -> ComposeResult:
        builder = self._get_field_builder()
        yield builder.build_group_container(group, initial_values=initial_values)

    def _update_ssh_tab_enabled(self, db_type: DatabaseType) -> None:
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
        self._missing_driver_error = None
        try:
            provider = self._app().services.provider_factory(db_type.value)
            ensure_provider_driver_available(provider, resolver=self._app().services.driver_resolver)
        except MissingDriverError as e:
            self._missing_driver_error = e

        self._update_driver_status_ui()

    def _check_ssh_driver_availability(self) -> None:
        from sqlit.domains.connections.app.tunnel import ensure_ssh_tunnel_available

        self._missing_ssh_driver_error = None
        if not supports_ssh(self._current_db_type.value):
            self._update_driver_status_ui()
            return
        try:
            ensure_ssh_tunnel_available()
        except MissingDriverError as e:
            self._missing_ssh_driver_error = e

        self._update_driver_status_ui()

    def _get_active_tab(self) -> str:
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
            return tabs.active
        except Exception:
            return "tab-general"

    def _update_driver_status_ui(self) -> None:
        try:
            test_status = self.query_one("#test-status", Static)
            dialog = self.query_one("#connection-dialog", Dialog)
        except Exception:
            return

        try:
            test_status.remove_class("success")
        except Exception:
            pass

        active_tab = self._get_active_tab()
        if active_tab == "tab-ssh":
            error = self._missing_ssh_driver_error
        else:
            error = self._missing_driver_error

        display = build_driver_status_display(
            error,
            self._post_install_message,
            self._app().services.install_strategy,
        )
        test_status.update(display.message)
        if display.success:
            try:
                test_status.add_class("success")
            except Exception:
                pass
        dialog.border_subtitle = display.subtitle

    def _start_test_spinner(self) -> None:
        """Start the connection test spinner animation."""
        import time

        self._test_in_progress = True
        self._test_start_time = time.perf_counter()
        if self._test_spinner is not None:
            self._test_spinner.stop()
        self._test_spinner = Spinner(self, on_tick=lambda _: self._update_test_status(), fps=30)
        self._test_spinner.start()

    def _stop_test_spinner(self) -> None:
        """Stop the connection test spinner animation."""
        self._test_in_progress = False
        if self._test_spinner is not None:
            self._test_spinner.stop()
            self._test_spinner = None

    def _update_test_status(self) -> None:
        """Update the test status display with current spinner frame."""
        import time

        try:
            test_status = self.query_one("#test-status", Static)
        except Exception:
            return

        if self._test_in_progress:
            elapsed = time.perf_counter() - self._test_start_time
            spinner_frame = self._test_spinner.frame if self._test_spinner else SPINNER_FRAMES[0]
            test_status.update(f"{spinner_frame} Testing ({elapsed:.1f}s)...")
        # When not in progress, status is updated by success/error handlers

    def _write_restart_cache(self, *, post_install_message: str | None = None) -> None:
        try:
            values = self._get_current_form_values()
            values["name"] = self.query_one("#conn-name", Input).value
            db_type = self.query_one("#dbtype-select", Select).value
            values["db_type"] = str(db_type) if db_type is not None else ""
            try:
                tabs = self.query_one("#connection-tabs", TabbedContent)
                active_tab = tabs.active
            except Exception:
                active_tab = "tab-general"

            payload = {
                "version": 1,
                "editing": bool(self.editing),
                "original_name": getattr(self.config, "name", None) if self.editing and self.config else None,
                "active_tab": active_tab,
                "values": values,
                "post_install_message": post_install_message,
            }
            write_restart_cache(payload)
        except Exception:
            # Best-effort; don't block installation due to caching failure.
            pass

    def _clear_restart_cache(self) -> None:
        clear_restart_cache()

    def compose(self) -> ComposeResult:
        title = "Edit Connection" if self.editing else "New Connection"
        db_type = self._get_initial_db_type()

        shortcuts = [("Test", "^t"), ("Save", "^s"), ("Cancel", "<esc>")]
        initial_values = self._get_initial_visibility_values()

        with Dialog(id="connection-dialog", title=title, shortcuts=shortcuts):
            with TabbedContent(id="connection-tabs", initial="tab-general"):
                with TabPane("General", id="tab-general"):
                    name_container = Container(id="container-name", classes="field-container")
                    name_container.border_title = "Name"
                    with name_container:
                        yield Input(
                            value=self.config.name if self.config else "",
                            placeholder="",
                            id="conn-name",
                            select_on_focus=False,
                        )
                        yield Static("", id="error-name", classes="error-text hidden")

                    db_types = list(DatabaseType)
                    labels = get_database_type_labels()
                    dbtype_container = Container(id="container-dbtype", classes="field-container")
                    dbtype_container.border_title = "Database Type"
                    with dbtype_container:
                        yield Select(
                            options=[(labels[dt], dt.value) for dt in db_types],
                            value=db_type.value,
                            allow_blank=False,
                            compact=True,
                            id="dbtype-select",
                        )

                    with Container(id="dynamic-fields-general"):
                        field_groups = self._get_field_groups_for_type(db_type, tab="general")
                        for group in field_groups:
                            yield from self._create_field_group(group, initial_values=initial_values)

                with TabPane("SSH", id="tab-ssh"):
                    with Container(id="dynamic-fields-ssh"):
                        ssh_groups = self._get_field_groups_for_type(db_type, tab="ssh")
                        for group in ssh_groups:
                            yield from self._create_field_group(group, initial_values=initial_values)

            yield Static("", id="test-status")

    def on_mount(self) -> None:
        import sys
        import time

        debug = os.environ.get("SQLIT_DEBUG_TIMING")

        if debug:
            t0 = time.perf_counter()

        self.call_after_refresh(self._ensure_initial_tab)

        if debug:
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"[DEBUG] _ensure_initial_tab scheduled: {elapsed:.1f}ms", file=sys.stderr)
            t1 = time.perf_counter()

        self._set_initial_select_values()

        if debug:
            elapsed = (time.perf_counter() - t1) * 1000
            print(f"[DEBUG] _set_initial_select_values: {elapsed:.1f}ms", file=sys.stderr)
            t1 = time.perf_counter()

        self._apply_prefill_values()

        if debug:
            elapsed = (time.perf_counter() - t1) * 1000
            print(f"[DEBUG] _apply_prefill_values: {elapsed:.1f}ms", file=sys.stderr)
            t1 = time.perf_counter()

        self._update_field_visibility()

        if debug:
            elapsed = (time.perf_counter() - t1) * 1000
            print(f"[DEBUG] _update_field_visibility: {elapsed:.1f}ms", file=sys.stderr)
            t1 = time.perf_counter()

        self._validate_name_unique()

        if debug:
            elapsed = (time.perf_counter() - t1) * 1000
            print(f"[DEBUG] _validate_name_unique: {elapsed:.1f}ms", file=sys.stderr)
            t1 = time.perf_counter()

        self._update_ssh_tab_enabled(self._current_db_type)

        if debug:
            elapsed = (time.perf_counter() - t1) * 1000
            print(f"[DEBUG] _update_ssh_tab_enabled: {elapsed:.1f}ms", file=sys.stderr)
            total = (time.perf_counter() - t0) * 1000
            print(f"[DEBUG] on_mount total: {total:.1f}ms", file=sys.stderr)

        # Defer driver check to after screen is rendered to avoid blocking UI
        self.call_after_refresh(self._deferred_driver_check)

    def _deferred_driver_check(self) -> None:
        """Check driver availability after screen is visible."""
        import sys
        import time

        debug = os.environ.get("SQLIT_DEBUG_TIMING")
        if debug:
            t0 = time.perf_counter()

        self._check_driver_availability(self._current_db_type)
        if self._get_active_tab() == "tab-ssh":
            self._check_ssh_driver_availability()

        if debug:
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"[DEBUG] _check_driver_availability: {elapsed:.1f}ms", file=sys.stderr)

        if self._post_install_message and not self._missing_driver_error:
            self._update_driver_status_ui()



    def _ensure_initial_tab(self) -> None:
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
        except Exception:
            return
        tabs.active = "tab-general"

    def _apply_prefill_values(self) -> None:
        if not self._prefill_values:
            return

        values = self._prefill_values.get("values") if "values" in self._prefill_values else self._prefill_values
        if not isinstance(values, dict):
            return

        name_value = values.get("name")
        if isinstance(name_value, str):
            try:
                self.query_one("#conn-name", Input).value = name_value
            except Exception:
                pass

        for field_name, widget in self._field_widgets.items():
            value = values.get(field_name)
            if value is None:
                continue
            if isinstance(widget, Input):
                widget.value = str(value)
            elif isinstance(widget, Select):
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
        if isinstance(active_tab, str) and active_tab:
            try:
                tabs = self.query_one("#connection-tabs", TabbedContent)
                tabs.active = active_tab
            except Exception:
                pass

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if self._get_active_tab() == "tab-ssh":
            self._check_ssh_driver_availability()
        else:
            self._update_driver_status_ui()

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
        for name, widget in self._field_widgets.items():
            if isinstance(widget, OptionList):
                field_def = self._field_definitions.get(name)
                if not field_def:
                    continue

                value = self._resolve_select_value(field_def)

                for i, opt in enumerate(field_def.options):
                    if opt.value == value:
                        widget.highlighted = i
                        break
            # Note: Select widgets get their value from construction, no need to set here

    def _rebuild_dynamic_fields(self, db_type: DatabaseType) -> None:
        self._current_db_type = db_type
        self._field_widgets.clear()
        self._field_definitions.clear()

        general_container = self.query_one("#dynamic-fields-general", Container)
        ssh_container = self.query_one("#dynamic-fields-ssh", Container)
        general_container.remove_children()
        ssh_container.remove_children()

        field_groups = self._get_field_groups_for_type(db_type, tab="general")
        for group in field_groups:
            for widget in self._create_field_group_widgets(group):
                general_container.mount(widget)

        ssh_groups = self._get_field_groups_for_type(db_type, tab="ssh")
        for group in ssh_groups:
            for widget in self._create_field_group_widgets(group):
                ssh_container.mount(widget)

    def _after_dbtype_change(self) -> None:
        self._set_initial_select_values()
        self._update_field_visibility()
        self._focus_first_visible_field()

    def _create_field_group_widgets(self, group: FieldGroup) -> list[Widget]:
        builder = self._get_field_builder()
        return [builder.build_group_container(group)]

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "dbtype-select":
            try:
                db_type = DatabaseType(str(event.value))
            except Exception:
                return
            if db_type != self._current_db_type:
                self._rebuild_dynamic_fields(db_type)
                self.call_after_refresh(self._after_dbtype_change)
                self._update_ssh_tab_enabled(db_type)
                self._check_driver_availability(db_type)
            return

        if event.select.id and str(event.select.id).startswith("field-"):
            self._update_field_visibility()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id and event.option_list.id.startswith("field-"):
            self._update_field_visibility()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "conn-name":
            self._validate_name_unique()

    def _update_field_visibility(self) -> None:
        values = self._get_current_form_values()

        for name, field_def in self._field_definitions.items():
            try:
                container = self.query_one(f"#container-{name}", Container)
            except Exception:
                # Container may not be mounted yet after dynamic field rebuild
                continue
            should_show = True
            if field_def.visible_when:
                should_show = bool(field_def.visible_when(values))
            if should_show:
                container.remove_class("hidden")
            else:
                container.add_class("hidden")

    def _get_focusable_fields(self) -> list:
        """Tab bar is intentionally excluded from focusable fields.
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
                        field_widget = self.query_one(f"#field-{field}")
                        fields.append(field_widget)
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
            for name in self._field_definitions:
                widget_opt = self._field_widgets.get(name)
                if widget_opt is None:
                    continue
                if name.startswith("ssh_"):
                    continue
                try:
                    container = self.query_one(f"#container-{name}", Container)
                    if "hidden" not in container.classes:
                        fields.append(widget_opt)
                except Exception:
                    pass

        return fields

    def _set_select_field_value(self, field_name: str, value: str) -> None:
        widget = self._field_widgets.get(field_name)
        field_def = self._field_definitions.get(field_name)
        if widget is None or not isinstance(widget, OptionList) or not field_def or not field_def.options:
            return
        for i, opt in enumerate(field_def.options):
            if opt.value == value:
                widget.highlighted = i
                return

    def action_install_driver(self) -> None:
        active_tab = self._get_active_tab()
        if active_tab == "tab-ssh" and self._missing_ssh_driver_error:
            self._prompt_install_missing_driver(self._missing_ssh_driver_error)
            return
        if self._missing_driver_error:
            self._prompt_install_missing_driver(self._missing_driver_error)

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
            for tab_id in ["tab-general", "tab-ssh"]:
                try:
                    pane = self.query_one(f"#{tab_id}", TabPane)
                    tab = tabs_widget.get_tab(pane)
                    tab.remove_class("has-error")
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_validation_to_ui(self) -> None:
        self._clear_tab_errors()
        self.validation_state.tab_errors.clear()

        self._clear_field_error("name")
        for field_name in self._field_definitions:
            self._clear_field_error(field_name)
        for ssh_field in ["ssh_host", "ssh_username", "ssh_key_path"]:
            self._clear_field_error(ssh_field)

        for field_name, message in self.validation_state.errors.items():
            self._set_field_error(field_name, message)

            if field_name == "name":
                self._set_tab_error("tab-general")
                self.validation_state.add_tab_error("tab-general")
            elif field_name.startswith("ssh_"):
                self._set_tab_error("tab-ssh")
                self.validation_state.add_tab_error("tab-ssh")
            elif field_name in self._field_definitions:
                self._set_tab_error("tab-general")
                self.validation_state.add_tab_error("tab-general")
            else:
                self._set_tab_error("tab-general")
                self.validation_state.add_tab_error("tab-general")

    def _get_existing_names(self) -> set[str]:
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
        ordered_fields = list(self._field_definitions.keys())

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
            field_def = self._field_definitions.get(field_name)
            if not field_def or not field_def.required:
                continue
            if not is_visible(field_def):
                continue
            widget = self._field_widgets.get(field_name)
            if widget is None:
                continue
            if is_missing(widget):
                widget.focus()
                return

        for field_name in ordered_fields:
            field_def = self._field_definitions.get(field_name)
            if not field_def or not is_visible(field_def):
                continue
            widget = self._field_widgets.get(field_name)
            if widget is None:
                continue
            widget.focus()
            return

    def _focus_first_visible_field(self) -> None:
        values = self._get_current_form_values()
        ordered_fields = list(self._field_definitions.keys())

        for field_name in ordered_fields:
            field_def = self._field_definitions.get(field_name)
            if not field_def:
                continue
            if field_def.visible_when and not bool(field_def.visible_when(values)):
                continue
            widget = self._field_widgets.get(field_name)
            if widget is None:
                continue
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
        from textual.widgets import Tabs

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
        elif active_tab == "tab-ssh":
            ssh_widget = self._field_widgets.get("ssh_enabled")
            if ssh_widget:
                ssh_widget.focus()

    def _get_config(self) -> ConnectionConfig | None:
        name_input = self.query_one("#conn-name", Input)
        name = name_input.value.strip()

        db_type_value = self.query_one("#dbtype-select", Select).value
        try:
            db_type = DatabaseType(str(db_type_value))
        except Exception:
            db_type = next(iter(DatabaseType))

        values = self._get_current_form_values()

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

        editing_name = self.config.name if self.editing and self.config else None
        self.validation_state = validate_connection_form(
            name=name,
            db_type=db_type.value,
            values=values,
            field_definitions=self._field_definitions,
            existing_names=self._get_existing_names(),
            editing_name=editing_name,
        )

        self._apply_validation_to_ui()

        if not self.validation_state.is_valid():
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

        config_data = dict(values)
        config_data["name"] = name
        config_data["db_type"] = db_type.value

        if has_advanced_auth(db_type.value):
            auth_type = values.get("auth_type", "sql")
            config_data["auth_type"] = auth_type
            config_data["trusted_connection"] = auth_type == "windows"

        file_path = str(config_data.pop("file_path", ""))
        if file_path:
            endpoint = {"kind": "file", "path": file_path}
        else:
            endpoint = {
                "kind": "tcp",
                "host": config_data.pop("server", ""),
                "port": config_data.pop("port", ""),
                "database": config_data.pop("database", ""),
                "username": config_data.pop("username", ""),
                "password": config_data.pop("password", None),
            }

        tunnel = {"enabled": False}
        if supports_ssh(db_type.value):
            ssh_enabled = config_data.pop("ssh_enabled", "disabled") == "enabled"
            if ssh_enabled:
                tunnel = {
                    "enabled": True,
                    "host": config_data.pop("ssh_host", ""),
                    "port": config_data.pop("ssh_port", "22"),
                    "username": config_data.pop("ssh_username", ""),
                    "auth_type": config_data.pop("ssh_auth_type", "key"),
                    "password": config_data.pop("ssh_password", None),
                    "key_path": config_data.pop("ssh_key_path", ""),
                }

        config_data["endpoint"] = endpoint
        config_data["tunnel"] = tunnel

        return ConnectionConfig.from_dict(config_data)

    def _get_package_install_hint(self, db_type: str) -> str | None:
        try:
            provider = self._app().services.provider_factory(db_type)
            driver = provider.driver
            if driver is None or not driver.package_name or not driver.extra_name:
                return None
            strategy = self._app().services.install_strategy.detect(
                extra_name=driver.extra_name,
                package_name=driver.package_name,
            )
            if strategy.can_auto_install:
                return self._format_install_hint(strategy)
            manual = getattr(strategy, "manual_instructions", "")
            if isinstance(manual, str) and manual:
                return manual.split("\n")[0].strip()
            return None
        except (ValueError, ImportError):
            return None

    def _format_install_hint(self, strategy: Any) -> str:
        from sqlit.domains.connections.ui.driver_status import _format_install_hint

        return _format_install_hint(strategy)

    def _prompt_install_missing_driver(self, error: Exception) -> None:
        from ..screens import PackageSetupScreen

        if not isinstance(error, MissingDriverError):
            return

        def on_install_success() -> None:
            # Cache form state and restart for seamless experience
            self._write_restart_cache(post_install_message="Successfully installed driver")
            restart = getattr(self.app, "restart", None)
            if callable(restart):
                restart()

        self.app.push_screen(PackageSetupScreen(error, on_success=on_install_success))

    def action_test_connection(self) -> None:
        from .password_input import PasswordInputScreen

        if self._missing_driver_error:
            self._prompt_install_missing_driver(self._missing_driver_error)
            return

        config = self._get_config()
        if not config:
            return

        if (
            config.tunnel
            and config.tunnel.auth_type == "password"
            and config.tunnel.password is None
        ):

            def on_ssh_password(password: str | None) -> None:
                if password is None:
                    return
                temp_config = config.with_tunnel(password=password)
                self._test_with_config(temp_config)

            self.app.push_screen(
                PasswordInputScreen(config.name, password_type="ssh"),
                on_ssh_password,
            )
            return

        endpoint = config.tcp_endpoint
        if not is_file_based(config.db_type) and endpoint and endpoint.password is None:

            def on_db_password(password: str | None) -> None:
                if password is None:
                    return
                temp_config = config.with_endpoint(password=password)
                self._test_with_config(temp_config)

            self.app.push_screen(
                PasswordInputScreen(config.name, password_type="database"),
                on_db_password,
            )
            return

        self._test_with_config(config)

    def _test_with_config(self, config: ConnectionConfig) -> None:
        import time

        self._last_test_ok = None
        self._last_test_error = ""

        def on_test_success() -> None:
            """Handle successful connection test on main thread."""

            self._stop_test_spinner()
            elapsed = time.perf_counter() - self._test_start_time
            try:
                set_health = getattr(self.app, "_set_connection_health", None)
                if callable(set_health):
                    set_health(config.name, True)
            except Exception:
                pass
            self._last_test_ok = True
            try:
                test_status = self.query_one("#test-status", Static)
                test_status.update(f"[green]✓[/] Connection OK ({elapsed:.1f}s)")
            except Exception:
                pass

        def on_test_error(error: Exception) -> None:
            """Handle connection test error on main thread."""

            self._stop_test_spinner()
            elapsed = time.perf_counter() - self._test_start_time

            if isinstance(error, MissingDriverError):
                self._last_test_ok = False
                self._prompt_install_missing_driver(error)
            elif isinstance(error, (ModuleNotFoundError, ImportError)):
                hint = self._get_package_install_hint(config.db_type)
                if hint:
                    error_msg = f"Install with: {hint}"
                else:
                    error_msg = str(error)
                self._last_test_ok = False
                self._last_test_error = error_msg
                try:
                    test_status = self.query_one("#test-status", Static)
                    test_status.update(f"[red]✗[/] Missing package ({elapsed:.1f}s)")
                except Exception:
                    pass
            else:
                try:
                    set_health = getattr(self.app, "_set_connection_health", None)
                    if callable(set_health):
                        set_health(config.name, False)
                except Exception:
                    pass
                self._last_test_ok = False
                self._last_test_error = str(error)
                try:
                    test_status = self.query_one("#test-status", Static)
                    # Show a short version of the error
                    err_str = str(error)
                    # Extract just the key part of the error message
                    if "]" in err_str:
                        err_str = err_str.split("]")[-1].strip()
                    if len(err_str) > 50:
                        err_str = err_str[:47] + "..."
                    test_status.update(f"[red]✗[/] {err_str} ({elapsed:.1f}s)")
                except Exception:
                    pass

        def do_test() -> None:
            """Run the connection test in a background thread."""
            try:
                manager = self._app()._connection_manager
                assert manager is not None
                result = manager.test_connection(config)
                if result.ok:
                    self.app.call_from_thread(on_test_success)
                else:
                    self.app.call_from_thread(on_test_error, result.error)
            except Exception as e:
                self.app.call_from_thread(on_test_error, e)

        self._start_test_spinner()
        self.run_worker(do_test, name="test-connection", thread=True, exclusive=True)

    def action_save(self) -> None:
        config = self._get_config()
        if not config:
            return

        try:
            ensure_provider_driver_available(
                self._app().services.provider_factory(config.db_type),
                resolver=self._app().services.driver_resolver,
            )
        except MissingDriverError as e:
            self._prompt_install_missing_driver(e)
            return

        original_name = self.config.name if self.editing and self.config else None
        self.dismiss(("save", config, original_name))

    def action_cancel(self) -> None:
        self.dismiss(None)
