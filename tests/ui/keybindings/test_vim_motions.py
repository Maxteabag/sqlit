"""UI tests for vim motion keybindings in the query editor."""

from __future__ import annotations

import pytest

from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestVimMotionKeybindings:
    """Test vim motion keybindings in NORMAL mode."""

    @pytest.mark.asyncio
    async def test_word_motions_w_W_b_B(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "foo-bar baz"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("w")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 4)

            await pilot.press("W")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 8)

            await pilot.press("b")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 4)

            await pilot.press("B")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_line_motions_0_dollar_G(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            lines = "SELECT * FROM cats\nSELECT * FROM dogs"
            app.query_input.text = lines
            app.query_input.cursor_location = (0, 7)
            await pilot.pause()

            await pilot.press("0")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

            await pilot.press("$")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, len("SELECT * FROM cats"))

            await pilot.press("G")
            await pilot.pause()
            assert app.query_input.cursor_location == (1, 0)

    @pytest.mark.asyncio
    async def test_find_char_motions_f_F(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            line = "select cat catalog"
            app.query_input.text = line
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("f")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 4)

            app.query_input.cursor_location = (0, len(line))
            await pilot.pause()

            await pilot.press("F")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 11)

    @pytest.mark.asyncio
    async def test_till_char_motions_t_T(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            line = "select cat catalog"
            app.query_input.text = line
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("t")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 3)

            line_back = "abcdeabc"
            app.query_input.text = line_back
            app.query_input.cursor_location = (0, len(line_back) - 1)
            await pilot.pause()

            await pilot.press("T")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 6)

    @pytest.mark.asyncio
    async def test_matching_bracket_motion(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "(cats)"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("%")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 5)

    @pytest.mark.asyncio
    async def test_go_to_first_line_gg(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT 1\nSELECT 2\nSELECT 3"
            app.query_input.cursor_location = (2, 4)
            await pilot.pause()

            await pilot.press("g", "g")
            await pilot.pause()
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_change_to_line_end_c_dollar(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT * FROM cats"
            app.query_input.cursor_location = (0, 7)
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL

            await pilot.press("c")
            await pilot.pause()
            await pilot.press("$")
            await pilot.pause()

            assert app.query_input.text == "SELECT "
            assert app.query_input.cursor_location == (0, 7)
            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_delete_word_dw(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("d", "w")
            await pilot.pause()

            assert app.query_input.text == "world"
            assert app.query_input.cursor_location == (0, 0)
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_yank_to_line_end_y_dollar(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "SELECT * FROM cats"
            app.query_input.cursor_location = (0, 7)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("y", "$")
            await pilot.pause()

            assert app._internal_clipboard == "* FROM cats"

    @pytest.mark.asyncio
    async def test_delete_to_line_start_d0(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("d", "0")
            await pilot.pause()

            assert app.query_input.text == "world"
            assert app.query_input.cursor_location == (0, 0)

    @pytest.mark.asyncio
    async def test_yank_to_end_y_G(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha\nbeta\ngamma"
            app.query_input.cursor_location = (1, 2)
            app._internal_clipboard = ""
            await pilot.pause()

            await pilot.press("y", "G")
            await pilot.pause()

            assert app._internal_clipboard == "beta\ngamma"

    @pytest.mark.asyncio
    async def test_delete_inside_word_diw(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha beta"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("d", "i")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()

            assert app.query_input.text == "alpha "
            assert app.vim_mode == VimMode.NORMAL

    @pytest.mark.asyncio
    async def test_delete_around_word_daw(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha beta gamma"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("d", "a")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()

            assert app.query_input.text == "alpha gamma"

    @pytest.mark.asyncio
    async def test_change_inside_word_ciw(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "alpha beta"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("c", "i")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()

            assert app.query_input.text == "alpha "
            assert app.query_input.cursor_location == (0, 6)
            assert app.vim_mode == VimMode.INSERT

    @pytest.mark.asyncio
    async def test_delete_inside_quotes_di_quote(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = 'SELECT "cat" AS name'
            app.query_input.cursor_location = (0, 9)
            await pilot.pause()

            await pilot.press("d", "i")
            await pilot.pause()
            await pilot.press('"')
            await pilot.pause()

            assert app.query_input.text == 'SELECT "" AS name'
            assert app.query_input.cursor_location == (0, 8)

    @pytest.mark.asyncio
    async def test_delete_inside_parens_di_paren(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "func(call(arg))"
            app.query_input.cursor_location = (0, 11)
            await pilot.pause()

            await pilot.press("d", "i")
            await pilot.pause()
            await pilot.press("(")
            await pilot.pause()

            assert app.query_input.text == "func(call())"

    # ========================================================================
    # Count prefix tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_5j_moves_down_5_lines(self) -> None:
        """5j should move cursor down 5 lines."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "line1\nline2\nline3\nline4\nline5\nline6\nline7"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            # Press 5 then j
            await pilot.press("5")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 5, f"Expected row 5, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_3k_moves_up_3_lines(self) -> None:
        """3k should move cursor up 3 lines."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "line1\nline2\nline3\nline4\nline5"
            app.query_input.cursor_location = (4, 0)  # Start at line 5
            await pilot.pause()

            await pilot.press("3")
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 1, f"Expected row 1, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_2w_moves_forward_2_words(self) -> None:
        """2w should move cursor forward 2 words."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world goodbye"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("2")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()

            # After 2w: hello(0) -> world(6) -> goodbye(12)
            assert app.query_input.cursor_location == (0, 12), f"Expected (0, 12), got {app.query_input.cursor_location}"

    @pytest.mark.asyncio
    async def test_dw_on_semicolon_delimited_string(self) -> None:
        """dw on 'hey;hello;whatsup' should delete 'hey;' (w skips word + punctuation)."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hey;hello;whatsup"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("d", "w")
            await pilot.pause()

            # dw deletes "hey;" - w motion skips word chars then punctuation to next word
            assert app.query_input.text == "hello;whatsup", f"Got: {app.query_input.text}"

    @pytest.mark.asyncio
    async def test_2dw_on_semicolon_delimited_string(self) -> None:
        """2dw on 'hey;hello;whatsup' should delete 2 words."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hey;hello;whatsup"
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            # Use 2dw (count before operator) instead of d2w
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("d", "w")
            await pilot.pause()

            # "hey;hello;whatsup"
            #  01234567890123456
            # w from 0 -> 4 ("hello"), w from 4 -> 10 ("whatsup")
            # 2dw deletes "hey;hello;" resulting in "whatsup"
            assert app.query_input.text == "whatsup", f"Got: {app.query_input.text}"

    @pytest.mark.asyncio
    async def test_3dd_deletes_3_lines(self) -> None:
        """3dd should delete 3 lines starting from current line."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "line1\nline2\nline3\nline4\nline5"
            app.query_input.cursor_location = (1, 0)  # Start at line2
            await pilot.pause()

            await pilot.press("3")
            await pilot.pause()
            await pilot.press("d", "d")
            await pilot.pause()

            # Should delete line2, line3, line4
            assert app.query_input.text == "line1\nline5", f"Got: {app.query_input.text}"

    @pytest.mark.asyncio
    async def test_25G_goes_to_line_25(self) -> None:
        """25G should go to line 25."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 30 lines
            lines = [f"line{i+1}" for i in range(30)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("2", "5")
            await pilot.pause()
            await pilot.press("G")
            await pilot.pause()

            # 25G goes to line 25 (0-indexed: row 24)
            assert app.query_input.cursor_location[0] == 24, f"Expected row 24, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_colon_25_goes_to_line_25(self) -> None:
        """:25 command should go to line 25."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 30 lines
            lines = [f"line{i+1}" for i in range(30)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            # Type :25 and press enter
            await pilot.press(":")
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("5")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # :25 goes to line 25 (0-indexed: row 24)
            assert app.query_input.cursor_location[0] == 24, f"Expected row 24, got {app.query_input.cursor_location[0]}"

    @pytest.mark.asyncio
    async def test_zero_alone_goes_to_line_start(self) -> None:
        """0 alone should go to line start, not be treated as count."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "hello world"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("0")
            await pilot.pause()

            assert app.query_input.cursor_location == (0, 0), f"Expected (0, 0), got {app.query_input.cursor_location}"

    @pytest.mark.asyncio
    async def test_10j_works_with_zero_in_count(self) -> None:
        """10j should move down 10 lines (0 appends to count)."""
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            # Create 15 lines
            lines = [f"line{i+1}" for i in range(15)]
            app.query_input.text = "\n".join(lines)
            app.query_input.cursor_location = (0, 0)
            await pilot.pause()

            await pilot.press("1", "0")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()

            assert app.query_input.cursor_location[0] == 10, f"Expected row 10, got {app.query_input.cursor_location[0]}"
