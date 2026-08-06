"""Regression tests for issue #229 - Rich markup leaking into copied cells.

When the results filter is active, cells are stored in the table with Rich
markup (e.g. `[bold #FFFF00]Ja[/]ne`). Copy actions used to feed that markup
straight to the clipboard. These tests drive `action_copy_cell` / _row through
their public entry points against a fake table that mimics the filter state,
so they fail without the fix and pass with it.
"""

from __future__ import annotations

from types import SimpleNamespace
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


class _FakeQueryInput:
    def __init__(self) -> None:
        self.text = ""
        self.cursor_location = (0, 0)
        self.read_only = True

    def focus(self) -> None:
        pass


class _FakeEditApp(_FakeApp):
    def __init__(self, cells: list[tuple[str, ...]], columns: list[str]) -> None:
        super().__init__(cells, render_markup=True)
        self._columns = columns
        self.query_input = _FakeQueryInput()
        self._suppress_autocomplete_once = False
        self.current_provider = SimpleNamespace(
            dialect=SimpleNamespace(qualified_name=lambda database, schema, name: name),
        )

    def _get_active_results_context(self) -> tuple[Any, list, list, bool]:
        return self._table, self._columns, [], False

    def _get_active_results_table_info(self, _table: Any, _stacked: bool) -> dict[str, Any]:
        return {"name": "users", "columns": []}

    def action_focus_query(self) -> None:
        pass

    def _update_footer_bindings(self) -> None:
        pass

    def _update_vim_mode_visuals(self) -> None:
        pass


def test_delete_row_strips_filter_markup_before_generating_sql() -> None:
    app = _FakeEditApp([("[bold #FFFF00]Ja[/]ne",)], ["name"])
    app.action_delete_row()
    assert app.query_input.text == "DELETE FROM users WHERE name = 'Jane';"


def test_edit_cell_strips_filter_markup_before_generating_sql() -> None:
    app = _FakeEditApp([("[bold #FFFF00]Ja[/]ne",)], ["name"])
    app.action_edit_cell()
    assert "WHERE name = 'Jane';" in app.query_input.text
