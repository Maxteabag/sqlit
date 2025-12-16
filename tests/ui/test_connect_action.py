"""UI tests for the connect action."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlit.app import SSMSTUI
from sqlit.ui.screens import ConnectionPickerScreen
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
