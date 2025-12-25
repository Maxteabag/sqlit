"""UI tests for the ConnectionScreen."""

from __future__ import annotations

import pytest

from sqlit.config import ConnectionConfig

from .conftest import ConnectionScreenTestApp


class TestConnectionScreen:
    @pytest.mark.asyncio
    async def test_create_connection(self, tmp_path):
        """Test creating a new SQLite connection (no external driver needed)."""
        # Create a temp file that passes validation
        db_path = tmp_path / "test.db"
        db_path.touch()

        # Initialize with SQLite to avoid external driver dependencies
        app = ConnectionScreenTestApp(prefill_values={"db_type": "sqlite"})

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            screen.query_one("#conn-name").value = "my-sqlite"
            screen.query_one("#field-file_path").value = str(db_path)

            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config, original_name = app.screen_result
        assert action == "save"
        assert config.name == "my-sqlite"
        assert config.db_type == "sqlite"
        assert config.get_option("file_path") == str(db_path)
        assert original_name is None  # New connection has no original name

    @pytest.mark.asyncio
    async def test_edit_connection(self, tmp_path):
        """Test editing an existing SQLite connection."""
        # Create temp files that pass validation
        old_db = tmp_path / "old.db"
        new_db = tmp_path / "new.db"
        old_db.touch()
        new_db.touch()

        original = ConnectionConfig(
            name="prod-db",
            db_type="sqlite",
            options={"file_path": str(old_db)},
        )
        app = ConnectionScreenTestApp(original, editing=True)

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            assert screen.query_one("#conn-name").value == "prod-db"
            assert screen.query_one("#field-file_path").value == str(old_db)

            screen.query_one("#conn-name").value = "new-prod-db"
            screen.query_one("#field-file_path").value = str(new_db)

            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config, original_name = app.screen_result
        assert action == "save"
        assert config.name == "new-prod-db"
        assert config.db_type == "sqlite"
        assert config.get_option("file_path") == str(new_db)
        assert original_name == "prod-db"  # Original name preserved for edit

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
        config = ConnectionConfig(name="", db_type="sqlite", options={"file_path": ""})
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
        config = ConnectionConfig(name="", db_type="sqlite", options={"file_path": ""})
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


class TestEditConnectionNoDuplicates:
    """Tests to ensure editing connections doesn't create duplicates."""

    @pytest.mark.asyncio
    async def test_edit_same_name_returns_original_name(self, tmp_path):
        """Editing a connection with same name should return original_name."""
        db_path = tmp_path / "test.db"
        db_path.touch()

        original = ConnectionConfig(
            name="my-connection",
            db_type="sqlite",
            options={"file_path": str(db_path)},
        )
        app = ConnectionScreenTestApp(original, editing=True)

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            # Keep the same name, just save
            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config, original_name = app.screen_result
        assert action == "save"
        assert config.name == "my-connection"
        assert original_name == "my-connection"

    @pytest.mark.asyncio
    async def test_edit_changed_name_returns_original_name(self, tmp_path):
        """Editing a connection with new name should return original_name for proper removal."""
        db_path = tmp_path / "test.db"
        db_path.touch()

        original = ConnectionConfig(
            name="old-name",
            db_type="sqlite",
            options={"file_path": str(db_path)},
        )
        app = ConnectionScreenTestApp(original, editing=True)

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            # Change the name
            screen.query_one("#conn-name").value = "new-name"
            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config, original_name = app.screen_result
        assert action == "save"
        assert config.name == "new-name"
        assert original_name == "old-name"  # Original name preserved

    @pytest.mark.asyncio
    async def test_new_connection_returns_no_original_name(self, tmp_path):
        """Creating a new connection should return None for original_name."""
        db_path = tmp_path / "test.db"
        db_path.touch()

        app = ConnectionScreenTestApp(prefill_values={"db_type": "sqlite"})

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            screen.query_one("#conn-name").value = "brand-new"
            screen.query_one("#field-file_path").value = str(db_path)
            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config, original_name = app.screen_result
        assert action == "save"
        assert config.name == "brand-new"
        assert original_name is None  # New connection has no original


class TestDuplicateConnection:
    """Tests for duplicate connection functionality."""

    @pytest.mark.asyncio
    async def test_duplicate_returns_no_original_name(self, tmp_path):
        """Duplicating a connection should return None for original_name (it's a new connection)."""
        db_path = tmp_path / "test.db"
        db_path.touch()

        # Simulate duplicate: passing a config but editing=False
        # (duplicate creates a new connection from template)
        template = ConnectionConfig(
            name="original (copy)",
            db_type="sqlite",
            options={"file_path": str(db_path)},
        )
        # When duplicating, editing=False since it's a new connection
        app = ConnectionScreenTestApp(template, editing=False)

        async with app.run_test(size=(100, 35)) as pilot:
            screen = app.screen
            # Save the duplicate
            screen.action_save()
            await pilot.pause()

        assert app.screen_result is not None
        action, config, original_name = app.screen_result
        assert action == "save"
        assert config.name == "original (copy)"
        assert original_name is None  # Duplicate is treated as new connection
