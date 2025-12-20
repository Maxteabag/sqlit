"""SQLite adapter using built-in sqlite3."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from .base import ColumnInfo, DatabaseAdapter, IndexInfo, SequenceInfo, TableInfo, TriggerInfo, resolve_file_path

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class SQLiteAdapter(DatabaseAdapter):
    """Adapter for SQLite using built-in sqlite3."""

    @property
    def name(self) -> str:
        return "SQLite"

    @property
    def supports_multiple_databases(self) -> bool:
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to SQLite database file."""
        import sqlite3

        file_path = resolve_file_path(config.file_path)
        # check_same_thread=False allows connection to be used from background threads
        # (for async query execution). SQLite serializes access internally.
        conn = sqlite3.connect(file_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get_databases(self, conn: Any) -> list[str]:
        """SQLite doesn't support multiple databases - return empty list."""
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from SQLite. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' " "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from SQLite. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from SQLite. Schema parameter is ignored."""
        cursor = conn.cursor()
        # Use quote_identifier to properly escape table names with special chars
        quoted_table = self.quote_identifier(table)
        cursor.execute(f"PRAGMA table_info({quoted_table})")
        # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
        # pk > 0 indicates column is part of primary key
        return [
            ColumnInfo(name=row[1], data_type=row[2] or "TEXT", is_primary_key=row[5] > 0)
            for row in cursor.fetchall()
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """SQLite doesn't support stored procedures - return empty list."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from SQLite."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type='index' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY tbl_name, name"
        )
        results = []
        for row in cursor.fetchall():
            # Check if index is unique using PRAGMA
            index_cursor = conn.cursor()
            index_cursor.execute(f"PRAGMA index_list({self.quote_identifier(row[1])})")
            is_unique = False
            for idx_info in index_cursor.fetchall():
                if idx_info[1] == row[0]:  # idx_info: seq, name, unique, origin, partial
                    is_unique = idx_info[2] == 1
                    break
            results.append(IndexInfo(name=row[0], table_name=row[1], is_unique=is_unique))
        return results

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from SQLite."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type='trigger' "
            "ORDER BY tbl_name, name"
        )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """SQLite doesn't support sequences - return empty list."""
        return []

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQLite index."""
        cursor = conn.cursor()

        # Get index columns using PRAGMA index_info
        cursor.execute(f"PRAGMA index_info({self.quote_identifier(index_name)})")
        columns = [row[2] for row in cursor.fetchall()]  # row: seqno, cid, name

        # Check if unique using PRAGMA index_list
        cursor.execute(f"PRAGMA index_list({self.quote_identifier(table_name)})")
        is_unique = False
        for row in cursor.fetchall():
            if row[1] == index_name:  # row: seq, name, unique, origin, partial
                is_unique = row[2] == 1
                break

        # Get the CREATE INDEX statement from sqlite_master
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name = ?",
            (index_name,),
        )
        row = cursor.fetchone()
        definition = row[0] if row and row[0] else None

        return {
            "name": index_name,
            "table_name": table_name,
            "columns": columns,
            "is_unique": is_unique,
            "definition": definition,
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a SQLite trigger."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name = ?",
            (trigger_name,),
        )
        row = cursor.fetchone()
        definition = row[0] if row else None

        # Parse timing and event from the definition if available
        timing = None
        event = None
        if definition:
            upper_def = definition.upper()
            if "BEFORE " in upper_def:
                timing = "BEFORE"
            elif "AFTER " in upper_def:
                timing = "AFTER"
            elif "INSTEAD OF " in upper_def:
                timing = "INSTEAD OF"

            if " INSERT " in upper_def:
                event = "INSERT"
            elif " UPDATE " in upper_def:
                event = "UPDATE"
            elif " DELETE " in upper_def:
                event = "DELETE"

        return {
            "name": trigger_name,
            "table_name": table_name,
            "timing": timing,
            "event": event,
            "definition": definition,
        }

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using double quotes for SQLite.

        Escapes embedded double quotes by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT LIMIT query for SQLite. Schema parameter is ignored."""
        return f'SELECT * FROM "{table}" LIMIT {limit}'

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query on SQLite with optional row limit."""
        cursor = conn.cursor()
        cursor.execute(query)
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            if max_rows is not None:
                rows = cursor.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]
            else:
                rows = cursor.fetchall()
                truncated = False
            return columns, [tuple(row) for row in rows], truncated
        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query on SQLite."""
        cursor = conn.cursor()
        cursor.execute(query)
        rowcount = int(cursor.rowcount)
        conn.commit()
        return rowcount
