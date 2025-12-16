"""Tests for leader combo keybindings (space + key)."""

from __future__ import annotations

import pytest

from sqlit.app import SSMSTUI
from sqlit.keymap import get_keymap
from sqlit.ui.screens import ConnectionPickerScreen, HelpScreen


class TestLeaderKeybindings:
    """Test leader combo keybindings (space + key)."""

    @pytest.mark.asyncio
    async def test_leader_show_connection_picker(self):
        """Leader + connection picker key should open the connection picker."""
        keymap = get_keymap()
        leader_key = keymap.action("leader_key")
        connection_key = keymap.leader("show_connection_picker")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Press leader and connection key quickly - must complete
            # before the 200ms timer expires and shows the menu
            await pilot.press(leader_key, connection_key)
            await pilot.pause()

            has_picker = any(isinstance(screen, ConnectionPickerScreen) for screen in app.screen_stack)
            assert has_picker

    @pytest.mark.asyncio
    async def test_leader_show_help(self):
        """Leader + help key should open the help screen."""
        keymap = get_keymap()
        leader_key = keymap.action("leader_key")
        help_key = keymap.leader("show_help")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Press leader and help key quickly - must complete
            # before the 200ms timer expires and shows the menu
            await pilot.press(leader_key, help_key)
            await pilot.pause()

            has_help = any(isinstance(screen, HelpScreen) for screen in app.screen_stack)
            assert has_help

    @pytest.mark.asyncio
    async def test_leader_commands_blocked_without_leader_key(self):
        """Leader commands should not work without pressing leader key first."""
        keymap = get_keymap()
        connection_key = keymap.leader("show_connection_picker")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Press connection key without leader - should not open connection picker
            await pilot.press(connection_key)
            await pilot.pause()

            has_picker = any(isinstance(screen, ConnectionPickerScreen) for screen in app.screen_stack)
            assert not has_picker
