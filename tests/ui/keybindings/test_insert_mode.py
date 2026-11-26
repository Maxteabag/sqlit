"""Tests for keybindings in vim INSERT mode."""

from __future__ import annotations

import pytest
from textual.messages import TerminalSupportsSynchronizedOutput

from sqlit.core.keymap import get_keymap
from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestInsertModeKeybindings:
    """Test keybindings in vim INSERT mode."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("synchronized", [False, True])
    async def test_insert_cursor_during_typing(self, synchronized: bool, monkeypatch: pytest.MonkeyPatch) -> None:
        app = _make_app()
        async with app.run_test() as pilot:
            app.action_focus_query()
            app.query_input.cursor_blink = False
            if synchronized:
                app.post_message(TerminalSupportsSynchronizedOutput())
            await pilot.pause()

            writes: list[str] = []
            monkeypatch.setattr(app._driver, "write", writes.append)
            await pilot.press("i", "x")
            assert app.query_input.text == "x"
            assert ("\x1b[?25h" in "".join(writes)) == synchronized
            assert app.query_input._draw_cursor == (not synchronized)

            if not synchronized:
                # A late terminal reply must not hide the cursor between frames.
                app.post_message(TerminalSupportsSynchronizedOutput())
                await pilot.pause()
                assert app.query_input._draw_cursor

            writes.clear()
            await pilot.press("escape")
            assert ("\x1b[?25l" in "".join(writes)) == synchronized
            assert app.query_input._draw_cursor

    @pytest.mark.asyncio
    async def test_enter_insert_mode_key(self):
        """Enter insert mode key should enter INSERT mode when in query normal mode."""
        keymap = get_keymap()
        insert_key = keymap.action("enter_insert_mode")

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL

            await pilot.press(insert_key)
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_exit_insert_mode_key(self):
        """Exit insert mode key should exit INSERT mode."""
        keymap = get_keymap()
        exit_key = keymap.action("exit_insert_mode")

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Enter insert mode
            app.action_enter_insert_mode()
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT

            # Exit with configured key
            await pilot.press(exit_key)
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_navigation_blocked_in_insert_mode(self):
        """Navigation keys should be blocked in INSERT mode."""
        keymap = get_keymap()
        focus_explorer_key = keymap.action("focus_explorer")

        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Enter insert mode
            app.action_enter_insert_mode()
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.has_focus

            # Try to navigate with focus explorer key - should NOT switch focus
            await pilot.press(focus_explorer_key)
            await pilot.pause()

            # Should still be in query with insert mode
            assert app.query_input.has_focus
            assert app.vim_mode == VimMode.INSERT
