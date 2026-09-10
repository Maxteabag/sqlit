"""Long-cell cropping must never truncate the stored SQL value."""
import pytest
from rich.text import Text
from textual.coordinate import Coordinate

from sqlit.shared.ui.widgets_tables import SqlitDataTable


@pytest.mark.parametrize("value", ["x" * 10000, "界" * 100, "e\u0301" * 100, "[bold]literal[/bold]" * 100, "🙂" * 100])
def test_long_literal_cell_is_bounded_but_backend_value_is_complete(value):
    table = SqlitDataTable(data=[(value,)], column_labels=["value"], render_markup=False)
    renderable = table._get_cell_renderable(0, 0, max_width=12)
    assert isinstance(renderable, Text)
    assert renderable.cell_len <= 12
    assert renderable.plain.endswith("…")
    assert table.get_cell_at(Coordinate(0, 0)) == value


def test_markup_cell_keeps_its_existing_formatting_path():
    table = SqlitDataTable(data=[("[bold]hello[/bold]",)], column_labels=["value"], render_markup=True)
    renderable = table._get_cell_renderable(0, 0, max_width=3)
    assert isinstance(renderable, Text)
    assert renderable.plain == "hello"
    assert renderable.spans
