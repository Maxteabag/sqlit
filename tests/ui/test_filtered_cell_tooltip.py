"""Cell previews must preserve values without leaking filter highlighting."""

from __future__ import annotations

import pytest
from rich.text import Text
from textual.coordinate import Coordinate

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import (
    MockConnectionStore,
    MockSettingsStore,
    build_test_services,
    create_test_connection,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("filtered", [False, True], ids=["unfiltered", "filtered"])
@pytest.mark.parametrize(
    "payload,search",
    [("Jane", "Ja"), ('{"path": "[/api/v1]", "name": "Jane"}', "Jane")],
    ids=["plain-text", "bracketed-json"],
)
async def test_cell_preview_preserves_original_value(payload: str, search: str, filtered: bool) -> None:
    connection = create_test_connection("test-db", "sqlite")
    services = build_test_services(
        connection_store=MockConnectionStore([connection]),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await app._display_query_results(
            columns=["payload"], rows=[(payload,)], row_count=1,
            truncated=False, elapsed_ms=0,
        )
        await pilot.pause()
        app.results_table.focus()
        if filtered:
            await pilot.press("slash")
            assert app._results_filter_visible
            await pilot.press(*search)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert not app._results_filter_visible
            assert app.results_table.render_markup

        app.results_table.cursor_coordinate = Coordinate(0, 0)
        await pilot.press("v")
        await pilot.pause()
        assert app._tooltip_showing
        tooltip = app.results_table.tooltip
        assert tooltip is not None
        # Textual renders string tooltips as markup, but Text values literally.
        preview = tooltip.plain if isinstance(tooltip, Text) else Text.from_markup(tooltip).plain
        assert preview == payload
