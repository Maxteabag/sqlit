"""Trino adapter using trino client."""

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
from sqlit.domains.connections.providers.registry import get_default_port

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class TrinoAdapter(CursorBasedAdapter):
    """Adapter for Trino (PrestoSQL) using trino client."""

    @property
    def name(self) -> str:
        return "Trino"

    @property
    def install_extra(self) -> str:
        return "trino"

    @property
    def install_package(self) -> str:
        return "trino"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("trino",)

    @property
    def supports_multiple_databases(self) -> bool:
        return True

    @property
    def supports_cross_database_queries(self) -> bool:
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        return False

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_sequences(self) -> bool:
        return False

    @property
    def default_schema(self) -> str:
        return ""

    def connect(self, config: ConnectionConfig) -> Any:
        trino_dbapi = self._import_driver_module(
            "trino.dbapi",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Trino connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("trino"))

        http_scheme = str(config.get_option("http_scheme", "http"))
        catalog = endpoint.database or config.get_option("catalog")
        schema = config.get_option("schema")

        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "port": port,
            "user": endpoint.username,
            "http_scheme": http_scheme,
        }
        if catalog:
            connect_args["catalog"] = catalog
        if schema:
            connect_args["schema"] = schema

        if endpoint.password:
            try:
                from trino.auth import BasicAuthentication
            except Exception as exc:
                raise ValueError("Trino password authentication requires trino.auth.BasicAuthentication") from exc
            connect_args["auth"] = BasicAuthentication(endpoint.username, endpoint.password)

        return trino_dbapi.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        cursor = conn.cursor()
        cursor.execute("SHOW CATALOGS")
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_schema, table_name FROM "
                f"{self.quote_identifier(database)}.information_schema.tables "
                "WHERE table_type = 'BASE TABLE' "
                "ORDER BY table_schema, table_name"
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]

        cursor.execute("SHOW TABLES")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_schema, table_name FROM "
                f"{self.quote_identifier(database)}.information_schema.views "
                "ORDER BY table_schema, table_name"
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]

        cursor.execute("SHOW VIEWS")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        schema_name = schema or self.default_schema
        if not schema_name:
            return []
        if database:
            cursor.execute(
                "SELECT column_name, data_type FROM "
                f"{self.quote_identifier(database)}.information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                (schema_name, table),
            )
        else:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                (schema_name, table),
            )
        return [ColumnInfo(name=row[0], data_type=row[1]) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        return []

    def get_indexes(self, conn: Any, database: str | None = None) -> list[IndexInfo]:
        return []

    def get_triggers(self, conn: Any, database: str | None = None) -> list[TriggerInfo]:
        return []

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        return []

    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        schema_name = schema or self.default_schema
        if database and schema_name:
            return f'SELECT * FROM "{database}"."{schema_name}"."{table}" LIMIT {limit}'
        if database:
            return f'SELECT * FROM "{database}"."{table}" LIMIT {limit}'
        if schema_name:
            return f'SELECT * FROM "{schema_name}"."{table}" LIMIT {limit}'
        return f'SELECT * FROM "{table}" LIMIT {limit}'
