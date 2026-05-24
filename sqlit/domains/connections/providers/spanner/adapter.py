"""Google Cloud Spanner adapter using google-cloud-spanner DB-API.

Note on INFORMATION_SCHEMA queries:
    Spanner's DB-API uses read-write transactions by default, but
    INFORMATION_SCHEMA queries require read-only mode. All metadata
    introspection methods use _execute_readonly() which temporarily
    enables autocommit mode to work around this limitation.

Note on DNS resolution:
    Some networks have issues with gRPC's default c-ares DNS resolver.
    The adapter sets GRPC_DNS_RESOLVER=native if not already set.

Note on dialect support:
    Spanner supports two SQL dialects: GoogleSQL and PostgreSQL.
    The adapter detects the dialect on connect and adjusts identifier
    quoting accordingly (backticks for GoogleSQL, double quotes for PostgreSQL).
    PostgreSQL dialect support is experimental and untested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    CursorBasedAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig

# Dialect constants
DIALECT_GOOGLESQL = "GOOGLE_STANDARD_SQL"
DIALECT_POSTGRESQL = "POSTGRESQL"


class SpannerAdapter(CursorBasedAdapter):
    """Adapter for Google Cloud Spanner."""

    @property
    def name(self) -> str:
        return "Spanner"

    @property
    def install_extra(self) -> str:
        return "spanner"

    @property
    def install_package(self) -> str:
        return "google-cloud-spanner"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("google.cloud.spanner_dbapi",)

    @property
    def supports_multiple_databases(self) -> bool:
        # Spanner connects to a single database per connection
        return False

    @property
    def supports_cross_database_queries(self) -> bool:
        # Each connection is scoped to one database
        return False

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        # Spanner has indexes but they're exposed via INFORMATION_SCHEMA
        return True

    @property
    def supports_sequences(self) -> bool:
        return False

    @property
    def default_schema(self) -> str:
        # Spanner doesn't have schemas
        return ""

    def _get_option(self, config: ConnectionConfig, key: str) -> str:
        """Get a string option from config."""
        value = config.options.get(key, "")
        return str(value) if value else ""

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to Google Cloud Spanner using the DB-API connector."""
        import os

        # Use native DNS resolver to avoid c-ares DNS issues on some networks
        if "GRPC_DNS_RESOLVER" not in os.environ:
            os.environ["GRPC_DNS_RESOLVER"] = "native"

        spanner_dbapi = self._import_driver_module(
            "google.cloud.spanner_dbapi",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        project = self._get_option(config, "spanner_project")
        instance = self._get_option(config, "spanner_instance")
        database = config.tcp_endpoint.database if config.tcp_endpoint else ""
        if not database:
            database = self._get_option(config, "database")
        database_role = self._get_option(config, "spanner_database_role") or None
        emulator_host = self._get_option(config, "spanner_emulator_host")

        credentials = None
        auth_method = self._get_option(config, "spanner_auth_method") or "default"

        if emulator_host:
            # For emulator, we need to set the environment variable
            os.environ["SPANNER_EMULATOR_HOST"] = emulator_host
        elif auth_method == "service_account":
            credentials_path = self._get_option(config, "spanner_credentials_path")
            if credentials_path:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(credentials_path)

        connect_kwargs: dict[str, Any] = {
            "instance_id": instance,
            "database_id": database,
            "project": project,
        }
        if credentials:
            connect_kwargs["credentials"] = credentials
        if database_role:
            connect_kwargs["database_role"] = database_role

        conn = spanner_dbapi.connect(**connect_kwargs)

        # Store config for later use
        conn._sqlit_spanner_database = database

        # Detect and store the database dialect (GoogleSQL or PostgreSQL)
        conn._sqlit_spanner_dialect = self._detect_dialect(conn)

        return conn

    def _detect_dialect(self, conn: Any) -> str:
        """Detect the database dialect (GoogleSQL or PostgreSQL).

        Queries INFORMATION_SCHEMA.DATABASE_OPTIONS to determine which SQL
        dialect the database uses. This affects identifier quoting.
        """
        query = """
            SELECT OPTION_VALUE
            FROM INFORMATION_SCHEMA.DATABASE_OPTIONS
            WHERE OPTION_NAME = 'database_dialect'
        """
        rows = self._execute_readonly(conn, query)
        if rows and rows[0]:
            return str(rows[0][0])
        # If we can't detect, raise an error (no fallback)
        msg = "Could not detect Spanner database dialect"
        raise ValueError(msg)

    def _get_dialect(self, conn: Any) -> str:
        """Get the cached dialect for a connection."""
        dialect = getattr(conn, "_sqlit_spanner_dialect", None)
        if dialect is None:
            msg = "Spanner dialect not detected on connection"
            raise ValueError(msg)
        return dialect

    def get_databases(self, conn: Any) -> list[str]:
        """Return the connected database (Spanner is single-database per connection)."""
        database = getattr(conn, "_sqlit_spanner_database", None)
        if database:
            return [database]
        return []

    def _execute_readonly(self, conn: Any, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        """Execute a read-only query (required for INFORMATION_SCHEMA).

        Spanner's DB-API uses read-write transactions by default, which don't
        support INFORMATION_SCHEMA queries. We temporarily enable autocommit
        mode to use single-use read-only transactions.
        """
        original_autocommit = conn.autocommit
        try:
            conn.autocommit = True
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        finally:
            conn.autocommit = original_autocommit

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from INFORMATION_SCHEMA."""
        query = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA = ''
            ORDER BY TABLE_NAME
        """
        rows = self._execute_readonly(conn, query)
        return [(row[0] or "", row[1]) for row in rows]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from INFORMATION_SCHEMA."""
        query = """
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'VIEW'
              AND TABLE_SCHEMA = ''
            ORDER BY TABLE_NAME
        """
        rows = self._execute_readonly(conn, query)
        return [(row[0] or "", row[1]) for row in rows]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from INFORMATION_SCHEMA."""
        # Get primary key columns first
        pk_query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.INDEX_COLUMNS
            WHERE TABLE_NAME = @table_name
              AND INDEX_NAME = 'PRIMARY_KEY'
            ORDER BY ORDINAL_POSITION
        """
        pk_rows = self._execute_readonly(conn, pk_query, {"table_name": table})
        pk_columns = {row[0] for row in pk_rows}

        # Get all columns
        query = """
            SELECT COLUMN_NAME, SPANNER_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = @table_name
            ORDER BY ORDINAL_POSITION
        """
        rows = self._execute_readonly(conn, query, {"table_name": table})
        return [
            ColumnInfo(
                name=row[0],
                data_type=row[1],
                is_primary_key=row[0] in pk_columns,
            )
            for row in rows
        ]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Spanner doesn't support stored procedures."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get list of indexes from INFORMATION_SCHEMA."""
        query = """
            SELECT INDEX_NAME, TABLE_NAME, IS_UNIQUE
            FROM INFORMATION_SCHEMA.INDEXES
            WHERE INDEX_TYPE != 'PRIMARY_KEY'
              AND TABLE_SCHEMA = ''
            ORDER BY TABLE_NAME, INDEX_NAME
        """
        rows = self._execute_readonly(conn, query)
        return [
            IndexInfo(
                name=row[0],
                table_name=row[1],
                is_unique=row[2],
            )
            for row in rows
        ]

    def get_index_definition(
        self, conn: Any, index_name: str, table_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about an index."""
        # Get index info
        query = """
            SELECT INDEX_NAME, TABLE_NAME, IS_UNIQUE, INDEX_STATE
            FROM INFORMATION_SCHEMA.INDEXES
            WHERE INDEX_NAME = @index_name
              AND TABLE_NAME = @table_name
        """
        rows = self._execute_readonly(conn, query, {"index_name": index_name, "table_name": table_name})
        row = rows[0] if rows else None

        if not row:
            return {
                "name": index_name,
                "table_name": table_name,
                "columns": [],
                "is_unique": False,
                "definition": None,
            }

        # Get index columns
        columns_query = """
            SELECT COLUMN_NAME, COLUMN_ORDERING
            FROM INFORMATION_SCHEMA.INDEX_COLUMNS
            WHERE INDEX_NAME = @index_name
              AND TABLE_NAME = @table_name
            ORDER BY ORDINAL_POSITION
        """
        col_rows = self._execute_readonly(conn, columns_query, {"index_name": index_name, "table_name": table_name})
        columns = [f"{col[0]} {col[1] or 'ASC'}".strip() for col in col_rows]

        return {
            "name": row[0],
            "table_name": row[1],
            "columns": columns,
            "is_unique": row[2],
            "index_state": row[3],
            "definition": None,
        }

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Spanner doesn't support triggers."""
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Spanner doesn't support traditional sequences."""
        return []

    def _quote_identifier_for_dialect(self, dialect: str, name: str) -> str:
        """Quote an identifier based on dialect.

        - GoogleSQL: `identifier` (backticks)
        - PostgreSQL: "identifier" (double quotes)
        """
        if dialect == DIALECT_POSTGRESQL:
            # PostgreSQL dialect uses double quotes
            escaped = name.replace('"', '""')
            return f'"{escaped}"'
        # GoogleSQL uses backticks
        escaped = name.replace("`", "\\`")
        return f"`{escaped}`"

    def _quote_identifier_for_conn(self, conn: Any, name: str) -> str:
        """Quote an identifier using the connection's dialect."""
        dialect = self._get_dialect(conn)
        return self._quote_identifier_for_dialect(dialect, name)

    def quote_identifier(self, name: str) -> str:
        """Quote an identifier for GoogleSQL (backticks).

        Note: This method doesn't have access to the connection, so it always
        uses GoogleSQL syntax. For connection-aware quoting, use
        _quote_identifier_for_conn() instead.
        """
        return self._quote_identifier_for_dialect(DIALECT_GOOGLESQL, name)

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT query with LIMIT.

        Note: This method doesn't have access to the connection, so it always
        uses GoogleSQL syntax for identifier quoting.
        """
        quoted = self._quote_identifier_for_dialect(DIALECT_GOOGLESQL, table)
        return f"SELECT * FROM {quoted} LIMIT {limit}"

    def build_select_query_for_conn(
        self, conn: Any, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT query with LIMIT using connection-aware quoting."""
        quoted = self._quote_identifier_for_conn(conn, table)
        return f"SELECT * FROM {quoted} LIMIT {limit}"
