"""Base class and common types for database adapters."""

from __future__ import annotations

import importlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.markup import escape

if TYPE_CHECKING:
    from ...config import ConnectionConfig


def resolve_file_path(path_str: str) -> Path:
    """Resolve a file path for file-based databases (SQLite, DuckDB).

    Handles:
    - Expanding ~ to home directory
    - Adding leading slash if path looks like it's missing one
    - Resolving to absolute path
    """
    path_str = path_str.strip()

    # Expand ~ to home directory
    file_path = Path(path_str).expanduser()

    # If path doesn't exist and looks like a missing leading slash, try adding it
    if not file_path.exists() and not path_str.startswith(("/", "~")):
        absolute_path = Path("/" + path_str)
        if absolute_path.exists():
            file_path = absolute_path

    # Resolve to absolute path
    return file_path.resolve()


@dataclass
class ColumnInfo:
    """Information about a database column."""

    name: str
    data_type: str
    is_primary_key: bool = False


@dataclass
class IndexInfo:
    """Information about a database index."""

    name: str
    table_name: str
    is_unique: bool = False


@dataclass
class TriggerInfo:
    """Information about a database trigger."""

    name: str
    table_name: str


@dataclass
class SequenceInfo:
    """Information about a database sequence."""

    name: str


# Type alias for table/view info: (schema, name)
TableInfo = tuple[str, str]


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters.

    Adapters handle database connectivity and introspection.
    Connection schema/metadata is defined separately in db.schema.
    """

    @property
    def install_hint(self) -> str | None:
        """Installation hint for the adapter's dependencies."""
        if not self.install_extra or not self.install_package:
            return None
        return _create_driver_import_error_hint(self.name, self.install_extra, self.install_package).strip()

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        """Import names used to verify required driver dependencies are installed."""
        return ()

    def ensure_driver_available(self) -> None:
        """Verify required dependencies can be imported, raising MissingDriverError if not."""
        forced_missing = os.environ.get("SQLIT_MOCK_MISSING_DRIVERS", "").strip()
        if forced_missing:
            forced = {s.strip() for s in forced_missing.split(",") if s.strip()}
            db_type = getattr(self, "_db_type", None)
            if db_type in forced:
                from ...db.exceptions import MissingDriverError

                if not self.install_extra or not self.install_package:
                    raise ImportError(f"Missing driver for {self.name}")
                raise MissingDriverError(self.name, self.install_extra, self.install_package)

        if not self.driver_import_names:
            return
        try:
            for module_name in self.driver_import_names:
                importlib.import_module(module_name)
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

    @property
    def install_extra(self) -> str | None:
        """Name of the [extra] for pip install."""
        return None

    @property
    def install_package(self) -> str | None:
        """Name of the package for pipx inject."""
        return None

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this database type."""
        pass

    @property
    @abstractmethod
    def supports_multiple_databases(self) -> bool:
        """Whether this database type supports multiple databases."""
        pass

    @property
    @abstractmethod
    def supports_stored_procedures(self) -> bool:
        """Whether this database type supports stored procedures."""
        pass

    @property
    def default_schema(self) -> str:
        """The default schema for this database type.

        Override in subclasses. Return empty string if schemas are not supported.
        """
        return ""

    @property
    def supports_indexes(self) -> bool:
        """Whether this database supports listing indexes.

        Override in subclasses if needed. Defaults to True since most databases support indexes.
        """
        return True

    @property
    def supports_triggers(self) -> bool:
        """Whether this database supports triggers.

        Override in subclasses if needed. Defaults to True since most databases support triggers.
        """
        return True

    @property
    def supports_sequences(self) -> bool:
        """Whether this database supports sequences.

        Override in subclasses. Defaults to False since many databases use auto-increment instead.
        """
        return False

    def format_table_name(self, schema: str, name: str) -> str:
        """Format a table name for display, omitting default schema.

        Args:
            schema: The schema name.
            name: The table name.

        Returns:
            Display name - "name" if schema is default, otherwise "schema.name".
        """
        if not schema or schema == self.default_schema:
            return name
        return f"{schema}.{name}"

    @abstractmethod
    def connect(self, config: ConnectionConfig) -> Any:
        """Create a connection to the database."""
        pass

    @abstractmethod
    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases (if supported)."""
        pass

    @abstractmethod
    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables in the database.

        Returns:
            List of (schema, table_name) tuples.
        """
        pass

    @abstractmethod
    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views in the database.

        Returns:
            List of (schema, view_name) tuples.
        """
        pass

    @abstractmethod
    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get list of columns for a table.

        Args:
            conn: Database connection.
            table: Table name.
            database: Database name (if supported).
            schema: Schema name (if supported).
        """
        pass

    @abstractmethod
    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get list of stored procedures (if supported)."""
        pass

    @abstractmethod
    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get list of indexes in the database.

        Returns:
            List of IndexInfo objects with name, table_name, and is_unique.
        """
        pass

    @abstractmethod
    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Get list of triggers in the database.

        Returns:
            List of TriggerInfo objects with name and table_name.
        """
        pass

    @abstractmethod
    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get list of sequences in the database (if supported).

        Returns:
            List of SequenceInfo objects with name.
        """
        pass

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about an index.

        Returns a dict with keys like:
        - name: Index name
        - table_name: Table the index is on
        - columns: List of column names in the index
        - is_unique: Whether the index is unique
        - definition: DDL statement (if available)

        Default implementation returns minimal info. Override in subclasses.
        """
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
        """Get detailed information about a trigger.

        Returns a dict with keys like:
        - name: Trigger name
        - table_name: Table the trigger is on
        - event: Trigger event (INSERT, UPDATE, DELETE)
        - timing: Trigger timing (BEFORE, AFTER, INSTEAD OF)
        - definition: Trigger source code/DDL

        Default implementation returns minimal info. Override in subclasses.
        """
        return {
            "name": trigger_name,
            "table_name": table_name,
            "event": None,
            "timing": None,
            "definition": None,
        }

    def get_sequence_definition(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a sequence.

        Returns a dict with keys like:
        - name: Sequence name
        - current_value: Current value (may not be available without advancing)
        - start_value: Starting value
        - increment: Increment amount
        - min_value: Minimum value
        - max_value: Maximum value
        - cycle: Whether the sequence cycles

        Default implementation returns minimal info. Override in subclasses.
        """
        return {
            "name": sequence_name,
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        """Quote an identifier (table name, column name, etc.)."""
        pass

    @abstractmethod
    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build a SELECT query with limit.

        Args:
            table: Table name.
            limit: Maximum rows to return.
            database: Database name (if supported).
            schema: Schema name (if supported).
        """
        pass

    @abstractmethod
    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query and return (columns, rows, truncated).

        Args:
            conn: Database connection.
            query: SQL query to execute.
            max_rows: Maximum rows to fetch. None means no limit.

        Returns:
            Tuple of (column_names, rows, was_truncated).
            was_truncated is True if there were more rows than max_rows.
        """
        pass

    @abstractmethod
    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query statement and return rows affected."""
        pass


class CursorBasedAdapter(DatabaseAdapter):
    """Base class for adapters using cursor-based execution (most SQL databases).

    Provides common implementations for execute_query and execute_non_query.
    """

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a query using cursor-based approach with optional row limit."""
        cursor = conn.cursor()
        cursor.execute(query)
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            if max_rows is not None:
                # Fetch one extra row to detect if there are more
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
        """Execute a non-query using cursor-based approach."""
        cursor = conn.cursor()
        cursor.execute(query)
        rowcount = int(cursor.rowcount)
        conn.commit()
        return rowcount


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


def _create_driver_import_error_hint(driver_name: str, extra_name: str, package_name: str) -> str:
    """Generate a context-aware hint for missing driver installation."""
    from ...install_strategy import detect_strategy

    strategy = detect_strategy(extra_name=extra_name, package_name=package_name)
    instructions = escape(strategy.manual_instructions)
    return (
        f"{driver_name} driver not found.\n\n"
        f"To connect to {driver_name}, run:\n\n"
        f"[bold]{instructions}[/bold]\n"
    )
