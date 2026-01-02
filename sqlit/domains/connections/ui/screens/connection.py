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
    Button,
    Input,
    OptionList,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from sqlit.domains.connections.domain.config import (
    DATABASE_TYPE_DISPLAY_ORDER,
    ConnectionConfig,
    DatabaseType,
    get_database_type_labels,
)
from sqlit.domains.connections.providers.catalog import get_provider_schema
from sqlit.domains.connections.providers.driver import ensure_provider_driver_available
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.providers.metadata import has_advanced_auth, is_file_based, supports_ssh
from sqlit.domains.connections.ui.connection_focus import ConnectionFocusController
from sqlit.domains.connections.ui.connection_form import ConnectionFormController
from sqlit.domains.connections.ui.connection_test_controller import ConnectionTestController
from sqlit.domains.connections.ui.driver_status_controller import DriverStatusController
from sqlit.domains.connections.ui.restart_cache import clear_restart_cache, write_restart_cache
from sqlit.domains.connections.ui.screens.connection_styles import CONNECTION_SCREEN_CSS
from sqlit.domains.connections.ui.validation import ValidationState, validate_connection_form
from sqlit.domains.connections.ui.validation_ui_binder import ConnectionValidationBinder
from sqlit.shared.ui.protocols import AppProtocol
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

    CSS = CONNECTION_SCREEN_CSS

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
        self._form = ConnectionFormController(
            config=config,
            prefill_values=self._prefill_values,
            on_browse_file=self._on_browse_file,
        )
        self._focused_container_id: str | None = None
        self.validation_state: ValidationState = ValidationState()
        self._saved_dialog_subtitle: str | None = None
        self._driver_status: DriverStatusController | None = None
        self._test_controller: ConnectionTestController | None = None
        self._focus_controller: ConnectionFocusController | None = None
        self._validation_binder: ConnectionValidationBinder | None = None

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

    def _app(self) -> AppProtocol:
        return cast(AppProtocol, self.app)

    def _driver_status_controller(self) -> DriverStatusController:
        if self._driver_status is None:
            self._driver_status = DriverStatusController(
                app=self._app(),
                post_install_message=self._post_install_message,
            )
        return self._driver_status

    def _test_controller_instance(self) -> ConnectionTestController:
        if self._test_controller is None:
            self._test_controller = ConnectionTestController(
                screen=self,
                app=self._app(),
                driver_status=self._driver_status_controller(),
            )
        return self._test_controller

    def _focus_controller_instance(self) -> ConnectionFocusController:
        if self._focus_controller is None:
            self._focus_controller = ConnectionFocusController(screen=self, form=self._form)
        return self._focus_controller

    def _get_focusable_fields(self) -> list[Any]:
        """Expose focusable field order for tests."""
        return self._focus_controller_instance()._get_focusable_fields()

    def _validation_binder_instance(self) -> ConnectionValidationBinder:
        if self._validation_binder is None:
            self._validation_binder = ConnectionValidationBinder(screen=self)
        return self._validation_binder

    def _get_restart_callback(self) -> Any:
        restart = getattr(self.app, "restart", None)
        return restart if callable(restart) else None

    def _query_one_or_none(self, selector: str, widget_type: type[Widget]) -> Widget | None:
        try:
            return self.query_one(selector, widget_type)
        except Exception:
            return None

    def _get_field_container(self, field_name: str) -> Container | None:
        container = self._query_one_or_none(f"#container-{field_name}", Container)
        return cast(Container | None, container)

    def _on_browse_file(self, field_name: str) -> None:
        """Open file picker for a file field."""
        from sqlit.shared.ui.screens.file_picker import FilePickerMode, FilePickerScreen

        # Get current value from the field
        current_value = ""
        if field_name in self._form.field_widgets:
            widget = self._form.field_widgets[field_name]
            if isinstance(widget, Input):
                current_value = widget.value

        # Determine file extensions based on field
        file_extensions: list[str] | None = None
        if field_name == "file_path":
            # SQLite/DuckDB database files
            file_extensions = [".db", ".sqlite", ".sqlite3", ".duckdb"]

        def handle_result(path: str | None) -> None:
            if path and field_name in self._form.field_widgets:
                widget = self._form.field_widgets[field_name]
                if isinstance(widget, Input):
                    widget.value = path

        self.app.push_screen(
            FilePickerScreen(
                mode=FilePickerMode.OPEN,
                title="Select File",
                start_path=current_value if current_value else None,
                file_extensions=file_extensions,
            ),
            handle_result,
        )

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

    def _update_tls_tab_enabled(self, db_type: DatabaseType) -> None:
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
            tls_pane = self.query_one("#tab-tls", TabPane)
        except Exception:
            return

        schema = get_provider_schema(db_type.value)
        has_fields = any(field.tab == "tls" for field in schema.fields)

        tls_pane.disabled = not has_fields
        try:
            tab = tabs.get_tab(tls_pane)
            tab.disabled = not has_fields
            if has_fields:
                tab.display = True
                tls_pane.display = True
            else:
                tab.display = False
                tls_pane.display = False
        except Exception:
            pass

        if not has_fields:
            try:
                if tabs.active == tls_pane.id:
                    tabs.active = "tab-general"
            except Exception:
                pass

    def _check_driver_availability(self, db_type: DatabaseType) -> None:
        controller = self._driver_status_controller()
        controller.check_driver_availability(db_type)
        self._update_driver_status_ui()

    def _check_ssh_driver_availability(self) -> None:
        controller = self._driver_status_controller()
        controller.check_ssh_driver_availability(self._form.current_db_type)
        self._update_driver_status_ui()

    def _get_active_tab(self) -> str:
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
            return tabs.active
        except Exception:
            return "tab-general"

    def _update_driver_status_ui(self) -> None:
        controller = self._driver_status_controller()
        test_status = cast(Static | None, self._query_one_or_none("#test-status", Static))
        dialog = cast(Dialog | None, self._query_one_or_none("#connection-dialog", Dialog))
        controller.update_status_ui(
            active_tab=self._get_active_tab(),
            test_status=test_status,
            dialog=dialog,
        )

    def _write_restart_cache(self, post_install_message: str | None = None) -> None:
        try:
            values = self._form.get_current_form_values()
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
        db_type = self._form.current_db_type

        shortcuts = [("Test", "^t"), ("Save", "^s"), ("Cancel", "<esc>")]
        initial_values = self._form.get_initial_visibility_values()

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

                    db_types = DATABASE_TYPE_DISPLAY_ORDER
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
                        field_groups = self._form.get_field_groups_for_type(db_type, tab="general")
                        for group in field_groups:
                            yield self._form.create_field_group(group, initial_values=initial_values)

                with TabPane("TLS", id="tab-tls"), Container(id="dynamic-fields-tls"):
                    tls_groups = self._form.get_field_groups_for_type(db_type, tab="tls")
                    for group in tls_groups:
                        yield self._form.create_field_group(group, initial_values=initial_values)

                with TabPane("SSH", id="tab-ssh"), Container(id="dynamic-fields-ssh"):
                    ssh_groups = self._form.get_field_groups_for_type(db_type, tab="ssh")
                    for group in ssh_groups:
                        yield self._form.create_field_group(group, initial_values=initial_values)

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

        self._form.set_initial_select_values()

        if debug:
            elapsed = (time.perf_counter() - t1) * 1000
            print(f"[DEBUG] _form.set_initial_select_values: {elapsed:.1f}ms", file=sys.stderr)
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

        self._update_ssh_tab_enabled(self._form.current_db_type)
        self._update_tls_tab_enabled(self._form.current_db_type)

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

        self._check_driver_availability(self._form.current_db_type)
        if self._get_active_tab() == "tab-ssh":
            self._check_ssh_driver_availability()

        if debug:
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"[DEBUG] _check_driver_availability: {elapsed:.1f}ms", file=sys.stderr)

        if self._post_install_message and not self._driver_status_controller().missing_driver_error:
            self._update_driver_status_ui()



    def _ensure_initial_tab(self) -> None:
        try:
            tabs = self.query_one("#connection-tabs", TabbedContent)
        except Exception:
            return
        tabs.active = "tab-general"

    def _apply_prefill_values(self) -> None:
        name_input = cast(Input | None, self._query_one_or_none("#conn-name", Input))
        tabs = cast(TabbedContent | None, self._query_one_or_none("#connection-tabs", TabbedContent))
        self._form.apply_prefill_values(name_input=name_input, tabs=tabs)

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

    def _after_dbtype_change(self) -> None:
        self._form.set_initial_select_values()
        self._update_field_visibility()
        self._focus_controller_instance().focus_first_visible_field()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "dbtype-select":
            try:
                db_type = DatabaseType(str(event.value))
            except Exception:
                return
            if db_type != self._form.current_db_type:
                self._form.rebuild_dynamic_fields(
                    db_type,
                    general_container=self.query_one("#dynamic-fields-general", Container),
                    advanced_container=self.query_one("#dynamic-fields-tls", Container),
                    ssh_container=self.query_one("#dynamic-fields-ssh", Container),
                )
                self.call_after_refresh(self._after_dbtype_change)
                self._update_ssh_tab_enabled(db_type)
                self._update_tls_tab_enabled(db_type)
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle browse button clicks for file fields."""
        if event.button.id and event.button.id.startswith("browse-"):
            field_name = event.button.id[7:]  # Remove "browse-" prefix
            self._on_browse_file(field_name)

    def _update_field_visibility(self) -> None:
        self._form.update_field_visibility(self._get_field_container)

    def action_install_driver(self) -> None:
        self._driver_status_controller().prompt_install_for_active_tab(
            self._get_active_tab(),
            write_restart_cache=self._write_restart_cache,
            restart_app=self._get_restart_callback(),
        )

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
        self._validation_binder_instance().clear_name_error()
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
            self._validation_binder_instance().set_name_error("Name already exists.")

    def action_next_field(self) -> None:
        self._focus_controller_instance().focus_next_field()

    def action_prev_field(self) -> None:
        self._focus_controller_instance().focus_prev_field()

    def action_focus_tab_content(self) -> None:
        self._focus_controller_instance().focus_tab_content()

    def _get_config(self) -> ConnectionConfig | None:
        name_input = self.query_one("#conn-name", Input)
        name = name_input.value.strip()

        db_type_value = self.query_one("#dbtype-select", Select).value
        try:
            db_type = DatabaseType(str(db_type_value))
        except Exception:
            db_type = next(iter(DatabaseType))

        values = self._form.get_current_form_values()

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
            field_definitions=self._form.field_definitions,
            existing_names=self._get_existing_names(),
            editing_name=editing_name,
        )

        self._validation_binder_instance().apply_validation(
            state=self.validation_state,
            field_definitions=self._form.field_definitions,
        )

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

    def action_test_connection(self) -> None:
        from .password_input import PasswordInputScreen

        missing_driver = self._driver_status_controller().missing_driver_error
        if missing_driver:
            self._driver_status_controller().prompt_install_missing_driver(
                missing_driver,
                write_restart_cache=self._write_restart_cache,
                restart_app=self._get_restart_callback(),
            )
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
                self._run_test(temp_config)

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
                self._run_test(temp_config)

            self.app.push_screen(
                PasswordInputScreen(config.name, password_type="database"),
                on_db_password,
            )
            return

        self._run_test(config)

    def _run_test(self, config: ConnectionConfig) -> None:
        self._test_controller_instance().test_connection(
            config,
            write_restart_cache=self._write_restart_cache,
            restart_app=self._get_restart_callback(),
        )

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
            self._driver_status_controller().prompt_install_missing_driver(
                e,
                write_restart_cache=self._write_restart_cache,
                restart_app=self._get_restart_callback(),
            )
            return

        original_name = self.config.name if self.editing and self.config else None
        self.dismiss(("save", config, original_name))

    def action_cancel(self) -> None:
        self.dismiss(None)
