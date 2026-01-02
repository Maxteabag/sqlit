"""PostgreSQL adapter using psycopg2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.postgresql.base import PostgresBaseAdapter
from sqlit.domains.connections.providers.registry import get_default_port
from sqlit.domains.connections.providers.tls import (
    TLS_MODE_DEFAULT,
    TLS_MODE_DISABLE,
    get_tls_files,
    get_tls_mode,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class PostgreSQLAdapter(PostgresBaseAdapter):
    """Adapter for PostgreSQL using psycopg2."""

    @property
    def name(self) -> str:
        return "PostgreSQL"

    @property
    def install_extra(self) -> str:
        return "postgres"

    @property
    def install_package(self) -> str:
        return "psycopg2-binary"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("psycopg2",)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to PostgreSQL database."""
        psycopg2 = self._import_driver_module(
            "psycopg2",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("PostgreSQL connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("postgresql"))
        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "port": port,
            "database": endpoint.database or "postgres",
            "user": endpoint.username,
            "password": endpoint.password,
            "connect_timeout": 10,
        }

        tls_mode = get_tls_mode(config)
        tls_ca, tls_cert, tls_key, tls_key_password = get_tls_files(config)
        if tls_mode != TLS_MODE_DEFAULT:
            connect_args["sslmode"] = tls_mode
        if tls_mode != TLS_MODE_DISABLE:
            if tls_ca:
                connect_args["sslrootcert"] = tls_ca
            if tls_cert:
                connect_args["sslcert"] = tls_cert
            if tls_key:
                connect_args["sslkey"] = tls_key
            if tls_key_password:
                connect_args["sslpassword"] = tls_key_password

        conn = psycopg2.connect(**connect_args)
        # Enable autocommit to avoid "transaction aborted" errors on failed statements
        conn.autocommit = True
        return conn

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from PostgreSQL."""
        cursor = conn.cursor()
        cursor.execute("SELECT datname FROM pg_database " "WHERE datistemplate = false ORDER BY datname")
        return [row[0] for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures/functions from PostgreSQL."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT routine_name FROM information_schema.routines "
            "WHERE routine_schema = 'public' AND routine_type = 'FUNCTION' "
            "ORDER BY routine_name"
        )
        return [row[0] for row in cursor.fetchall()]
