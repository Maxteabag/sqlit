"""UI tests for the ConnectionScreen."""

from __future__ import annotations

import pytest

from sqlit.config import ConnectionConfig
from sqlit.db.schema import get_all_schemas

from .conftest import ConnectionScreenTestApp


def _get_providers_with_advanced_tab() -> set[str]:
    return {db_type for db_type, schema in get_all_schemas().items() if any(f.advanced for f in schema.fields)}


def _get_providers_without_advanced_tab() -> set[str]:
    return {db_type for db_type, schema in get_all_schemas().items() if not any(f.advanced for f in schema.fields)}


class TestConnectionScreen:
    @pytest.mark.asyncio
    async def test_create_connection(self):
        app = ConnectionScreenTestApp()

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            screen.query_one("#conn-name").value = "my-mssql"
            screen.query_one("#field-server").value = "localhost"
            screen.query_one("#field-port").value = "1433"
            screen.query_one("#field-database").value = "mydb"
            screen.query_one("#field-username").value = "sa"
            screen.query_one("#field-password").value = "secret"

            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config = app.screen_result
        assert action == "save"
        assert config.name == "my-mssql"
        assert config.db_type == "mssql"
        assert config.server == "localhost"
        assert config.port == "1433"
        assert config.database == "mydb"
        assert config.username == "sa"
        assert config.password == "secret"

    @pytest.mark.asyncio
    async def test_edit_connection(self):
        original = ConnectionConfig(
            name="prod-db",
            db_type="mssql",
            server="old-server",
            port="1433",
            database="olddb",
            username="olduser",
            password="oldpass",
        )
        app = ConnectionScreenTestApp(original, editing=True)

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            assert screen.query_one("#conn-name").value == "prod-db"
            assert screen.query_one("#field-server").value == "old-server"

            screen.query_one("#conn-name").value = "new-prod-db"
            screen.query_one("#field-server").value = "new-server"
            screen.query_one("#field-database").value = "newdb"

            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config = app.screen_result
        assert action == "save"
        assert config.name == "new-prod-db"
        assert config.db_type == "mssql"
        assert config.server == "new-server"
        assert config.database == "newdb"

    @pytest.mark.asyncio
    async def test_cancel_connection(self):
        app = ConnectionScreenTestApp()

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            screen.action_cancel()
            await pilot.pause()

        assert app.screen_result is None

    @pytest.mark.asyncio
    async def test_empty_fields_shows_validation_errors(self):
        app = ConnectionScreenTestApp()

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen

            screen.action_save()
            await pilot.pause()

            assert not screen.validation_state.is_valid()
            assert screen.validation_state.has_error("server")
            assert screen.validation_state.has_error("username")

            container_server = screen.query_one("#container-server")
            container_username = screen.query_one("#container-username")
            assert "invalid" in container_server.classes
            assert "invalid" in container_username.classes

            screen.query_one("#field-server").value = "localhost"
            screen.action_save()
            await pilot.pause()

            assert screen.validation_state.has_error("username")
            assert not screen.validation_state.has_error("server")

        assert app.screen_result is None

    @pytest.mark.asyncio
    async def test_save_from_ssh_tab_marks_general_tab_with_error(self):
        app = ConnectionScreenTestApp()

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            tabs = screen.query_one("#connection-tabs")
            tabs.active = "tab-ssh"
            await pilot.pause()

            screen.action_save()
            await pilot.pause()

            assert screen.validation_state.has_tab_error("tab-general")

    @pytest.mark.asyncio
    async def test_save_from_ssh_tab_redirects_to_general_on_error(self):
        app = ConnectionScreenTestApp()

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            tabs = screen.query_one("#connection-tabs")
            tabs.active = "tab-ssh"
            await pilot.pause()

            screen.action_save()
            await pilot.pause()

            assert tabs.active == "tab-general"


class TestTabNavigation:
    """Tests for Tab key navigation through form fields."""

    @pytest.mark.asyncio
    async def test_sqlite_tab_navigation_excludes_tab_bar(self):
        """Tab navigation should cycle through form fields only, not the tab bar.

        For SQLite, the focusable fields should be:
        conn-name -> dbtype-select -> file_path -> (back to conn-name)

        The tab bar should NOT be included in this cycle.
        """
        config = ConnectionConfig(name="", db_type="sqlite", file_path="")
        app = ConnectionScreenTestApp(config, editing=False)

        async with app.run_test(size=(100, 35)) as _pilot:
            screen = app.screen

            # Get the list of focusable fields
            focusable = screen._get_focusable_fields()

            # Verify tab bar is NOT in the focusable fields
            from textual.widgets import Tabs

            tab_bar_in_fields = any(isinstance(f, Tabs) for f in focusable)
            assert not tab_bar_in_fields, "Tab bar should not be in focusable fields"

            # Verify the expected fields are present
            field_ids = [getattr(f, "id", None) for f in focusable]
            assert "conn-name" in field_ids
            assert "dbtype-select" in field_ids
            assert "field-file_path" in field_ids

            # For SQLite, there should be exactly 3 focusable fields
            assert len(focusable) == 3, f"Expected 3 focusable fields for SQLite, got {len(focusable)}: {field_ids}"

    @pytest.mark.asyncio
    async def test_tab_key_cycles_through_sqlite_fields(self):
        """Pressing Tab should cycle through SQLite form fields correctly."""
        config = ConnectionConfig(name="", db_type="sqlite", file_path="")
        app = ConnectionScreenTestApp(config, editing=False)

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen

            # Focus should start on conn-name
            conn_name = screen.query_one("#conn-name")
            conn_name.focus()
            await pilot.pause()
            assert screen.focused.id == "conn-name"

            # Tab to dbtype-select
            await pilot.press("tab")
            assert screen.focused.id == "dbtype-select"

            # Tab to file_path
            await pilot.press("tab")
            assert screen.focused.id == "field-file_path"

            # Tab should cycle back to conn-name (not to tab bar)
            await pilot.press("tab")
            assert screen.focused.id == "conn-name", "Tab should cycle back to conn-name, not go to tab bar"

    @pytest.mark.asyncio
    async def test_shift_tab_from_first_field_goes_to_tab_bar(self):
        """Pressing Shift+Tab from the first field should focus the tab bar.

        This allows users to navigate to the tab bar and switch tabs using
        arrow keys, then press Tab/Down to go back into form fields.
        """
        # Use default (mssql) which has more fields and SSH tab enabled
        app = ConnectionScreenTestApp()

        async with app.run_test(size=(100, 35)) as pilot:
            from textual.widgets import Tabs

            screen = app.screen

            # Focus should start on conn-name (first field)
            conn_name = screen.query_one("#conn-name")
            conn_name.focus()
            await pilot.pause()
            assert screen.focused.id == "conn-name"

            # Verify we're on general tab
            tabs = screen.query_one("#connection-tabs")
            assert tabs.active == "tab-general"

            # Shift+Tab should go to the tab bar
            await pilot.press("shift+tab")

            # Should still be on general tab (not switched)
            assert tabs.active == "tab-general", "Shift+Tab should not switch tabs"

            # Focus should be on the Tabs widget (tab bar)
            assert isinstance(screen.focused, Tabs), (
                f"Shift+Tab from first field should focus tab bar, " f"but focused is {type(screen.focused).__name__}"
            )


class TestAdvancedTab:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", _get_providers_with_advanced_tab())
    async def test_advanced_tab_enabled(self, db_type):
        config = ConnectionConfig(name="test", db_type=db_type)
        app = ConnectionScreenTestApp(config, editing=True)

        async with app.run_test(size=(100, 35)) as _pilot:
            screen = app.screen
            tabs = screen.query_one("#connection-tabs")
            advanced_pane = screen.query_one("#tab-advanced")
            advanced_tab = tabs.get_tab(advanced_pane)

            assert not advanced_tab.disabled

    @pytest.mark.asyncio
    @pytest.mark.parametrize("db_type", _get_providers_without_advanced_tab())
    async def test_advanced_tab_disabled(self, db_type):
        config = ConnectionConfig(name="test", db_type=db_type)
        app = ConnectionScreenTestApp(config, editing=True)

        async with app.run_test(size=(100, 35)) as _pilot:
            screen = app.screen
            tabs = screen.query_one("#connection-tabs")
            advanced_pane = screen.query_one("#tab-advanced")
            advanced_tab = tabs.get_tab(advanced_pane)

            assert advanced_tab.disabled
