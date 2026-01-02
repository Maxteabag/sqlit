"""MySQL-compatible adapter base class."""

from __future__ import annotations

from typing import Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)


class MySQLBaseAdapter(CursorBasedAdapter):
    """Base class for MySQL-compatible databases (MySQL, MariaDB).

    These share the same SQL dialect, information_schema queries, and backtick quoting.
    Note: MySQL uses "database" and "schema" interchangeably - there are no schemas
    within a database like in SQL Server or PostgreSQL.
    """

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"mysql", "information_schema", "performance_schema", "sys"})

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases."""
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables. Returns (schema, name) tuples with empty schema."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (database,),
            )
        else:
            cursor.execute("SHOW TABLES")
        # MySQL doesn't have schemas within databases, so schema is empty
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views. Returns (schema, name) tuples with empty schema."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_name FROM information_schema.views " "WHERE table_schema = %s ORDER BY table_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT table_name FROM information_schema.views " "WHERE table_schema = DATABASE() ORDER BY table_name"
            )
        return [("", row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table. Schema parameter is ignored (MySQL has no schemas)."""
        cursor = conn.cursor()

        # Get primary key columns
        if database:
            cursor.execute(
                "SELECT column_name FROM information_schema.key_column_usage "
                "WHERE table_schema = %s AND table_name = %s AND constraint_name = 'PRIMARY'",
                (database, table),
            )
        else:
            cursor.execute(
                "SELECT column_name FROM information_schema.key_column_usage "
                "WHERE table_schema = DATABASE() AND table_name = %s AND constraint_name = 'PRIMARY'",
                (table,),
            )
        pk_columns = {row[0] for row in cursor.fetchall()}

        # Get all columns
        if database:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (database, table),
            )
        else:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "ORDER BY ordinal_position",
                (table,),
            )
        return [ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = %s AND routine_type = 'PROCEDURE' "
                "ORDER BY routine_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE' "
                "ORDER BY routine_name"
            )
        return [row[0] for row in cursor.fetchall()]

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using backticks for MySQL/MariaDB.

        Escapes embedded backticks by doubling them.
        """
        escaped = name.replace("`", "``")
        return f"`{escaped}`"

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT LIMIT query. Schema parameter is ignored (MySQL has no schemas)."""
        if database:
            return f"SELECT * FROM `{database}`.`{table}` LIMIT {limit}"
        return f"SELECT * FROM `{table}` LIMIT {limit}"

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from MySQL/MariaDB."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT DISTINCT index_name, table_name, non_unique "
                "FROM information_schema.statistics "
                "WHERE table_schema = %s AND index_name != 'PRIMARY' "
                "ORDER BY table_name, index_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT DISTINCT index_name, table_name, non_unique "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND index_name != 'PRIMARY' "
                "ORDER BY table_name, index_name"
            )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=row[2] == 0)
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from MySQL/MariaDB."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT trigger_name, event_object_table "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = %s "
                "ORDER BY event_object_table, trigger_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT trigger_name, event_object_table "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = DATABASE() "
                "ORDER BY event_object_table, trigger_name"
            )
        return [TriggerInfo(name=row[0], table_name=row[1]) for row in cursor.fetchall()]

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences. MySQL doesn't support sequences, returns empty list."""
        return []

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a MySQL/MariaDB index."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT column_name, non_unique, index_type "
                "FROM information_schema.statistics "
                "WHERE table_schema = %s AND table_name = %s AND index_name = %s "
                "ORDER BY seq_in_index",
                (database, table_name, index_name),
            )
        else:
            cursor.execute(
                "SELECT column_name, non_unique, index_type "
                "FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s "
                "ORDER BY seq_in_index",
                (table_name, index_name),
            )
        rows = cursor.fetchall()
        columns = [row[0] for row in rows]
        is_unique = rows[0][1] == 0 if rows else False
        index_type = rows[0][2] if rows else "BTREE"

        return {
            "name": index_name,
            "table_name": table_name,
            "columns": columns,
            "is_unique": is_unique,
            "type": index_type,
            "definition": f"CREATE {'UNIQUE ' if is_unique else ''}INDEX {index_name} ON {table_name} ({', '.join(columns)})",
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a MySQL/MariaDB trigger."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT action_timing, event_manipulation, action_statement "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = %s AND trigger_name = %s",
                (database, trigger_name),
            )
        else:
            cursor.execute(
                "SELECT action_timing, event_manipulation, action_statement "
                "FROM information_schema.triggers "
                "WHERE trigger_schema = DATABASE() AND trigger_name = %s",
                (trigger_name,),
            )
        row = cursor.fetchone()
        if row:
            return {
                "name": trigger_name,
                "table_name": table_name,
                "timing": row[0],
                "event": row[1],
                "definition": row[2],
            }
        return {
            "name": trigger_name,
            "table_name": table_name,
            "timing": None,
            "event": None,
            "definition": None,
        }
