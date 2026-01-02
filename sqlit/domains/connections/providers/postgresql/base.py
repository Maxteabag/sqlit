"""PostgreSQL-compatible adapter base class."""

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


class PostgresBaseAdapter(CursorBasedAdapter):
    """Base class for PostgreSQL-compatible databases (PostgreSQL, CockroachDB).

    These share the same SQL dialect, information_schema queries, and double-quote quoting.
    """

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return True

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"template0", "template1"})

    @property
    def supports_cross_database_queries(self) -> bool:
        """PostgreSQL databases are isolated; cross-database queries not supported."""
        return False

    @property
    def default_schema(self) -> str:
        return "public"

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from all schemas."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from all schemas."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT table_schema, table_name FROM information_schema.views "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table."""
        cursor = conn.cursor()
        schema = schema or "public"

        # Get primary key columns
        cursor.execute(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "WHERE tc.constraint_type = 'PRIMARY KEY' "
            "AND tc.table_schema = %s AND tc.table_name = %s",
            (schema, table),
        )
        pk_columns = {row[0] for row in cursor.fetchall()}

        # Get all columns
        cursor.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (schema, table),
        )
        return [
            ColumnInfo(name=row[0], data_type=row[1], is_primary_key=row[0] in pk_columns)
            for row in cursor.fetchall()
        ]

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using double quotes for PostgreSQL.

        Escapes embedded double quotes by doubling them.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT LIMIT query for PostgreSQL."""
        schema = schema or "public"
        return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'

    @property
    def supports_sequences(self) -> bool:
        """PostgreSQL supports sequences."""
        return True

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get indexes from PostgreSQL."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT indexname, tablename, "
            "  CASE WHEN indexdef LIKE '%UNIQUE%' THEN true ELSE false END as is_unique "
            "FROM pg_indexes "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY tablename, indexname"
        )
        return [
            IndexInfo(name=row[0], table_name=row[1], is_unique=row[2])
            for row in cursor.fetchall()
        ]

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get triggers from PostgreSQL."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT trigger_name, event_object_table "
            "FROM information_schema.triggers "
            "WHERE trigger_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY event_object_table, trigger_name"
        )
        # Deduplicate since a trigger can fire on multiple events
        seen = set()
        results = []
        for row in cursor.fetchall():
            key = (row[0], row[1])
            if key not in seen:
                seen.add(key)
                results.append(TriggerInfo(name=row[0], table_name=row[1]))
        return results

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from PostgreSQL."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sequence_name "
            "FROM information_schema.sequences "
            "WHERE sequence_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY sequence_name"
        )
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a PostgreSQL index."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT indexdef, "
            "  CASE WHEN indexdef LIKE '%%UNIQUE%%' THEN true ELSE false END as is_unique "
            "FROM pg_indexes "
            "WHERE indexname = %s AND tablename = %s",
            (index_name, table_name),
        )
        row = cursor.fetchone()
        if row:
            return {
                "name": index_name,
                "table_name": table_name,
                "columns": [],  # Would need to parse indexdef to extract
                "is_unique": row[1],
                "definition": row[0],
            }
        return {
            "name": index_name,
            "table_name": table_name,
            "columns": [],
            "is_unique": False,
            "definition": None,
        }

    def get_trigger_definition(
        self, conn: Any, trigger_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a PostgreSQL trigger."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_timing, event_manipulation, action_statement "
            "FROM information_schema.triggers "
            "WHERE trigger_name = %s AND event_object_table = %s "
            "LIMIT 1",
            (trigger_name, table_name),
        )
        row = cursor.fetchone()
        if row:
            # Try to get the full trigger definition using pg_get_triggerdef
            try:
                cursor.execute(
                    "SELECT pg_get_triggerdef(t.oid) "
                    "FROM pg_trigger t "
                    "JOIN pg_class c ON t.tgrelid = c.oid "
                    "WHERE t.tgname = %s AND c.relname = %s",
                    (trigger_name, table_name),
                )
                def_row = cursor.fetchone()
                definition = def_row[0] if def_row else row[2]
            except Exception:
                definition = row[2]

            return {
                "name": trigger_name,
                "table_name": table_name,
                "timing": row[0],
                "event": row[1],
                "definition": definition,
            }
        return {
            "name": trigger_name,
            "table_name": table_name,
            "timing": None,
            "event": None,
            "definition": None,
        }

    def get_sequence_definition(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a PostgreSQL sequence."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT start_value, increment, minimum_value, maximum_value, cycle_option "
            "FROM information_schema.sequences "
            "WHERE sequence_name = %s "
            "AND sequence_schema NOT IN ('pg_catalog', 'information_schema')",
            (sequence_name,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "name": sequence_name,
                "start_value": row[0],
                "increment": row[1],
                "min_value": row[2],
                "max_value": row[3],
                "cycle": row[4] == "YES",
            }
        return {
            "name": sequence_name,
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }
