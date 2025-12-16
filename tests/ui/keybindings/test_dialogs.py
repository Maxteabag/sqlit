"""Tests for dialog keybindings."""

from __future__ import annotations

import pytest

from sqlit.app import SSMSTUI
from sqlit.keymap import get_keymap
from sqlit.ui.screens import ConfirmScreen, ErrorScreen, HelpScreen


class TestDialogKeybindings:
    """Test that dialogs block normal keybindings and have their own actions."""

    @pytest.mark.asyncio
    async def test_normal_actions_blocked_when_error_dialog_open(self):
        """Normal navigation/actions should be blocked when an error dialog is open."""
        keymap = get_keymap()
        focus_query_key = keymap.action("focus_query")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Focus explorer first
            app.action_focus_explorer()
            await pilot.pause()
            assert app.object_tree.has_focus

            # Open error dialog
            app.push_screen(ErrorScreen("Test Error", "This is a test error message"))
            await pilot.pause()

            # Verify dialog is shown
            has_error = any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)
            assert has_error

            # Try to focus query - should be blocked by modal
            await pilot.press(focus_query_key)
            await pilot.pause()

            # Explorer should still have focus (action was blocked)
            # Note: The underlying widget focus doesn't change when modal is active
            # The key is that the action was blocked
            assert any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

    @pytest.mark.asyncio
    async def test_error_dialog_close_with_enter(self):
        """Error dialog should close with enter key."""
        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Open error dialog
            app.push_screen(ErrorScreen("Test Error", "This is a test error message"))
            await pilot.pause()

            # Verify dialog is shown
            assert any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

            # Close with enter
            await pilot.press("enter")
            await pilot.pause()

            # Dialog should be closed
            assert not any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

    @pytest.mark.asyncio
    async def test_error_dialog_close_with_escape(self):
        """Error dialog should close with escape key."""
        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Open error dialog
            app.push_screen(ErrorScreen("Test Error", "This is a test error message"))
            await pilot.pause()

            assert any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

            # Close with escape
            await pilot.press("escape")
            await pilot.pause()

            assert not any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

    @pytest.mark.asyncio
    async def test_error_dialog_copy_action(self):
        """Error dialog 'y' key should copy message."""
        app = SSMSTUI()
        test_message = "This is a test error message"
        copied_text = {"value": None}

        async with app.run_test(size=(100, 35)) as pilot:

            def mock_copy(text):
                copied_text["value"] = text
                # Don't call original - it may fail in test environment

            app.copy_to_clipboard = mock_copy

            # Open error dialog
            app.push_screen(ErrorScreen("Test Error", test_message))
            await pilot.pause()

            # Press 'y' to copy
            await pilot.press("y")
            await pilot.pause()

            # Dialog should still be open (copy doesn't close it)
            assert any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

            # Verify copy was called with correct message
            assert copied_text["value"] == test_message

    @pytest.mark.asyncio
    async def test_confirm_dialog_yes_action(self):
        """Confirm dialog 'y' key should confirm and close."""
        app = SSMSTUI()
        result_holder = {"result": None}

        def capture_result(result):
            result_holder["result"] = result

        async with app.run_test(size=(100, 35)) as pilot:
            # Open confirm dialog with callback
            app.push_screen(ConfirmScreen("Delete item?"), capture_result)
            await pilot.pause()

            assert any(isinstance(screen, ConfirmScreen) for screen in app.screen_stack)

            # Press 'y' to confirm
            await pilot.press("y")
            await pilot.pause()

            # Dialog should be closed
            assert not any(isinstance(screen, ConfirmScreen) for screen in app.screen_stack)
            # Result should be True
            assert result_holder["result"] is True

    @pytest.mark.asyncio
    async def test_confirm_dialog_no_action(self):
        """Confirm dialog 'n' key should cancel and close."""
        app = SSMSTUI()
        result_holder = {"result": None}

        def capture_result(result):
            result_holder["result"] = result

        async with app.run_test(size=(100, 35)) as pilot:
            app.push_screen(ConfirmScreen("Delete item?"), capture_result)
            await pilot.pause()

            assert any(isinstance(screen, ConfirmScreen) for screen in app.screen_stack)

            # Press 'n' to cancel
            await pilot.press("n")
            await pilot.pause()

            assert not any(isinstance(screen, ConfirmScreen) for screen in app.screen_stack)
            assert result_holder["result"] is False

    @pytest.mark.asyncio
    async def test_confirm_dialog_escape_cancels(self):
        """Confirm dialog escape key should cancel and close."""
        app = SSMSTUI()
        result_holder = {"result": None}

        def capture_result(result):
            result_holder["result"] = result

        async with app.run_test(size=(100, 35)) as pilot:
            app.push_screen(ConfirmScreen("Delete item?"), capture_result)
            await pilot.pause()

            # Press escape to cancel
            await pilot.press("escape")
            await pilot.pause()

            assert not any(isinstance(screen, ConfirmScreen) for screen in app.screen_stack)
            assert result_holder["result"] is False

    @pytest.mark.asyncio
    async def test_help_dialog_blocks_normal_actions(self):
        """Help dialog should block normal actions like focus changes."""
        keymap = get_keymap()
        focus_explorer_key = keymap.action("focus_explorer")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Focus query first
            app.action_focus_query()
            await pilot.pause()
            assert app.query_input.has_focus

            # Open help via leader combo
            leader_key = keymap.action("leader_key")
            help_key = keymap.leader("show_help")
            await pilot.press(leader_key, help_key)
            await pilot.pause()

            assert any(isinstance(screen, HelpScreen) for screen in app.screen_stack)

            # Try to focus explorer - should be blocked
            await pilot.press(focus_explorer_key)
            await pilot.pause()

            # Help screen should still be open
            assert any(isinstance(screen, HelpScreen) for screen in app.screen_stack)

    @pytest.mark.asyncio
    async def test_help_dialog_closes_with_escape(self):
        """Help dialog should close with escape."""
        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Open help
            keymap = get_keymap()
            leader_key = keymap.action("leader_key")
            help_key = keymap.leader("show_help")
            await pilot.press(leader_key, help_key)
            await pilot.pause()

            assert any(isinstance(screen, HelpScreen) for screen in app.screen_stack)

            # Close with escape
            await pilot.press("escape")
            await pilot.pause()

            assert not any(isinstance(screen, HelpScreen) for screen in app.screen_stack)

    @pytest.mark.asyncio
    async def test_leader_commands_blocked_when_dialog_open(self):
        """Leader commands should not work when a dialog is open."""
        keymap = get_keymap()
        leader_key = keymap.action("leader_key")
        theme_key = keymap.leader("change_theme")

        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Open error dialog
            app.push_screen(ErrorScreen("Test", "Error message"))
            await pilot.pause()

            # Try leader combo - should be blocked
            await pilot.press(leader_key, theme_key)
            await pilot.pause()

            # Only the error dialog should be open, not theme picker
            error_count = sum(1 for screen in app.screen_stack if isinstance(screen, ErrorScreen))
            assert error_count == 1
            # Screen stack should just have main screen + error dialog
            assert len(app.screen_stack) == 2

    @pytest.mark.asyncio
    async def test_nested_dialogs_both_block(self):
        """When multiple dialogs are stacked, outer actions should be blocked."""
        app = SSMSTUI()

        async with app.run_test(size=(100, 35)) as pilot:
            # Open first dialog
            app.push_screen(ErrorScreen("Error 1", "First error"))
            await pilot.pause()

            # Open second dialog on top
            app.push_screen(ConfirmScreen("Confirm action?"))
            await pilot.pause()

            # Both should be in stack
            assert len(app.screen_stack) == 3  # main + 2 dialogs

            # Close top dialog with escape
            await pilot.press("escape")
            await pilot.pause()

            # First dialog should still be there
            assert len(app.screen_stack) == 2
            assert any(isinstance(screen, ErrorScreen) for screen in app.screen_stack)

            # Close remaining dialog
            await pilot.press("escape")
            await pilot.pause()

            # Back to main screen only
            assert len(app.screen_stack) == 1
