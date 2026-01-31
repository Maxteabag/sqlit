"""MotherDuck adapter for cloud DuckDB."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import TableInfo
from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class MotherDuckAdapter(DuckDBAdapter):
    """Adapter for MotherDuck cloud DuckDB service."""

    @property
    def name(self) -> str:
        return "MotherDuck"

    @property
    def supports_process_worker(self) -> bool:
        """Disable process worker to avoid segfault when switching from other DBs.

        The MotherDuck/DuckDB native library has issues when loaded in a subprocess
        that has already loaded other database drivers. Running in the main process
        avoids this issue.
        """
        return False

    @property
    def supports_multiple_databases(self) -> bool:
        """MotherDuck supports multiple databases."""
        return True

    def apply_database_override(self, config: ConnectionConfig, database: str) -> ConnectionConfig:
        """Apply a default database for unqualified queries."""
        if not database:
            return config
        return config.with_endpoint(database=database)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MotherDuck cloud database."""
        duckdb = self._import_driver_module(
            "duckdb",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        # Get database from endpoint (optional - empty means browse all)
        database = ""
        if config.tcp_endpoint:
            database = config.tcp_endpoint.database or ""

        # Get token from tcp_endpoint.password (stored in keyring)
        token = ""
        if config.tcp_endpoint:
            token = config.tcp_endpoint.password or ""

        if not token:
            raise ValueError("MotherDuck connections require an access token.")

        # Connect with or without specific database
        if database:
            conn_str = f"md:{database}?motherduck_token={token}"
        else:
            conn_str = f"md:?motherduck_token={token}"

        duckdb_any: Any = duckdb
        return duckdb_any.connect(conn_str)

    def get_databases(self, conn: Any) -> list[str]:
        """List all MotherDuck databases."""
        result = conn.execute("SELECT database_name FROM duckdb_databases() WHERE NOT internal")
        return [row[0] for row in result.fetchall()]

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get tables from a specific MotherDuck database."""
        if database:
            result = conn.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_catalog = ? "
                "AND table_type = 'BASE TABLE' "
                "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_schema, table_name",
                (database,),
            )
        else:
            result = conn.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type = 'BASE TABLE' "
                "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_schema, table_name"
            )
        return [(row[0], row[1]) for row in result.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get views from a specific MotherDuck database."""
        if database:
            result = conn.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_catalog = ? "
                "AND table_type = 'VIEW' "
                "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_schema, table_name",
                (database,),
            )
        else:
            result = conn.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_type = 'VIEW' "
                "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_schema, table_name"
            )
        return [(row[0], row[1]) for row in result.fetchall()]

    def build_select_query(
        self, table: str, limit: int, database: str | None = None, schema: str | None = None
    ) -> str:
        """Build SELECT LIMIT query for MotherDuck.

        MotherDuck requires three-part names: database.schema.table
        """
        schema = schema or "main"
        if database:
            return f'SELECT * FROM "{database}"."{schema}"."{table}" LIMIT {limit}'
        return f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
