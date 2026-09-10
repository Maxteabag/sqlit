"""End-to-end pilot tests for the results-grid transpose toggle."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


def _make_app() -> SSMSTUI:
    connections = [create_test_connection("test-db", "sqlite")]
    services = build_test_services(
        connection_store=MockConnectionStore(connections),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


@pytest.mark.asyncio
async def test_toggle_transpose_swaps_and_restores_grid():
    app = _make_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await app._display_query_results(
            columns=["id", "name"],
            rows=[(1, "Ana"), (2, "Luis")],
            row_count=2,
            truncated=False,
            elapsed_ms=0,
        )
        await pilot.pause()

        assert app.results_table.row_count == 2
        assert [c.label.plain for c in app.results_table.ordered_columns] == ["id", "name"]

        app.action_toggle_transpose()
        await pilot.pause()

        assert app._results_transposed is True
        assert [c.label.plain for c in app.results_table.ordered_columns] == ["Column", "Row 1", "Row 2"]
        assert app.results_table.row_count == 2
        assert list(app.results_table.get_row_at(0)) == ["id", "1", "2"]
        assert list(app.results_table.get_row_at(1)) == ["name", "Ana", "Luis"]

        app.action_toggle_transpose()
        await pilot.pause()

        assert app._results_transposed is False
        assert [c.label.plain for c in app.results_table.ordered_columns] == ["id", "name"]
        assert list(app.results_table.get_row_at(0)) == [1, "Ana"]
        assert list(app.results_table.get_row_at(1)) == [2, "Luis"]


@pytest.mark.asyncio
async def test_new_query_results_reset_transpose_state():
    app = _make_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await app._display_query_results(
            columns=["id"], rows=[(1,), (2,)], row_count=2, truncated=False, elapsed_ms=0
        )
        await pilot.pause()

        app.action_toggle_transpose()
        await pilot.pause()
        assert app._results_transposed is True

        await app._display_query_results(
            columns=["id"], rows=[(3,), (4,)], row_count=2, truncated=False, elapsed_ms=0
        )
        await pilot.pause()

        assert app._results_transposed is False
        assert [c.label.plain for c in app.results_table.ordered_columns] == ["id"]


@pytest.mark.asyncio
async def test_toggle_transpose_stacked_mode_per_section():
    from sqlit.domains.query.app.multi_statement import MultiStatementResult, StatementResult
    from sqlit.domains.query.app.query_service import QueryResult
    from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

    app = _make_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        multi_result = MultiStatementResult(
            results=[
                StatementResult(
                    statement="SELECT 1",
                    result=QueryResult(columns=["id"], rows=[(1,), (2,)], row_count=2, truncated=False),
                    success=True,
                ),
                StatementResult(
                    statement="SELECT 2",
                    result=QueryResult(columns=["x"], rows=[(9,)], row_count=1, truncated=False),
                    success=True,
                ),
            ]
        )
        app._display_multi_statement_results(multi_result, elapsed_ms=0)
        await pilot.pause()

        container = app.query_one("#stacked-results", StackedResultsContainer)
        sections = list(container.query(ResultSection))
        assert len(sections) == 2
        first_section, second_section = sections
        first_section.query_one(app.results_table.__class__).focus()
        await pilot.pause()

        app.action_toggle_transpose()
        await pilot.pause()

        assert first_section.result_transposed is True
        assert second_section.result_transposed is False

        first_table = first_section.query_one(app.results_table.__class__)
        assert [c.label.plain for c in first_table.ordered_columns] == ["Column", "Row 1", "Row 2"]
        assert list(first_table.get_row_at(0)) == ["id", "1", "2"]

        second_table = second_section.query_one(app.results_table.__class__)
        assert [c.label.plain for c in second_table.ordered_columns] == ["x"]


@pytest.mark.asyncio
async def test_toggle_transpose_stacked_mode_preserves_focus_across_sections():
    """Each toggle must keep focus on the table just rebuilt, or the next `T` press
    silently targets whatever `_get_active_results_context()` falls back to instead
    of the section the user is actually looking at."""
    from sqlit.domains.query.app.multi_statement import MultiStatementResult, StatementResult
    from sqlit.domains.query.app.query_service import QueryResult
    from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

    app = _make_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        multi_result = MultiStatementResult(
            results=[
                StatementResult(
                    statement="SELECT 1",
                    result=QueryResult(columns=["id"], rows=[(1,), (2,)], row_count=2, truncated=False),
                    success=True,
                ),
                StatementResult(
                    statement="SELECT 2",
                    result=QueryResult(columns=["x"], rows=[(9,)], row_count=1, truncated=False),
                    success=True,
                ),
            ]
        )
        app._display_multi_statement_results(multi_result, elapsed_ms=0)
        await pilot.pause()

        container = app.query_one("#stacked-results", StackedResultsContainer)
        first_section, second_section = list(container.query(ResultSection))

        second_section.query_one(app.results_table.__class__).focus()
        await pilot.pause()

        app.action_toggle_transpose()
        await pilot.pause()
        app.action_toggle_transpose()
        await pilot.pause()

        assert second_section.result_transposed is False
        assert first_section.result_transposed is False


@pytest.mark.asyncio
async def test_view_cell_full_uses_transposed_column_label():
    """`action_view_cell_full` must label the value with the column actually under
    the cursor. While transposed, `_last_result_columns[cursor_col]` (the original,
    untransposed column list) is the wrong list to index - the cursor runs over
    Column/Row-N instead."""
    from sqlit.shared.ui.widgets import InlineValueView

    app = _make_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await app._display_query_results(
            columns=["id", "name"], rows=[(1, "Ana"), (2, "Luis")], row_count=2, truncated=False, elapsed_ms=0
        )
        await pilot.pause()

        app.action_toggle_transpose()
        await pilot.pause()

        app.action_view_cell_full()
        await pilot.pause()

        value_view = app.query_one("#value-view", InlineValueView)
        assert value_view._column_name == "Column"


@pytest.mark.asyncio
async def test_toggle_transpose_with_no_results_is_noop():
    app = _make_app()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        app.action_toggle_transpose()
        await pilot.pause()

        assert app._results_transposed is False
