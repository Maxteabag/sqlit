"""Regression tests for issue #229 - Rich markup leaking into copied cells.

When the results filter is active, cells are stored in the table with Rich
markup (e.g. `[bold #FFFF00]Ja[/]ne`). Copy actions used to feed that markup
straight to the clipboard. These tests drive `action_copy_cell` / _row through
their public entry points against a fake table that mimics the filter state,
so they fail without the fix and pass with it.
"""

from __future__ import annotations

from typing import Any

import pytest

from sqlit.domains.results.ui.mixins.results import ResultsMixin


class _FakeTable:
    def __init__(self, cells: list[tuple[str, ...]], render_markup: bool) -> None:
        self._cells = cells
        self.row_count = len(cells)
        self.render_markup = render_markup
        self.cursor_row = 0
        self.cursor_coordinate = (0, 0)

    def get_cell_at(self, coord: Any) -> Any:
        if isinstance(coord, tuple):
            row, col = coord
        else:
            row, col = coord.row, coord.column
        return self._cells[row][col]

    def get_row_at(self, row: int) -> list[Any]:
        return list(self._cells[row])


class _FakeApp(ResultsMixin):
    """Just enough harness to exercise the copy actions without Textual."""

    def __init__(self, cells: list[tuple[str, ...]], *, render_markup: bool = True) -> None:
        self._table = _FakeTable(cells, render_markup=render_markup)
        self.clipboard_text: str | None = None

    def _get_active_results_context(self) -> tuple[Any, list, list, bool]:
        return self._table, [], [], False

    def _copy_text(self, text: str) -> bool:  # type: ignore[override]
        self.clipboard_text = text
        return True

    def _flash_table_yank(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def notify(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def _clear_leader_pending(self) -> None:
        pass


@pytest.mark.parametrize(
    "action_name",
    ["action_copy_cell", "action_ry_cell"],
)
def test_copy_cell_strips_filter_markup(action_name: str) -> None:
    app = _FakeApp([("[bold #FFFF00]Ja[/]ne",)])
    getattr(app, action_name)()
    assert app.clipboard_text == "Jane"


@pytest.mark.parametrize(
    "action_name",
    ["action_copy_row", "action_ry_row"],
)
def test_copy_row_strips_filter_markup(action_name: str) -> None:
    app = _FakeApp([("[bold #FFFF00]Ja[/]ne", "Doe")])
    getattr(app, action_name)()
    assert app.clipboard_text == "Jane\tDoe"


def test_copy_cell_preserves_literal_brackets_when_not_rendering_markup() -> None:
    # When the table is in plain mode, cells are stored verbatim. We must NOT
    # treat brackets as markup, or legitimate data like "[bold]hi" gets eaten.
    app = _FakeApp([("[bold]hello",)], render_markup=False)
    app.action_copy_cell()
    assert app.clipboard_text == "[bold]hello"
