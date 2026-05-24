"""Regression test for crash when rendering blobs containing markup-like text.

See https://github.com/.../issues/202: a PDF blob containing the substring
``[/ICCBased 14 0 R]`` crashed the results table because Rich interpreted the
brackets as a closing markup tag.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.ui.widgets_tables import SqlitDataTable

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


# A snippet of real PDF stream contents that triggered the original crash.
BLOB_WITH_MARKUP = b"%PDF-1.4\n[/ICCBased 14 0 R]\nstream..."


def test_format_cell_bytes_does_not_crash_rich_console():
    """Rendering the output of _format_cell on a bytes value must not raise MarkupError."""
    # _format_cell doesn't use self; call as unbound for a lightweight test.
    formatted = SqlitDataTable._format_cell(None, BLOB_WITH_MARKUP, None)  # type: ignore[arg-type]

    # Render through a Rich console the same way textual_fastdatatable does.
    console = Console(file=io.StringIO(), force_terminal=True, width=120)
    console.print(formatted)  # Must not raise rich.errors.MarkupError.


@pytest.mark.asyncio
async def test_results_table_renders_blob_with_markup_chars():
    """Displaying a row whose blob contains '[/...]' must not crash the table render."""
    connections = [create_test_connection("test-db", "sqlite")]
    services = build_test_services(
        connection_store=MockConnectionStore(connections),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    app = SSMSTUI(services=services)

    columns = ["id", "data"]
    rows = [(1, BLOB_WITH_MARKUP)]

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await app._display_query_results(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )

        # Force the render loop to actually paint the cell — that's where the
        # original crash happened, not at insert time.
        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == 1
