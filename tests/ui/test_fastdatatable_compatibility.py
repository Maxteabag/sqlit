"""Compatibility coverage for textual-fastdatatable's rendering hooks."""

import pytest
from textual.app import App, ComposeResult

from sqlit.shared.ui.widgets_tables import SqlitDataTable


class _TableApp(App[None]):
    def __init__(self, table: SqlitDataTable) -> None:
        super().__init__()
        self.table = table

    def compose(self) -> ComposeResult:
        yield self.table


def test_cell_renderable_accepts_width_from_fastdatatable_019() -> None:
    """0.19 passes the available width to subclass cell renderers."""
    table = SqlitDataTable(data={"id": [1]})

    renderable = table._get_cell_renderable(-1, 0, max_width=10)

    assert getattr(renderable, "plain", renderable) == "id"


@pytest.mark.asyncio
async def test_table_renders_with_fastdatatable_019_width_argument() -> None:
    """Rendering a result table must not crash when 0.19 supplies max_width."""
    table = SqlitDataTable(data={"id": list(range(100))})

    async with _TableApp(table).run_test(size=(40, 10)):
        assert "id" in table.render_line(0).text
