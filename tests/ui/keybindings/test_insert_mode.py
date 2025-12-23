"""Tests for keybindings in vim INSERT mode."""

from __future__ import annotations

import pytest

from sqlit.app import SSMSTUI
from sqlit.keymap import get_keymap
from sqlit.widgets import VimMode


class TestInsertModeKeybindings:
    """Test keybindings in vim INSERT mode."""

    @pytest.mark.asyncio
    async def test_enter_insert_mode_key(self):
        """Enter insert mode key should enter INSERT mode when in query normal mode."""
        keymap = get_keymap()
        insert_key = keymap.action("enter_insert_mode")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Wait for app to fully mount
            await pilot.pause()

            # Set up NORMAL mode state directly (vim mode behavior)
            app.query_input.focus()
            app.editor_mode = VimMode.NORMAL
            app.query_input.read_only = True
            await pilot.pause()

            assert app.editor_mode == VimMode.NORMAL

            await pilot.press(insert_key)
            await pilot.pause()

            assert app.editor_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_exit_insert_mode_key(self):
        """Exit insert mode key should exit INSERT mode."""
        keymap = get_keymap()
        exit_key = keymap.action("exit_insert_mode")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Wait for app to fully mount
            await pilot.pause()

            # Set up INSERT mode state directly
            app.query_input.focus()
            app.editor_mode = VimMode.INSERT
            app.query_input.read_only = False
            await pilot.pause()

            assert app.editor_mode == VimMode.INSERT

            # Exit with configured key
            await pilot.press(exit_key)
            await pilot.pause()

            assert app.editor_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_navigation_blocked_in_insert_mode(self):
        """Navigation keys should be blocked in INSERT mode."""
        keymap = get_keymap()
        focus_explorer_key = keymap.action("focus_explorer")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Wait for app to fully mount
            await pilot.pause()

            # Set up INSERT mode state directly
            app.query_input.focus()
            app.editor_mode = VimMode.INSERT
            app.query_input.read_only = False
            await pilot.pause()

            assert app.editor_mode == VimMode.INSERT
            assert app.query_input.has_focus

            # Try to navigate with focus explorer key - should NOT switch focus
            await pilot.press(focus_explorer_key)
            await pilot.pause()

            # Should still be in query with insert mode
            assert app.query_input.has_focus
            assert app.editor_mode == VimMode.INSERT
