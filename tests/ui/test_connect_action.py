"""UI tests for the connect action."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlit.app import SSMSTUI
from sqlit.services.docker_detector import DetectedContainer, DockerStatus
from sqlit.ui.screens import ConnectionPickerScreen
from sqlit.ui.screens.connection_picker import DockerConnectionResult
from sqlit.ui.tree_nodes import ConnectionNode

from .mocks import MockConnectionStore, MockSettingsStore, create_test_connection


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

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.app.load_settings", mock_settings.load_all),
            patch("sqlit.app.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

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

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.app.load_settings", mock_settings.load_all),
            patch("sqlit.app.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                app.action_show_connection_picker()
                await pilot.pause()

                picker = next((s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)), None)
                assert picker is not None

                # Activate filter with "/" and search for "ora"
                picker.action_open_filter()
                picker.search_text = "ora"
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
            create_test_connection("saved-postgres", "postgresql"),
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

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.app.load_settings", mock_settings.load_all),
            patch("sqlit.app.save_settings", mock_settings.save_all),
            patch(
                "sqlit.services.docker_detector.detect_database_containers",
                mock_detect,
            ),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                app.action_show_connection_picker()
                await pilot.pause()

                picker = next(
                    (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                    None,
                )
                assert picker is not None

                # Verify Docker containers were detected
                assert len(picker._docker_containers) == 2
                assert picker._docker_containers[0].container_name == "test-postgres"
                assert picker._docker_containers[1].container_name == "test-mysql"

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

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.app.load_settings", mock_settings.load_all),
            patch("sqlit.app.save_settings", mock_settings.save_all),
            patch(
                "sqlit.services.docker_detector.detect_database_containers",
                mock_detect,
            ),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                app.action_show_connection_picker()
                await pilot.pause()

                picker = next(
                    (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                    None,
                )
                assert picker is not None
                assert picker._docker_status_message == "(Docker not running)"

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

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.app.load_settings", mock_settings.load_all),
            patch("sqlit.app.save_settings", mock_settings.save_all),
            patch(
                "sqlit.services.docker_detector.detect_database_containers",
                mock_detect,
            ),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                app.action_show_connection_picker()
                await pilot.pause()

                picker = next(
                    (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                    None,
                )
                assert picker is not None

                # First container should be detected as saved
                assert picker._is_container_saved(mock_containers[0]) is True
                # Second container should not be saved
                assert picker._is_container_saved(mock_containers[1]) is False

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

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.app.load_settings", mock_settings.load_all),
            patch("sqlit.app.save_settings", mock_settings.save_all),
            patch(
                "sqlit.services.docker_detector.detect_database_containers",
                mock_detect,
            ),
        ):
            app = SSMSTUI()
            result_holder = []

            async with app.run_test(size=(100, 35)) as pilot:
                app.action_show_connection_picker()
                await pilot.pause()

                picker = next(
                    (s for s in app.screen_stack if isinstance(s, ConnectionPickerScreen)),
                    None,
                )
                assert picker is not None

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
                assert isinstance(result, DockerConnectionResult)
                assert result.container.container_name == "test-postgres"
                assert result.action == "connect"
