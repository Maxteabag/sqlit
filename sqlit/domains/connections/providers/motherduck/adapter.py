"""MotherDuck adapter for cloud DuckDB."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import ForeignKeyInfo, TableInfo
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

    def get_foreign_keys(self, conn: Any, database: str | None = None) -> list[ForeignKeyInfo]:
        """Get foreign keys from a specific MotherDuck database."""
        query = (
            "SELECT "
            "  tc.constraint_name, "
            "  tc.table_schema AS source_schema, "
            "  tc.table_name AS source_table, "
            "  kcu.column_name AS source_column, "
            "  kcu2.table_schema AS target_schema, "
            "  kcu2.table_name AS target_table, "
            "  kcu2.column_name AS target_column "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.referential_constraints rc "
            "  ON tc.constraint_name = rc.constraint_name "
            "  AND tc.constraint_schema = rc.constraint_schema "
            "JOIN information_schema.key_column_usage kcu2 "
            "  ON rc.unique_constraint_name = kcu2.constraint_name "
            "  AND rc.unique_constraint_schema = kcu2.constraint_schema "
            "  AND kcu.ordinal_position = kcu2.ordinal_position "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "AND tc.table_schema NOT IN ('pg_catalog', 'information_schema') "
        )
        if database:
            query += "AND tc.table_catalog = ? "
            query += "ORDER BY tc.table_name, tc.constraint_name"
            result = conn.execute(query, (database,))
        else:
            query += "ORDER BY tc.table_name, tc.constraint_name"
            result = conn.execute(query)
        return [
            ForeignKeyInfo(
                constraint_name=row[0],
                source_schema=row[1],
                source_table=row[2],
                source_column=row[3],
                target_schema=row[4],
                target_table=row[5],
                target_column=row[6],
            )
            for row in result.fetchall()
        ]

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
