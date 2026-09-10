"""Tests for the results-grid transpose (columns-as-rows) toggle."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlit.domains.results.ui.mixins.results import MAX_TRANSPOSE_ROWS, ResultsMixin, _transpose_result_data


class _FakeTable:
    def __init__(self, row_count: int, cursor_coordinate: tuple[int, int] = (0, 0)) -> None:
        self.row_count = row_count
        self.cursor_coordinate = cursor_coordinate

    @property
    def cursor_row(self) -> int:
        return self.cursor_coordinate[0]

    def get_cell_at(self, _coord: Any) -> Any:
        return "cell-value"

    def get_row_at(self, _row: int) -> list[Any]:
        return ["row-value"]


class _FakeApp(ResultsMixin):
    """Just enough harness to exercise action_toggle_transpose without Textual."""

    def __init__(
        self,
        columns: list[str],
        rows: list[tuple[Any, ...]],
        *,
        stacked: bool = False,
        section: Any = None,
        table_row_count: int | None = None,
    ) -> None:
        self._columns = columns
        self._rows = rows
        self._stacked = stacked
        self._section = section
        self._table = _FakeTable(table_row_count if table_row_count is not None else len(rows))
        self._results_transposed = False
        self.notifications: list[tuple[str, str]] = []
        self.replace_calls: list[tuple[list[str], list[tuple[Any, ...]]]] = []
        self.typed_replace_calls: list[tuple[list[str], list[tuple[Any, ...]]]] = []
        self.footer_updates = 0
        self.clipboard_text: str | None = None

    def _get_active_results_context(self) -> tuple[Any, list[str], list[tuple[Any, ...]], bool]:
        return self._table, list(self._columns), list(self._rows), self._stacked

    def _find_results_section(self, _widget: Any) -> Any | None:
        return self._section

    def _replace_results_table(self, columns: list[str], rows: list[tuple[Any, ...]]) -> None:
        self.replace_calls.append((columns, rows))

    def _replace_results_section_table_typed(
        self, section: Any, _old_table: Any, columns: list[str], rows: list[tuple[Any, ...]]
    ) -> None:
        assert section is self._section
        self.typed_replace_calls.append((columns, rows))

    def notify(self, message: str, severity: str = "information", **_kwargs: Any) -> None:
        self.notifications.append((message, severity))

    def _update_footer_bindings(self) -> None:
        self.footer_updates += 1

    def _copy_text(self, text: str) -> bool:
        self.clipboard_text = text
        return True

    def _flash_table_yank(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def _clear_leader_pending(self) -> None:
        pass


class TestTransposeResultData:
    def test_swaps_columns_and_rows(self) -> None:
        header, transposed = _transpose_result_data(["id", "name"], [(1, "Ana"), (2, "Luis")])
        assert header == ["Column", "Row 1", "Row 2"]
        assert transposed == [("id", "1", "2"), ("name", "Ana", "Luis")]

    def test_formats_none_as_null_string(self) -> None:
        # A "Row N" column mixes values from every original column (which may have
        # different types), and the Arrow-backed table requires one type per column,
        # so cells are formatted to strings up front - including NULLs.
        header, transposed = _transpose_result_data(["id", "note"], [(1, None)])
        assert header == ["Column", "Row 1"]
        assert transposed == [("id", "1"), ("note", "NULL")]


class TestActionToggleTranspose:
    def test_toggle_on_rebuilds_table_transposed(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])

        app.action_toggle_transpose()

        assert app.replace_calls == [
            (["Column", "Row 1", "Row 2"], [("id", "1", "2"), ("name", "Ana", "Luis")])
        ]
        assert app._results_transposed is True
        assert app.footer_updates == 1

    def test_toggle_off_restores_original_table(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])

        app.action_toggle_transpose()
        app.action_toggle_transpose()

        assert app.replace_calls[-1] == (["id", "name"], [(1, "Ana"), (2, "Luis")])
        assert app._results_transposed is False
        assert app.footer_updates == 2

    def test_no_results_notifies_and_does_not_rebuild(self) -> None:
        app = _FakeApp([], [])

        app.action_toggle_transpose()

        assert app.replace_calls == []
        assert app.notifications == [("No results", "warning")]
        assert app.footer_updates == 0

    def test_truncates_when_too_many_rows(self) -> None:
        columns = ["id"]
        rows = [(i,) for i in range(MAX_TRANSPOSE_ROWS + 50)]
        app = _FakeApp(columns, rows, table_row_count=len(rows))

        app.action_toggle_transpose()

        built_columns, built_rows = app.replace_calls[0]
        assert built_columns == ["Column"] + [f"Row {i + 1}" for i in range(MAX_TRANSPOSE_ROWS)]
        assert built_rows == [("id", *(str(i) for i in range(MAX_TRANSPOSE_ROWS)))]
        assert app.notifications == [
            (f"Transposed first {MAX_TRANSPOSE_ROWS} of {len(rows)} rows", "warning")
        ]

    def test_stacked_mode_uses_section_flag_and_typed_builder(self) -> None:
        section = SimpleNamespace(result_transposed=False)
        app = _FakeApp(["id"], [(1,), (2,)], stacked=True, section=section)

        app.action_toggle_transpose()

        assert section.result_transposed is True
        assert app.typed_replace_calls == [(["Column", "Row 1", "Row 2"], [("id", "1", "2")])]
        assert app.replace_calls == []

        app.action_toggle_transpose()

        assert section.result_transposed is False
        assert app.typed_replace_calls[-1] == (["id"], [(1,), (2,)])


class TestCopyColumnValuesBlockedWhenTransposed:
    """`_copy_column_values` (bound to `ryf v`) reads the cursor's column index
    against the *original* untransposed columns/rows - while transposed, the
    cursor's column index runs over Column/Row-N instead, so the copied values
    would come from the wrong original column. It must be blocked, like the
    other column-identity actions (edit_cell, delete_row, ...)."""

    def test_blocked_when_transposed(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])
        app._table.cursor_coordinate = (0, 1)
        app._results_transposed = True

        app._copy_column_values()

        assert app.clipboard_text is None
        assert app.notifications == [("Not available in transposed view", "warning")]

    def test_allowed_when_not_transposed(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])
        app._table.cursor_coordinate = (0, 1)

        app._copy_column_values()

        assert app.clipboard_text is not None
        assert "Ana" in app.clipboard_text and "Luis" in app.clipboard_text


class TestCopyScopeAsFormatBlockedWhenTransposed:
    """`_copy_scope_as_format` (ryf* cell/row) mixes the live cursor position with
    the original untransposed `columns` list for cell labels, and pairs a
    transposed row's live values with the original column headers for rows -
    both mismatched while transposed. `all` is unaffected (no cursor involved)."""

    def test_cell_scope_blocked_when_transposed(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])
        app._table.cursor_coordinate = (0, 1)
        app._results_transposed = True

        app._copy_scope_as_format("json", "cell")

        assert app.clipboard_text is None
        assert app.notifications == [("Not available in transposed view", "warning")]

    def test_row_scope_blocked_when_transposed(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])
        app._table.cursor_coordinate = (0, 0)
        app._results_transposed = True

        app._copy_scope_as_format("json", "row")

        assert app.clipboard_text is None
        assert app.notifications == [("Not available in transposed view", "warning")]

    def test_cell_scope_allowed_when_not_transposed(self) -> None:
        app = _FakeApp(["id", "name"], [(1, "Ana"), (2, "Luis")])
        app._table.cursor_coordinate = (0, 1)

        app._copy_scope_as_format("json", "cell")

        assert app.clipboard_text is not None
