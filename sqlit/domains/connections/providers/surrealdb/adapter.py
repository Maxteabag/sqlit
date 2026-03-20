"""SurrealDB adapter using surrealdb.py SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    IndexInfo,
    SequenceInfo,
    TableInfo,
    TriggerInfo,
)
from sqlit.domains.connections.providers.registry import get_default_port

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class SurrealDBAdapter(DatabaseAdapter):
    """Adapter for SurrealDB using the official Python SDK.

    SurrealDB is a multi-model database that uses SurrealQL,
    a query language similar to SQL but with some differences.
    """

    @property
    def name(self) -> str:
        return "SurrealDB"

    @property
    def install_extra(self) -> str:
        return "surrealdb"

    @property
    def install_package(self) -> str:
        return "surrealdb"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("surrealdb",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True  # Namespace/database hierarchy

    @property
    def supports_cross_database_queries(self) -> bool:
        return False  # Must use() a specific database

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return True

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_sequences(self) -> bool:
        return False

    @property
    def supports_process_worker(self) -> bool:
        # WebSocket connections may not work well across process boundaries
        return False

    @property
    def default_schema(self) -> str:
        return ""

    @property
    def test_query(self) -> str:
        return "RETURN 1"

    def connect(self, config: ConnectionConfig) -> Any:
        surrealdb_module = self._import_driver_module(
            "surrealdb",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("SurrealDB connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("surrealdb"))

        # Build WebSocket URL
        use_ssl = str(config.get_option("use_ssl", "false")).lower() == "true"
        scheme = "wss" if use_ssl else "ws"
        url = f"{scheme}://{endpoint.host}:{port}/rpc"

        # Create sync connection
        db = surrealdb_module.Surreal(url)
        db.connect()

        # Sign in if credentials provided
        if endpoint.username and endpoint.password:
            db.signin({"user": endpoint.username, "pass": endpoint.password})

        # Select namespace and database
        namespace = config.get_option("namespace", "test")
        database = endpoint.database or config.get_option("database", "test")
        db.use(namespace, database)

        return db

    def disconnect(self, conn: Any) -> None:
        if hasattr(conn, "close"):
            conn.close()

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works."""
        result = conn.query("RETURN 1")
        if not result:
            raise Exception("SurrealDB test query returned no result")

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases in the current namespace."""
        try:
            result = conn.query("INFO FOR NS")
            if result and isinstance(result, list) and result[0]:
                info = result[0]
                if isinstance(info, dict) and "databases" in info:
                    return list(info["databases"].keys())
        except Exception:
            pass
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables in the current database."""
        try:
            result = conn.query("INFO FOR DB")
            if result and isinstance(result, list) and result[0]:
                info = result[0]
                if isinstance(info, dict) and "tables" in info:
                    tables = list(info["tables"].keys())
                    return [("", t) for t in sorted(tables)]
        except Exception:
            pass
        return []

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        # SurrealDB doesn't have traditional views
        return []

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get column information for a table.

        SurrealDB is schemaless by default, so we sample records to infer columns.
        If a schema is defined, we use INFO FOR TABLE.
        """
        columns: list[ColumnInfo] = []

        try:
            # First try to get schema info
            result = conn.query(f"INFO FOR TABLE {table}")
            if result and isinstance(result, list) and result[0]:
                info = result[0]
                if isinstance(info, dict) and "fields" in info:
                    for field_name, field_def in info["fields"].items():
                        # field_def might contain type info
                        data_type = "any"
                        if isinstance(field_def, dict) and "type" in field_def:
                            data_type = str(field_def["type"])
                        elif isinstance(field_def, str):
                            # Try to extract type from definition string
                            data_type = field_def.split()[0] if field_def else "any"
                        columns.append(ColumnInfo(name=field_name, data_type=data_type))

            # If no schema fields, sample data to infer columns
            if not columns:
                sample = conn.query(f"SELECT * FROM {table} LIMIT 1")
                if sample and isinstance(sample, list) and sample[0]:
                    first_row = sample[0]
                    if isinstance(first_row, dict):
                        for key in first_row.keys():
                            if key != "id":  # id is always present
                                value = first_row[key]
                                data_type = type(value).__name__ if value is not None else "any"
                                columns.append(ColumnInfo(name=key, data_type=data_type))
                        # Add id column first
                        columns.insert(0, ColumnInfo(name="id", data_type="record"))
        except Exception:
            pass

        return columns

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        """Get list of indexes across all tables."""
        indexes: list[IndexInfo] = []
        try:
            result = conn.query("INFO FOR DB")
            if result and isinstance(result, list) and result[0]:
                info = result[0]
                if isinstance(info, dict) and "tables" in info:
                    for table_name in info["tables"].keys():
                        table_info = conn.query(f"INFO FOR TABLE {table_name}")
                        if table_info and isinstance(table_info, list) and table_info[0]:
                            t_info = table_info[0]
                            if isinstance(t_info, dict) and "indexes" in t_info:
                                for idx_name, idx_def in t_info["indexes"].items():
                                    is_unique = "UNIQUE" in str(idx_def).upper() if idx_def else False
                                    indexes.append(IndexInfo(
                                        name=idx_name,
                                        table_name=table_name,
                                        is_unique=is_unique
                                    ))
        except Exception:
            pass
        return indexes

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return []

    def quote_identifier(self, name: str) -> str:
        # SurrealDB uses backticks for identifiers with special characters
        if any(c in name for c in " -./"):
            escaped = name.replace("`", "``")
            return f"`{escaped}`"
        return name

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        return f"SELECT * FROM {self.quote_identifier(table)} LIMIT {limit}"

    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]:
        """Execute a query and return (columns, rows, truncated)."""
        result = conn.query(query)

        if not result:
            return [], [], False

        # SurrealDB returns a list of results (one per statement)
        # For a single query, we take the first result
        data = result[0] if isinstance(result, list) else result

        # Handle single value returns (like RETURN 1)
        if not isinstance(data, (list, dict)):
            return ["result"], [(data,)], False

        # Handle empty results
        if isinstance(data, list) and not data:
            return [], [], False

        # Handle list of records
        if isinstance(data, list):
            if not data:
                return [], [], False
            first = data[0]
            if isinstance(first, dict):
                columns = list(first.keys())
                all_rows = [tuple(row.get(col) for col in columns) for row in data]
                if max_rows is not None and len(all_rows) > max_rows:
                    return columns, all_rows[:max_rows], True
                return columns, all_rows, False
            # List of non-dict values
            rows = [(v,) for v in (data[:max_rows] if max_rows else data)]
            truncated = max_rows is not None and len(data) > max_rows
            return ["value"], rows, truncated

        # Handle single dict
        if isinstance(data, dict):
            columns = list(data.keys())
            return columns, [tuple(data.values())], False

        return [], [], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query statement."""
        result = conn.query(query)
        # SurrealDB doesn't return row counts in the traditional sense
        # Return 1 if operation succeeded
        if result is not None:
            if isinstance(result, list) and result:
                data = result[0]
                if isinstance(data, list):
                    return len(data)
            return 1
        return 0

    def classify_query(self, query: str) -> bool:
        """Return True if the query is expected to return rows."""
        query_type = query.strip().upper().split()[0] if query.strip() else ""
        # SurrealQL query types that return data
        return query_type in {
            "SELECT", "RETURN", "INFO", "SHOW", "LIVE",
            "CREATE", "INSERT", "UPDATE", "UPSERT", "DELETE"  # These also return the affected records
        }
