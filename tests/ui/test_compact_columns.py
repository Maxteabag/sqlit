"""Leader+w sizes result columns to the average value width instead of the widest."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import (
    MockConnectionStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)

# One long outlier among short values: full width follows the outlier,
# compact width follows the typical value.
ROWS = [(i, "ab", "x" * 60 if i == 0 else "short") for i in range(10)]


def _widths(app: SSMSTUI) -> list[int]:
    return [column.render_width for column in app.results_table.ordered_columns]


async def _show_results(app: SSMSTUI, pilot) -> None:
    await app._display_query_results(
        columns=["id", "code", "description"], rows=ROWS, row_count=len(ROWS),
        truncated=False, elapsed_ms=0,
    )
    await pilot.pause()


@pytest.mark.asyncio
async def test_leader_w_toggles_compact_columns_and_persists_for_new_results() -> None:
    connection = create_test_connection("test-db", "sqlite")
    services = build_test_services(
        connection_store=MockConnectionStore([connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await _show_results(app, pilot)
        app.results_table.focus()
        await pilot.pause()
        full = _widths(app)
        assert full[2] == 60 + 2

        await pilot.press("space", "w")
        await pilot.pause()
        assert app.results_compact_columns
        compact = _widths(app)
        # description: (60 + 9 * 5) / 10 -> 11 cells; short data keeps its header readable.
        assert compact[2] == 11 + 2
        assert compact[1] == len("code") + 2
        assert compact[0] == full[0]  # never wider than its full width
        assert app.results_table.virtual_size.width == sum(compact)

        # A new query result keeps the compact layout.
        await _show_results(app, pilot)
        assert _widths(app) == compact

        app.results_table.focus()
        await pilot.press("space", "w")
        await pilot.pause()
        assert not app.results_compact_columns
        assert _widths(app) == full
