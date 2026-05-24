"""UI tests for vim motion keybindings in the results table (issue #170)."""

from __future__ import annotations

from typing import Any

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


async def _populate_results(pilot: Any, app: SSMSTUI, columns: list[str], rows: list[tuple]) -> None:
    """Display a set of results on the app and focus the results table."""
    # Wait for the Lazy-loaded results table to exist.
    await pilot.pause()
    await app._display_query_results(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=False,
        elapsed_ms=0,
    )
    # Let any incremental render timers run.
    for _ in range(3):
        await pilot.pause(0.05)
    app.action_focus_results()
    await pilot.pause()


class TestResultsVimMotions:
    """Vim motions bound to the results view."""

    @pytest.mark.asyncio
    async def test_G_jumps_to_last_row_preserving_column(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            columns = ["id", "name", "email"]
            rows = [(i, f"row-{i}", f"e{i}@x") for i in range(20)]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            # Move to column 2 first, then jump to end.
            await pilot.press("l", "l")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == 2

            await pilot.press("G")
            await pilot.pause()

            assert app.results_table.cursor_coordinate.row == len(rows) - 1
            assert app.results_table.cursor_coordinate.column == 2

    @pytest.mark.asyncio
    async def test_gg_jumps_to_first_row_preserving_column(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            columns = ["id", "name", "email"]
            rows = [(i, f"row-{i}", f"e{i}@x") for i in range(20)]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            await pilot.press("l", "l")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == 2

            await pilot.press("G")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.row == len(rows) - 1

            await pilot.press("g")
            await pilot.press("g")
            await pilot.pause()

            assert app.results_table.cursor_coordinate.row == 0
            assert app.results_table.cursor_coordinate.column == 2

    @pytest.mark.asyncio
    async def test_ctrl_d_and_ctrl_u_page_preserve_column(self) -> None:
        app = _make_app()
        async with app.run_test(size=(100, 20)) as pilot:
            columns = ["id", "a", "b"]
            rows = [(i, i * 2, i * 3) for i in range(200)]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            await pilot.press("l")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == 1
            start_row = app.results_table.cursor_coordinate.row

            await pilot.press("ctrl+d")
            await pilot.pause()
            after_page_down = app.results_table.cursor_coordinate.row
            assert after_page_down > start_row, "ctrl+d should move cursor down by a page"
            assert app.results_table.cursor_coordinate.column == 1

            await pilot.press("ctrl+u")
            await pilot.pause()
            after_page_up = app.results_table.cursor_coordinate.row
            assert after_page_up < after_page_down, "ctrl+u should move cursor up again"
            assert app.results_table.cursor_coordinate.column == 1

    @pytest.mark.asyncio
    async def test_0_and_dollar_move_within_row(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 35)) as pilot:
            columns = ["a", "b", "c", "d", "e"]
            rows = [(1, 2, 3, 4, 5), (6, 7, 8, 9, 10)]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            await pilot.press("l")
            await pilot.press("l")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == 2

            await pilot.press("dollar_sign")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == len(columns) - 1

            await pilot.press("0")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == 0

    @pytest.mark.asyncio
    async def test_f_opens_column_picker_and_jumps(self) -> None:
        from sqlit.domains.results.ui.screens import ColumnPickerScreen

        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            columns = ["id", "first_name", "last_name", "email", "created_at"]
            rows = [(i, f"first{i}", f"last{i}", f"e{i}@x", f"2024-0{i}") for i in range(3)]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            assert app.results_table.cursor_coordinate.column == 0

            await pilot.press("f")
            await pilot.pause()

            assert isinstance(app.screen, ColumnPickerScreen)

            await pilot.press("e", "m", "a", "i")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert app.results_table.cursor_coordinate.column == columns.index("email")

    @pytest.mark.asyncio
    async def test_F_also_opens_column_picker(self) -> None:
        from sqlit.domains.results.ui.screens import ColumnPickerScreen

        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            columns = ["id", "name"]
            rows = [(1, "a"), (2, "b")]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            await pilot.press("F")
            await pilot.pause()

            assert isinstance(app.screen, ColumnPickerScreen)

    @pytest.mark.asyncio
    async def test_column_picker_escape_cancels(self) -> None:
        from sqlit.domains.results.ui.screens import ColumnPickerScreen

        app = _make_app()
        async with app.run_test(size=(100, 35)) as pilot:
            columns = ["id", "name"]
            rows = [(1, "a"), (2, "b")]
            await _populate_results(pilot, app, columns, rows)
            await pilot.pause()

            await pilot.press("l")
            await pilot.pause()
            assert app.results_table.cursor_coordinate.column == 1

            await pilot.press("f")
            await pilot.pause()
            assert isinstance(app.screen, ColumnPickerScreen)

            await pilot.press("escape")
            await pilot.pause()

            assert not isinstance(app.screen, ColumnPickerScreen)
            assert app.results_table.cursor_coordinate.column == 1
