"""Apache Arrow Flight SQL adapter using adbc-driver-flightsql."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import (
    ColumnInfo,
    DatabaseAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class FlightSQLAdapter(DatabaseAdapter):
    """Adapter for Apache Arrow Flight SQL.

    Flight SQL is a protocol for interacting with SQL databases using
    Apache Arrow Flight. It provides high-performance data transfer
    using Arrow's columnar format.

    This adapter uses the official Apache Arrow ADBC Flight SQL driver,
    which provides a standard DBAPI 2.0 interface.

    Supports:
    - Basic authentication (username/password)
    - Bearer token authentication
    - TLS/SSL connections
    - Standard SQL operations via Flight SQL protocol
    """

    @classmethod
    def badge_label(cls) -> str:
        return "Flight"

    @classmethod
    def url_schemes(cls) -> tuple[str, ...]:
        return ("flight", "grpc", "grpc+tls")

    @property
    def name(self) -> str:
        return "Arrow Flight SQL"

    @property
    def install_extra(self) -> str:
        return "flight"

    @property
    def install_package(self) -> str:
        return "adbc-driver-flightsql"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("adbc_driver_flightsql",)

    @property
    def supports_multiple_databases(self) -> bool:
        # Flight SQL supports catalogs (databases)
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        # Standard Flight SQL doesn't have stored procedures
        return False

    @property
    def supports_indexes(self) -> bool:
        # Flight SQL metadata doesn't include index info
        return False

    @property
    def supports_triggers(self) -> bool:
        # Flight SQL metadata doesn't include triggers
        return False

    @property
    def supports_sequences(self) -> bool:
        return False

    @classmethod
    def docker_image_patterns(cls) -> tuple[str, ...]:
        """Docker image substrings used to identify Flight SQL servers."""
        return ("sqlflite", "flight-sql", "flightsql")

    @classmethod
    def docker_env_vars(cls) -> dict[str, tuple[str, ...]]:
        """Environment variables used to extract docker credentials."""
        return {
            "user": ("SQLFLITE_USER", "FLIGHT_USER"),
            "password": ("SQLFLITE_PASSWORD", "FLIGHT_PASSWORD"),
            "database": ("SQLFLITE_DATABASE", "FLIGHT_DATABASE"),
        }

    @classmethod
    def docker_default_user(cls) -> str:
        """Default username for Docker containers."""
        return ""

    @classmethod
    def docker_default_port(cls) -> int:
        """Default port for Docker containers."""
        return 31337

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to a Flight SQL server.

        Returns a DBAPI 2.0 connection configured with the appropriate
        authentication and TLS settings.
        """
        try:
            import adbc_driver_flightsql.dbapi as flight_sql
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            raise MissingDriverError(
                self.name, self.install_extra, self.install_package
            ) from e

        port = int(config.port or "8815")

        # Determine TLS mode
        tls_mode = config.get_option("flight_use_tls", "auto")
        if tls_mode == "auto":
            # Auto-detect: use TLS for common HTTPS ports
            use_tls = port in (443, 8443)
        else:
            use_tls = tls_mode == "enabled"

        # Build connection URI
        scheme = "grpc+tls" if use_tls else "grpc"
        uri = f"{scheme}://{config.server}:{port}"

        # Build connection options
        db_kwargs: dict[str, str] = {}

        # Get auth type
        auth_type = config.get_option("flight_auth_type", "basic")

        if auth_type == "basic" and (config.username or config.password):
            db_kwargs["username"] = config.username or ""
            db_kwargs["password"] = config.password or ""
        elif auth_type == "token":
            token = config.get_option("flight_token", "")
            if token:
                db_kwargs["adbc.flight.sql.authorization_header"] = f"Bearer {token}"

        # Skip TLS verification for local testing (optional)
        if use_tls and config.get_option("flight_skip_verify", "false") == "true":
            db_kwargs["adbc.flight.sql.client_option.tls_skip_verify"] = "true"

        conn = flight_sql.connect(uri, db_kwargs=db_kwargs)

        # Store the catalog/database for later use
        conn._sqlit_catalog = config.database or None

        return conn

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works."""
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of catalogs (databases) from Flight SQL."""
        try:
            # Try ADBC's get_objects method if available
            if hasattr(conn, "adbc_get_objects"):
                objects = conn.adbc_get_objects(depth="catalogs")
                table = objects.read_all()
                if "catalog_name" in table.column_names:
                    return [str(val) for val in table["catalog_name"].to_pylist() if val]
            # Fall back to information_schema or SHOW DATABASES
            with conn.cursor() as cursor:
                try:
                    cursor.execute("SHOW DATABASES")
                    return [row[0] for row in cursor.fetchall()]
                except Exception:
                    pass
                try:
                    cursor.execute("SELECT DISTINCT catalog_name FROM information_schema.schemata")
                    return [row[0] for row in cursor.fetchall() if row[0]]
                except Exception:
                    pass
            return []
        except Exception:
            return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from Flight SQL.

        Returns (schema, table_name) tuples.
        """
        try:
            # Try ADBC's get_objects method if available
            if hasattr(conn, "adbc_get_objects"):
                catalog = database or getattr(conn, "_sqlit_catalog", None)
                objects = conn.adbc_get_objects(
                    depth="tables",
                    catalog_filter=catalog,
                    table_types=["TABLE", "BASE TABLE"],
                )
                table = objects.read_all()
                # ADBC returns nested structure, need to flatten
                results = []
                if len(table) > 0:
                    for catalog_batch in table.to_pydict().get("catalog_db_schemas", []):
                        if catalog_batch:
                            for db_schema in catalog_batch:
                                schema_name = db_schema.get("db_schema_name", "") or ""
                                for tbl in db_schema.get("db_schema_tables", []) or []:
                                    table_name = tbl.get("table_name", "")
                                    if table_name:
                                        results.append((schema_name, table_name))
                return results

            # Fall back to information_schema or SHOW TABLES
            with conn.cursor() as cursor:
                try:
                    cursor.execute("SHOW TABLES")
                    return [("", row[0]) for row in cursor.fetchall()]
                except Exception:
                    pass
                try:
                    cursor.execute(
                        "SELECT table_schema, table_name FROM information_schema.tables "
                        "WHERE table_type IN ('TABLE', 'BASE TABLE')"
                    )
                    return [(row[0] or "", row[1]) for row in cursor.fetchall()]
                except Exception:
                    pass
            return []
        except Exception:
            return []

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from Flight SQL."""
        try:
            # Try ADBC's get_objects method if available
            if hasattr(conn, "adbc_get_objects"):
                catalog = database or getattr(conn, "_sqlit_catalog", None)
                objects = conn.adbc_get_objects(
                    depth="tables",
                    catalog_filter=catalog,
                    table_types=["VIEW"],
                )
                table = objects.read_all()
                results = []
                if len(table) > 0:
                    for catalog_batch in table.to_pydict().get("catalog_db_schemas", []):
                        if catalog_batch:
                            for db_schema in catalog_batch:
                                schema_name = db_schema.get("db_schema_name", "") or ""
                                for tbl in db_schema.get("db_schema_tables", []) or []:
                                    table_name = tbl.get("table_name", "")
                                    if table_name:
                                        results.append((schema_name, table_name))
                return results

            # Fall back to information_schema
            with conn.cursor() as cursor:
                try:
                    cursor.execute(
                        "SELECT table_schema, table_name FROM information_schema.tables "
                        "WHERE table_type = 'VIEW'"
                    )
                    return [(row[0] or "", row[1]) for row in cursor.fetchall()]
                except Exception:
                    pass
            return []
        except Exception:
            return []

    def get_columns(
        self,
        conn: Any,
        table: str,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[ColumnInfo]:
        """Get columns for a table from Flight SQL."""
        try:
            # Try ADBC's get_table_schema method if available
            if hasattr(conn, "adbc_get_table_schema"):
                catalog = database or getattr(conn, "_sqlit_catalog", None)
                arrow_schema = conn.adbc_get_table_schema(
                    catalog=catalog,
                    db_schema=schema,
                    table_name=table,
                )
                return [
                    ColumnInfo(
                        name=field.name,
                        data_type=str(field.type),
                        is_primary_key=False,
                    )
                    for field in arrow_schema
                ]

            # Fall back to information_schema
            with conn.cursor() as cursor:
                try:
                    query = (
                        "SELECT column_name, data_type FROM information_schema.columns "
                        f"WHERE table_name = '{table}'"
                    )
                    if schema:
                        query += f" AND table_schema = '{schema}'"
                    cursor.execute(query)
                    return [
                        ColumnInfo(name=row[0], data_type=row[1], is_primary_key=False)
                        for row in cursor.fetchall()
                    ]
                except Exception:
                    pass

            # Last resort: execute a SELECT and get schema from result
            with conn.cursor() as cursor:
                quoted_table = self.quote_identifier(table)
                if schema:
                    quoted_schema = self.quote_identifier(schema)
                    cursor.execute(f"SELECT * FROM {quoted_schema}.{quoted_table} LIMIT 0")
                else:
                    cursor.execute(f"SELECT * FROM {quoted_table} LIMIT 0")

                if cursor.description:
                    return [
                        ColumnInfo(name=desc[0], data_type="unknown", is_primary_key=False)
                        for desc in cursor.description
                    ]
            return []
        except Exception:
            return []

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Flight SQL doesn't support stored procedures."""
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Flight SQL doesn't expose index information."""
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        """Flight SQL doesn't expose trigger information."""
        return []

    def get_sequences(
        self, conn: Any, database: str | None = None
    ) -> list[SequenceInfo]:
        """Flight SQL doesn't expose sequence information."""
        return []

    def quote_identifier(self, name: str) -> str:
        """Quote identifier using double quotes (ANSI SQL standard).

        Most Flight SQL servers follow ANSI SQL quoting conventions.
        """
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(
        self,
        table: str,
        limit: int,
        database: str | None = None,
        schema: str | None = None,
    ) -> str:
        """Build SELECT query with LIMIT (ANSI SQL).

        Uses standard LIMIT syntax which most Flight SQL servers support.
        """
        quoted_table = self.quote_identifier(table)
        if schema:
            quoted_schema = self.quote_identifier(schema)
            return f"SELECT * FROM {quoted_schema}.{quoted_table} LIMIT {limit}"
        return f"SELECT * FROM {quoted_table} LIMIT {limit}"

    def _arrow_table_to_tuples(
        self, table: Any
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Convert an Arrow table to column names and row tuples.

        This handles the conversion from Arrow's columnar format to
        the row-based format that sqlit expects.
        """
        if table is None or len(table) == 0:
            return [], []

        columns = list(table.column_names)

        # Convert to Python objects
        # to_pydict() gives {col_name: [values...]}
        data = table.to_pydict()

        # Transpose to rows
        num_rows = len(table)
        rows = []
        for i in range(num_rows):
            row = tuple(data[col][i] for col in columns)
            rows.append(row)

        return columns, rows

    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]], bool]:
        """Execute a query on Flight SQL server.

        Uses DBAPI 2.0 cursor interface and optionally fetches Arrow table
        for efficient data transfer.
        """
        with conn.cursor() as cursor:
            cursor.execute(query)

            # Try to use Arrow table for efficiency if available
            if hasattr(cursor, "fetch_arrow_table"):
                table = cursor.fetch_arrow_table()
                columns, rows = self._arrow_table_to_tuples(table)
            else:
                # Fall back to standard DBAPI fetchall
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows = [tuple(row) for row in cursor.fetchall()]
                else:
                    columns, rows = [], []

            # Handle row limiting
            truncated = False
            if max_rows is not None and len(rows) > max_rows:
                truncated = True
                rows = rows[:max_rows]

            return columns, rows, truncated

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query statement (INSERT, UPDATE, DELETE, DDL).

        Returns the number of affected rows, or -1 if not available.
        """
        with conn.cursor() as cursor:
            cursor.execute(query)
            return cursor.rowcount if cursor.rowcount >= 0 else -1
