"""UI tests for vim visual mode keybindings in the query editor."""

from __future__ import annotations

import pytest

from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services

SAMPLE_TEXT = "select\n  foo,\n  bar,\n  baz\nfrom foo\nwhere 1=1"


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestEnterExitVisualMode:
    """Test entering and exiting visual modes."""

    @pytest.mark.asyncio
    async def test_v_enters_visual_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (0, 3)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

    @pytest.mark.asyncio
    async def test_V_enters_visual_line_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (0, 3)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

    @pytest.mark.asyncio
    async def test_escape_exits_visual_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

            await pilot.press("escape")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_escape_exits_visual_line_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

            await pilot.press("escape")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_v_exits_visual_mode(self) -> None:
        """Pressing v again in visual mode should exit."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_V_exits_visual_line_mode(self) -> None:
        """Pressing V again in visual line mode should exit."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL


class TestVisualModeToggle:
    """Test toggling between visual and visual line modes."""

    @pytest.mark.asyncio
    async def test_V_in_visual_switches_to_visual_line(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

    @pytest.mark.asyncio
    async def test_v_in_visual_line_switches_to_visual(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL_LINE

            await pilot.press("v")
            await pilot.pause()
            assert app.vim_mode == VimMode.VISUAL


class TestVisualModeMotions:
    """Test that motions extend selection in visual mode."""

    @pytest.mark.asyncio
    async def test_visual_mode_h_l_movement(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 5)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("l")
            await pilot.pause()

            sel = app.query_input.selection
            assert sel.start != sel.end, "Selection should be non-empty after motion"

    @pytest.mark.asyncio
    async def test_visual_mode_w_extends_selection(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            sel = app.query_input.selection
            assert sel.start != sel.end
            assert app.vim_mode == VimMode.VISUAL

    @pytest.mark.asyncio
    async def test_visual_line_mode_j_k_movement(self) -> None:
        """j/k should extend selection by full lines in visual line mode."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            # Move down
            await pilot.press("j")
            await pilot.pause()

            sel = app.query_input.selection
            start, end = min(sel.start, sel.end), max(sel.start, sel.end)
            # Should span from row 1 col 0 to row 2 end
            assert start[0] == 1
            assert start[1] == 0
            assert end[0] == 2

            # Move back up
            await pilot.press("k")
            await pilot.pause()

            sel = app.query_input.selection
            start, end = min(sel.start, sel.end), max(sel.start, sel.end)
            assert start[0] == 1
            assert end[0] == 1

    @pytest.mark.asyncio
    async def test_visual_line_mode_G_extends_to_end(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = SAMPLE_TEXT
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("G")
            await pilot.pause()

            sel = app.query_input.selection
            start, end = min(sel.start, sel.end), max(sel.start, sel.end)
            assert start[0] == 0
            last_row = SAMPLE_TEXT.count("\n")
            assert end[0] == last_row


class TestVisualModeOperators:
    """Test operators (y, d, c) in visual modes."""

    @pytest.mark.asyncio
    async def test_visual_yank(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            # Select "hello w" — w moves to col 6, inclusive of cursor char
            await pilot.press("w")
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._internal_clipboard == "hello w"
            # Text should be unchanged
            assert app.query_input.text == "hello world"

    @pytest.mark.asyncio
    async def test_visual_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.text == "orld"

    @pytest.mark.asyncio
    async def test_visual_change_enters_insert(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.text == "orld"

    @pytest.mark.asyncio
    async def test_visual_line_yank(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 0)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("y")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._internal_clipboard == "beta"
            assert app.query_input.text == "alpha\nbeta\ngamma"

    @pytest.mark.asyncio
    async def test_visual_line_delete(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.text == "alpha\ngamma"

    @pytest.mark.asyncio
    async def test_visual_line_delete_multiple_lines(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma\ndelta"
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()

            await pilot.press("d")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app.query_input.text == "alpha\ndelta"

    @pytest.mark.asyncio
    async def test_visual_line_change_enters_insert(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 0)
            await pilot.pause()

            await pilot.press("V")
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()

            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.text == "alpha\ngamma"
