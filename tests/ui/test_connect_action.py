"""UI tests for the connect action."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlit.domains.connections.discovery.docker_detector import DetectedContainer, DockerStatus
from sqlit.domains.connections.ui.screens import ConnectionPickerScreen
from sqlit.domains.connections.ui.screens.connection_picker.tabs import is_container_saved
from sqlit.domains.explorer.domain.tree_nodes import ConnectionNode
from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


class TestConnectAction:
    @pytest.mark.asyncio
    async def test_connection_picker_select_highlights_in_tree(self):
        connections = [
            create_test_connection("AppleDatabase", "sqlite"),
            create_test_connection("OrangeDB", "sqlite"),
            create_test_connection("Pear-db", "sqlite"),
        ]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next((s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)), None)
            assert picker is not None

            with patch.object(app, "connect_to_server"):
                picker.action_select()
                await pilot.pause()

            cursor_node = app.object_tree.cursor_node
            assert cursor_node is not None
            assert isinstance(cursor_node.data, ConnectionNode)
            assert cursor_node.data.config.name == "AppleDatabase"

    @pytest.mark.asyncio
    async def test_connection_picker_fuzzy_search_selects_correct_connection(self):
        connections = [
            create_test_connection("AppleDatabase", "sqlite"),
            create_test_connection("OrangeDB", "sqlite"),
            create_test_connection("Pear-db", "sqlite"),
        ]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next((s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)), None)
            assert picker is not None

            # Activate filter with "/" and search for "ora"
            picker.action_open_filter()
            picker._filter_state.text = "ora"
            picker._update_list()
            await pilot.pause()

            with patch.object(app, "connect_to_server"):
                picker.action_select()
                await pilot.pause()

            cursor_node = app.object_tree.cursor_node
            assert cursor_node is not None
            assert isinstance(cursor_node.data, ConnectionNode)
            assert cursor_node.data.config.name == "OrangeDB"


class TestDockerContainerPicker:
    """UI tests for Docker container detection in connection picker."""

    @pytest.mark.asyncio
    async def test_connection_picker_shows_docker_containers(self):
        """Test that Docker containers appear in the connection picker."""
        connections = [
            # Use different port to avoid matching mock containers
            create_test_connection("saved-postgres", "postgresql", port="5433"),
        ]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        # Mock Docker containers
        mock_containers = [
            DetectedContainer(
                container_id="abc123",
                container_name="test-postgres",
                db_type="postgresql",
                host="localhost",
                port=5432,
                username="postgres",
                password="secret",
                database="testdb",
            ),
            DetectedContainer(
                container_id="def456",
                container_name="test-mysql",
                db_type="mysql",
                host="localhost",
                port=3306,
                username="root",
                password="rootpass",
                database="mydb",
            ),
        ]

        def mock_detect():
            return DockerStatus.AVAILABLE, mock_containers

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
            docker_detector=mock_detect,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next(
                (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                None,
            )
            assert picker is not None
            picker._on_containers_loaded(DockerStatus.AVAILABLE, mock_containers)
            await pilot.pause()

            # Verify Docker containers were detected
            assert len(picker._docker_state.containers) == 2
            assert picker._docker_state.containers[0].container_name == "test-postgres"
            assert picker._docker_state.containers[1].container_name == "test-mysql"

            # Switch to Docker tab (Tab once from Connections)
            await pilot.press("tab")
            await pilot.pause()

            # Verify option list contains Docker section
            from textual.widgets import OptionList

            option_list = picker.query_one("#picker-list", OptionList)
            assert option_list.option_count > 0

            # Find Docker container options (they have docker: prefix in ID)
            docker_options = []
            for i in range(option_list.option_count):
                opt = option_list.get_option_at_index(i)
                if opt and opt.id and str(opt.id).startswith("docker:"):
                    docker_options.append(opt)

            assert len(docker_options) == 2, "Should have 2 Docker container options"

    @pytest.mark.asyncio
    async def test_connection_picker_shows_docker_not_running(self):
        """Test that picker shows message when Docker is not running."""
        mock_connections = MockConnectionStore([])
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        def mock_detect():
            return DockerStatus.NOT_RUNNING, []

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
            docker_detector=mock_detect,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next(
                (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                None,
            )
            assert picker is not None
            picker._on_containers_loaded(DockerStatus.NOT_RUNNING, [])
            await pilot.pause()
            assert picker._docker_state.status_message == "(Docker not running)"

    @pytest.mark.asyncio
    async def test_connection_picker_docker_saved_indicator(self):
        """Test that saved Docker containers show correct indicator."""
        # Create a saved connection that matches a Docker container
        connections = [
            create_test_connection(
                "matched-container",
                "postgresql",
                server="localhost",
                port="5432",
            ),
        ]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        mock_containers = [
            DetectedContainer(
                container_id="abc123",
                container_name="matched-container",
                db_type="postgresql",
                host="localhost",
                port=5432,
                username="postgres",
                password="secret",
                database="testdb",
            ),
            DetectedContainer(
                container_id="def456",
                container_name="unsaved-container",
                db_type="mysql",
                host="localhost",
                port=3306,
                username="root",
                password="rootpass",
                database=None,
            ),
        ]

        def mock_detect():
            return DockerStatus.AVAILABLE, mock_containers

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
            docker_detector=mock_detect,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next(
                (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                None,
            )
            assert picker is not None

            # First container should be detected as saved
            assert is_container_saved(connections, mock_containers[0]) is True
            # Second container should not be saved
            assert is_container_saved(connections, mock_containers[1]) is False

    @pytest.mark.asyncio
    async def test_connection_picker_select_docker_container(self):
        """Test selecting a Docker container returns correct result."""
        mock_connections = MockConnectionStore([])
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        mock_containers = [
            DetectedContainer(
                container_id="abc123",
                container_name="test-postgres",
                db_type="postgresql",
                host="localhost",
                port=5432,
                username="postgres",
                password="secret",
                database="testdb",
            ),
        ]

        def mock_detect():
            return DockerStatus.AVAILABLE, mock_containers

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
            docker_detector=mock_detect,
        )
        app = SSMSTUI(services=services)
        result_holder = []

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next(
                (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                None,
            )
            assert picker is not None
            picker._on_containers_loaded(DockerStatus.AVAILABLE, mock_containers)
            await pilot.pause()

            # Switch to Docker tab (Tab once from Connections)
            await pilot.press("tab")
            await pilot.pause()

            # Navigate to Docker container (skip headers and saved section)
            from textual.widgets import OptionList

            option_list = picker.query_one("#picker-list", OptionList)

            # Find the Docker container option
            for i in range(option_list.option_count):
                opt = option_list.get_option_at_index(i)
                if opt and opt.id and str(opt.id).startswith("docker:"):
                    option_list.highlighted = i
                    break

            # Mock dismiss to capture result
            original_dismiss = picker.dismiss

            def capture_dismiss(result):
                result_holder.append(result)
                original_dismiss(result)

            picker.dismiss = capture_dismiss

            # Select the Docker container
            picker.action_select()
            await pilot.pause()

            # Verify result
            assert len(result_holder) == 1
            result = result_holder[0]
            assert result is not None
            assert result.name == "test-postgres"
            assert result.db_type == "postgresql"


class TestConnectionPickerCursorPreservation:
    """Tests for cursor preservation when list is rebuilt."""

    @pytest.mark.asyncio
    async def test_cursor_preserved_after_container_load(self):
        """Test that cursor position is preserved when Docker containers finish loading.

        This tests the fix for the bug where cursor would reset to index 0
        whenever async operations (like Docker container detection) completed.
        """
        connections = [
            create_test_connection("AAA-first", "sqlite"),
            create_test_connection("BBB-second", "sqlite"),
            create_test_connection("CCC-third", "sqlite"),
        ]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next(
                (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                None,
            )
            assert picker is not None

            from textual.widgets import OptionList

            option_list = picker.query_one("#picker-list", OptionList)

            # Navigate down to BBB-second (index 1)
            await pilot.press("j")  # Move down
            await pilot.pause()

            # Get current highlighted position
            highlighted_before = option_list.highlighted
            assert highlighted_before is not None
            highlighted_option = option_list.get_option_at_index(highlighted_before)
            assert highlighted_option is not None
            highlighted_id_before = highlighted_option.id

            # Simulate Docker containers loading (triggers _rebuild_list)
            picker._on_containers_loaded(DockerStatus.AVAILABLE, [])
            await pilot.pause()

            # Cursor should still be on the same item
            highlighted_after = option_list.highlighted
            assert highlighted_after is not None
            highlighted_option_after = option_list.get_option_at_index(highlighted_after)
            assert highlighted_option_after is not None

            # The same option should be highlighted (by ID)
            assert highlighted_option_after.id == highlighted_id_before

    @pytest.mark.asyncio
    async def test_cursor_falls_back_to_first_when_item_removed(self):
        """Test that cursor moves to first selectable item when selected item is removed."""
        connections = [
            create_test_connection("AAA-first", "sqlite"),
            create_test_connection("BBB-second", "sqlite"),
        ]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        services = build_test_services(
            connection_store=mock_connections,
            settings_store=mock_settings,
        )
        app = SSMSTUI(services=services)

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_show_connection_picker()
            await pilot.pause()

            picker = next(
                (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                None,
            )
            assert picker is not None

            from textual.widgets import OptionList

            option_list = picker.query_one("#picker-list", OptionList)

            # Navigate to BBB-second
            await pilot.press("j")
            await pilot.pause()

            # Remove BBB-second from connections
            picker.connections = [connections[0]]

            # Trigger rebuild (simulating what happens after a delete)
            picker._rebuild_list()
            await pilot.pause()

            # Cursor should have fallen back to first selectable item
            highlighted = option_list.highlighted
            assert highlighted is not None
            # Should be on AAA-first now (first actual connection option)
            opt = option_list.get_option_at_index(highlighted)
            assert opt is not None
            assert opt.id == "AAA-first"
