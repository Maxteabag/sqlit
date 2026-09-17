"""Integration test for PR #250 against a real multi-database SQL Server.

The bug: ``action_delete_row`` / ``action_edit_cell`` in the results panel built
the DELETE/UPDATE from the *bare* table name. When you preview a table that
lives in a different database than the one the connection is currently on, the
unqualified statement targets the *wrong* database (the connection's current
one), silently mutating the wrong table.

This test reproduces it end to end:

  * a real SQL Server with two databases, each holding ``dbo.widgets`` with one
    row carrying a database-specific marker;
  * a connection whose current database is A;
  * the real ``ResultsMixin`` actions driven with ``table_info`` pointing at the
    table in database B (exactly what the explorer stashes when you open a table
    from another database);
  * the generated SQL executed against the live connection.

With the bug the statement hits database A. With the fix it hits B. We assert
that B is mutated and A is left untouched, so the test is RED on the old code
and GREEN on PR #250.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sqlit.domains.connections.providers.adapters.base import ColumnInfo
from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
from sqlit.domains.results.ui.mixins.results import ResultsMixin
from tests.conftest import MSSQL_HOST, MSSQL_PASSWORD, MSSQL_PORT, MSSQL_USER
from tests.fixtures.mssql import mssql_available

DB_A = "sqlit_qual_a"
DB_B = "sqlit_qual_b"


def _master_config() -> Any:
    from tests.helpers import ConnectionConfig

    return ConnectionConfig(
        name="test-qual-master",
        db_type="mssql",
        server=MSSQL_HOST,
        port=str(MSSQL_PORT),
        database="master",
        username=MSSQL_USER,
        password=MSSQL_PASSWORD,
        options={"auth_type": "sql"},
    )


def _db_config(database: str) -> Any:
    from tests.helpers import ConnectionConfig

    return ConnectionConfig(
        name=f"test-qual-{database}",
        db_type="mssql",
        server=MSSQL_HOST,
        port=str(MSSQL_PORT),
        database=database,
        username=MSSQL_USER,
        password=MSSQL_PASSWORD,
        options={"auth_type": "sql"},
    )


@pytest.fixture
def two_databases():
    """Create two databases each with dbo.widgets(id PK, label) and one row."""
    if not mssql_available():
        pytest.skip("SQL Server is not available")

    adapter = SQLServerAdapter()
    master = adapter.connect(_master_config())
    master.autocommit = True
    cur = master.cursor()
    for db, marker in ((DB_A, "A_original"), (DB_B, "B_original")):
        cur.execute(f"IF DB_ID('{db}') IS NOT NULL BEGIN ALTER DATABASE [{db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{db}]; END")
        cur.execute(f"CREATE DATABASE [{db}]")
        cur.execute(f"CREATE TABLE [{db}].[dbo].[widgets] (id INT PRIMARY KEY, label NVARCHAR(50))")
        cur.execute(f"INSERT INTO [{db}].[dbo].[widgets] (id, label) VALUES (1, '{marker}')")
    cur.close()
    master.close()

    yield adapter

    master = adapter.connect(_master_config())
    master.autocommit = True
    cur = master.cursor()
    for db in (DB_A, DB_B):
        cur.execute(f"IF DB_ID('{db}') IS NOT NULL BEGIN ALTER DATABASE [{db}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{db}]; END")
    cur.close()
    master.close()


class _FakeInput:
    def __init__(self) -> None:
        self.text = ""
        self.cursor_location = (0, 0)
        self.read_only = False

    def focus(self) -> None:
        pass


class _FakeTable:
    """Mimics the focused DataTable holding the single previewed row."""

    def __init__(self, row: tuple[Any, ...]) -> None:
        self._row = row
        self.row_count = 1
        self.cursor_coordinate: tuple[int, int] = (0, 0)

    def get_row_at(self, _row: int) -> list[Any]:
        return list(self._row)


class _ResultsHost(ResultsMixin):
    """Minimal host so the *real* ResultsMixin actions run without Textual.

    Everything that matters for the bug — qualified_name composition, the
    table_info lookup, WHERE/PK handling — is the production mixin + adapter.
    """

    def __init__(self, adapter: SQLServerAdapter, table_info: dict[str, Any], row: tuple[Any, ...], columns: list[str]) -> None:
        self._table = _FakeTable(row)
        self._columns = columns
        # The explorer stashes the previewed table's identity here; the real
        # _get_active_results_table_info falls back to it.
        self._last_query_table = table_info
        self.query_input = _FakeInput()
        self._suppress_autocomplete_once = False
        self.current_provider = SimpleNamespace(dialect=adapter)
        self.vim_mode = None

    def _get_active_results_context(self) -> tuple[Any, list, list, bool]:
        return self._table, self._columns, [tuple(self._table._row)], False

    def notify(self, *_a: Any, **_k: Any) -> None:
        pass

    def action_focus_query(self) -> None:
        pass

    def _update_footer_bindings(self) -> None:
        pass

    def _update_vim_mode_visuals(self) -> None:
        pass


def _columns_meta() -> list[ColumnInfo]:
    return [
        ColumnInfo(name="id", data_type="int", is_primary_key=True),
        ColumnInfo(name="label", data_type="nvarchar", is_primary_key=False),
    ]


def _count(adapter: SQLServerAdapter, conn: Any, database: str) -> int:
    _cols, rows, _ = adapter.execute_query(conn, f"SELECT COUNT(*) FROM [{database}].[dbo].[widgets]")
    return rows[0][0]


def _label(adapter: SQLServerAdapter, conn: Any, database: str) -> str | None:
    _cols, rows, _ = adapter.execute_query(conn, f"SELECT label FROM [{database}].[dbo].[widgets] WHERE id = 1")
    return rows[0][0] if rows else None


@pytest.mark.integration
@pytest.mark.mssql
class TestResultsQualifiedMutation:
    def test_delete_targets_table_own_database(self, two_databases: SQLServerAdapter) -> None:
        adapter = two_databases
        # Connection's *current* database is A; we operate on a row from B.
        conn = adapter.connect(_db_config(DB_A))
        try:
            table_info = {"database": DB_B, "schema": "dbo", "name": "widgets", "columns": _columns_meta()}
            host = _ResultsHost(adapter, table_info, row=(1, "B_original"), columns=["id", "label"])

            host.action_delete_row()
            query = host.query_input.text
            assert query, "no DELETE query generated"

            # Execute exactly what the panel produced, against the A-connection.
            cur = conn.cursor()
            cur.execute(query)
            conn.commit()
            cur.close()

            # The fix must delete from B (the table we were viewing) and leave A.
            assert _count(adapter, conn, DB_B) == 0, f"row in {DB_B} should be deleted; query was: {query}"
            assert _count(adapter, conn, DB_A) == 1, f"row in {DB_A} must be untouched; query was: {query}"
        finally:
            conn.close()

    def test_update_targets_table_own_database(self, two_databases: SQLServerAdapter) -> None:
        adapter = two_databases
        conn = adapter.connect(_db_config(DB_A))
        try:
            table_info = {"database": DB_B, "schema": "dbo", "name": "widgets", "columns": _columns_meta()}
            host = _ResultsHost(adapter, table_info, row=(1, "B_original"), columns=["id", "label"])
            # Put the cursor on the editable (non-PK) `label` column.
            host._table.cursor_coordinate = (0, 1)

            host.action_edit_cell()
            query = host.query_input.text
            assert query and query.startswith("UPDATE"), f"no UPDATE query generated: {query!r}"

            cur = conn.cursor()
            cur.execute(query)
            conn.commit()
            cur.close()

            # B's label was set to '' (the panel's placeholder); A stays original.
            assert _label(adapter, conn, DB_B) == "", f"row in {DB_B} should be updated; query was: {query}"
            assert _label(adapter, conn, DB_A) == "A_original", f"row in {DB_A} must be untouched; query was: {query}"
        finally:
            conn.close()
