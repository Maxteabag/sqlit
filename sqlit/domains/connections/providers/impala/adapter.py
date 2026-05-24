"""Impala adapter using impyla."""

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


class ImpalaAdapter(CursorBasedAdapter):
    """Adapter for Apache Impala using impyla."""

    @property
    def name(self) -> str:
        return "Impala"

    @property
    def install_extra(self) -> str:
        return "impala"

    @property
    def install_package(self) -> str:
        return "impyla"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("impala.dbapi",)

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
        return False  # Impala uses partitions, not traditional indexes

    @property
    def supports_triggers(self) -> bool:
        return False

    @property
    def supports_sequences(self) -> bool:
        return False

    @property
    def system_databases(self) -> frozenset[str]:
        return frozenset({"_impala_builtins"})

    @property
    def default_schema(self) -> str:
        return ""

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a default database for unqualified queries."""
        if not database:
            return config
        return config.with_endpoint(database=database)

    def connect(self, config: ConnectionConfig) -> Any:
        impala_dbapi = self._import_driver_module(
            "impala.dbapi",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("Impala connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("impala"))

        auth_mechanism = str(config.get_option("auth_mechanism", "NOSASL"))
        use_ssl = str(config.get_option("use_ssl", "false")).lower() == "true"

        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "port": port,
            "auth_mechanism": auth_mechanism,
            "use_ssl": use_ssl,
        }

        if endpoint.database:
            connect_args["database"] = endpoint.database

        if endpoint.username:
            connect_args["user"] = endpoint.username
        if endpoint.password:
            connect_args["password"] = endpoint.password

        connect_args.update(config.extra_options)
        return impala_dbapi.connect(**connect_args)

    def get_databases(self, conn: Any) -> list[str]:
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        return [row[0] for row in cursor.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(f"SHOW TABLES IN {self.quote_identifier(database)}")
        else:
            cursor.execute("SHOW TABLES")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        # Impala doesn't distinguish views in SHOW TABLES by default
        # We can query from information_schema if available
        cursor = conn.cursor()
        try:
            if database:
                cursor.execute(
                    f"SELECT table_name FROM {self.quote_identifier(database)}.information_schema.tables "
                    "WHERE table_type = 'VIEW' ORDER BY table_name"
                )
            else:
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_type = 'VIEW' ORDER BY table_name"
                )
            return [("", row[0]) for row in cursor.fetchall()]
        except Exception:
            # information_schema might not be available
            return []

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        cursor = conn.cursor()
        if database:
            cursor.execute(f"DESCRIBE {self.quote_identifier(database)}.{self.quote_identifier(table)}")
        else:
            cursor.execute(f"DESCRIBE {self.quote_identifier(table)}")
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
        escaped = name.replace("`", "``")
        return f"`{escaped}`"

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        if database:
            return f"SELECT * FROM `{database}`.`{table}` LIMIT {limit}"
        return f"SELECT * FROM `{table}` LIMIT {limit}"
