"""Tests for contextual keybindings that only work in specific contexts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlit.app import SSMSTUI
from sqlit.keymap import get_keymap

from ..mocks import MockConnectionStore, MockSettingsStore, create_test_connection


class TestContextualKeybindings:
    """Test that keybindings only work in their intended context."""

    @pytest.mark.asyncio
    async def test_focus_explorer_key_when_query_focused(self):
        """Focus explorer key should focus explorer when query panel is focused."""
        keymap = get_keymap()
        focus_explorer_key = keymap.action("focus_explorer")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Focus query first
            app.action_focus_query()
            await pilot.pause()
            assert app.query_input.has_focus

            # Press focus explorer key
            await pilot.press(focus_explorer_key)
            await pilot.pause()

            assert app.object_tree.has_focus

    @pytest.mark.asyncio
    async def test_focus_query_key_when_explorer_focused(self):
        """Focus query key should focus query when explorer is focused."""
        keymap = get_keymap()
        focus_query_key = keymap.action("focus_query")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Focus explorer first
            app.action_focus_explorer()
            await pilot.pause()
            assert app.object_tree.has_focus

            # Press focus query key
            await pilot.press(focus_query_key)
            await pilot.pause()

            assert app.query_input.has_focus

    @pytest.mark.asyncio
    async def test_edit_connection_blocked_when_query_focused(self):
        """Edit connection key should NOT trigger edit_connection when query is focused."""
        keymap = get_keymap()
        edit_key = keymap.action("edit_connection")

        connections = [create_test_connection("TestDB", "sqlite")]
        mock_connections = MockConnectionStore(connections)
        mock_settings = MockSettingsStore({"theme": "tokyo-night"})

        with (
            patch("sqlit.app.load_connections", mock_connections.load_all),
            patch("sqlit.theme_manager.load_settings", mock_settings.load_all),
            patch("sqlit.theme_manager.save_settings", mock_settings.save_all),
        ):
            app = SSMSTUI()

            async with app.run_test(size=(100, 35)) as pilot:
                # Focus query
                app.action_focus_query()
                await pilot.pause()

                edit_called = False
                original_edit = app.action_edit_connection

                def mock_edit():
                    nonlocal edit_called
                    edit_called = True
                    original_edit()

                app.action_edit_connection = mock_edit

                # Press edit key - should focus explorer (since e is also focus_explorer), not edit connection
                await pilot.press(edit_key)
                await pilot.pause()

                assert not edit_called
