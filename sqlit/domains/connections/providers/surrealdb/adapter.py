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


def _to_plain(value: Any) -> Any:
    """Convert SurrealDB SDK types (RecordID, etc.) into something printable."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    cls_name = type(value).__name__
    if cls_name == "RecordID":
        return str(value)
    return value


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

        # Surreal() is blocking in surrealdb>=1.0; opens the socket in __init__
        db = surrealdb_module.Surreal(url)

        if endpoint.username and endpoint.password:
            db.signin({"username": endpoint.username, "password": endpoint.password})

        namespace = config.get_option("namespace", "test")
        database = endpoint.database or config.get_option("database", "test")
        db.use(namespace, database)

        return db

    def disconnect(self, conn: Any) -> None:
        if hasattr(conn, "close"):
            conn.close()

    def execute_test_query(self, conn: Any) -> None:
        """Execute a simple query to verify the connection works."""
        # query() raises on error; a successful RETURN 1 returns the int 1.
        conn.query("RETURN 1")

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases in the current namespace."""
        try:
            info = conn.query("INFO FOR NS")
            if isinstance(info, dict) and "databases" in info:
                return list(info["databases"].keys())
        except Exception:
            pass
        return []

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables in the current database."""
        try:
            info = conn.query("INFO FOR DB")
            if isinstance(info, dict) and "tables" in info:
                return [("", t) for t in sorted(info["tables"].keys())]
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
            info = conn.query(f"INFO FOR TABLE {table}")
            if isinstance(info, dict) and "fields" in info and info["fields"]:
                # SurrealDB's INFO FOR TABLE only lists explicitly-defined
                # fields, but every record implicitly has an `id`. Surface it
                # as the primary key column so consumers can detect it.
                columns.append(
                    ColumnInfo(name="id", data_type="record", is_primary_key=True)
                )
                for field_name, field_def in info["fields"].items():
                    data_type = "any"
                    if isinstance(field_def, dict) and "type" in field_def:
                        data_type = str(field_def["type"])
                    elif isinstance(field_def, str):
                        # e.g. "DEFINE FIELD name ON t1 TYPE string PERMISSIONS FULL"
                        parts = field_def.split()
                        if "TYPE" in parts:
                            idx = parts.index("TYPE")
                            if idx + 1 < len(parts):
                                data_type = parts[idx + 1]
                        elif parts:
                            data_type = parts[0]
                    columns.append(ColumnInfo(name=field_name, data_type=data_type))

            if not columns:
                sample = conn.query(f"SELECT * FROM {table} LIMIT 1")
                if isinstance(sample, list) and sample:
                    first_row = sample[0]
                    if isinstance(first_row, dict):
                        for key in first_row.keys():
                            if key == "id":
                                continue
                            value = first_row[key]
                            data_type = type(value).__name__ if value is not None else "any"
                            columns.append(ColumnInfo(name=key, data_type=data_type))
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
            info = conn.query("INFO FOR DB")
            if not (isinstance(info, dict) and "tables" in info):
                return []
            for table_name in info["tables"].keys():
                t_info = conn.query(f"INFO FOR TABLE {table_name}")
                if not (isinstance(t_info, dict) and "indexes" in t_info):
                    continue
                for idx_name, idx_def in t_info["indexes"].items():
                    is_unique = "UNIQUE" in str(idx_def).upper() if idx_def else False
                    indexes.append(IndexInfo(
                        name=idx_name,
                        table_name=table_name,
                        is_unique=is_unique,
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
        """Execute a query and return (columns, rows, truncated).

        surrealdb>=1.0 returns the query result already unwrapped: scalars for
        RETURN, a dict for INFO, and a list[dict] for SELECT.
        """
        data = conn.query(query)

        if data is None:
            return [], [], False

        if isinstance(data, list):
            if not data:
                return [], [], False
            first = data[0]
            if isinstance(first, dict):
                columns = list(first.keys())
                rows = [
                    tuple(_to_plain(row.get(col)) for col in columns) for row in data
                ]
                if max_rows is not None and len(rows) > max_rows:
                    return columns, rows[:max_rows], True
                return columns, rows, False
            rows = [(_to_plain(v),) for v in (data[:max_rows] if max_rows else data)]
            truncated = max_rows is not None and len(data) > max_rows
            return ["value"], rows, truncated

        if isinstance(data, dict):
            columns = list(data.keys())
            return columns, [tuple(_to_plain(v) for v in data.values())], False

        # Scalar returns (int, str, bool, etc.)
        return ["result"], [(_to_plain(data),)], False

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-query statement."""
        result = conn.query(query)
        if result is None:
            return 0
        if isinstance(result, list):
            return len(result)
        return 1

    def classify_query(self, query: str) -> bool:
        """Return True if the query is expected to return rows."""
        query_type = query.strip().upper().split()[0] if query.strip() else ""
        # SurrealQL query types that return data
        return query_type in {
            "SELECT", "RETURN", "INFO", "SHOW", "LIVE",
            "CREATE", "INSERT", "UPDATE", "UPSERT", "DELETE"  # These also return the affected records
        }
