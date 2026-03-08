"""Base class and common types for database adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig

SELECT_KEYWORDS = frozenset(["SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA"])


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
    Connection schema/metadata is defined in provider schema modules.
    """

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        """Import names used to verify required driver dependencies are installed."""
        return ()

    @property
    def install_extra(self) -> str | None:
        """Name of the [extra] for pip install."""
        return None

    @property
    def install_package(self) -> str | None:
        """Name of the package for pipx inject."""
        return None

    def set_driver_resolver(self, resolver: Any) -> None:
        self._driver_resolver = resolver

    def _get_driver_resolver(self) -> Any | None:
        return getattr(self, "_driver_resolver", None)

    def _import_driver_module(
        self,
        module_name: str,
        *,
        driver_name: str,
        extra_name: str | None,
        package_name: str | None,
    ) -> Any:
        from sqlit.domains.connections.providers.driver import import_driver_module

        return import_driver_module(
            module_name,
            driver_name=driver_name,
            extra_name=extra_name,
            package_name=package_name,
            resolver=self._get_driver_resolver(),
        )

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
    def supports_cross_database_queries(self) -> bool:
        """Whether this database supports cross-database queries.

        When True, queries can reference tables in other databases using
        fully qualified names (e.g., [db].[schema].[table] in SQL Server).

        When False, each database is isolated and a specific database must
        be selected before querying. Connection creation will require a
        database to be specified.

        Defaults to True. Override in subclasses for databases like PostgreSQL
        where each database is isolated.
        """
        return True

    @property
    @abstractmethod
    def supports_stored_procedures(self) -> bool:
        """Whether this database type supports stored procedures."""
        pass

    @property
    def system_databases(self) -> frozenset[str]:
        """Set of system database names to exclude from user listings.

        Override in subclasses for database-specific system databases.
        Returns lowercase names for case-insensitive comparison.
        """
        return frozenset()

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

    @property
    def supports_process_worker(self) -> bool:
        """Whether this adapter supports running queries in a separate process."""
        return True

    @property
    def test_query(self) -> str:
        """A simple query to test the connection.

        Override in subclasses for databases that need special syntax.
        """
        return "SELECT 1"

    def classify_query(self, query: str) -> bool:
        """Return True if the query is expected to return rows."""
        query_type = query.strip().upper().split()[0] if query.strip() else ""
        return query_type in SELECT_KEYWORDS

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works.

        Override in subclasses for databases with non-standard APIs.
        """
        cursor = conn.cursor()
        cursor.execute(self.test_query)
        cursor.fetchone()

    def disconnect(self, conn: Any) -> None:
        """Close a connection if the driver exposes a close method."""
        close_fn = getattr(conn, "close", None)
        if callable(close_fn):
            close_fn()

    def normalize_config(self, config: ConnectionConfig) -> ConnectionConfig:
        """Normalize provider-specific config defaults."""
        return config

    def validate_config(self, config: ConnectionConfig) -> None:
        """Validate provider-specific config values."""
        return None

    def detect_capabilities(self, conn: Any, config: ConnectionConfig) -> None:
        """Detect runtime capabilities after establishing a connection."""
        return None

    def get_auth_type(self, config: ConnectionConfig) -> Any | None:
        """Return the provider-specific auth type, if applicable."""
        return None

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a query-time database override if supported."""
        return config

    def get_post_connect_warnings(self, config: ConnectionConfig) -> list[str]:
        """Return warning messages after a successful connection."""
        return []

    def build_connection_string(self, config: ConnectionConfig) -> str:
        """Build a connection string for adapters that support it."""
        raise NotImplementedError(f"{self.name} does not support connection strings")

    def format_table_name(self, schema: str | None, table: str) -> str:
        """Format a table name for display, omitting default schema.

        Args:
            schema: The schema name.
            name: The table name.

        Returns:
            Display name - "name" if schema is default, otherwise "schema.name".
        """
        if not schema or schema == self.default_schema:
            return table
        return f"{schema}.{table}"

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


__all__ = [
    "ColumnInfo",
    "DatabaseAdapter",
    "IndexInfo",
    "SequenceInfo",
    "TableInfo",
    "TriggerInfo",
    "resolve_file_path",
]
