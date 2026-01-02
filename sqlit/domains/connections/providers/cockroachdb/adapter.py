"""CockroachDB adapter using psycopg2 (PostgreSQL wire-compatible)."""

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


class CockroachDBAdapter(PostgresBaseAdapter):
    """Adapter for CockroachDB using psycopg2 (PostgreSQL wire-compatible)."""

    @property
    def name(self) -> str:
        return "CockroachDB"

    @property
    def install_extra(self) -> str:
        return "cockroachdb"

    @property
    def install_package(self) -> str:
        return "psycopg2-binary"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("psycopg2",)

    @property
    def supports_stored_procedures(self) -> bool:
        return False  # CockroachDB has limited stored procedure support

    @property
    def supports_triggers(self) -> bool:
        """Triggers are preview-only in CockroachDB; treat as unsupported by default."""
        return False

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to CockroachDB database."""
        psycopg2 = self._import_driver_module(
            "psycopg2",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("CockroachDB connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("cockroachdb"))
        connect_args: dict[str, Any] = {
            "host": endpoint.host,
            "port": port,
            "database": endpoint.database or "defaultdb",
            "user": endpoint.username,
            "password": endpoint.password,
            "connect_timeout": 10,
        }

        tls_mode = get_tls_mode(config)
        tls_ca, tls_cert, tls_key, tls_key_password = get_tls_files(config)
        has_tls_files = any([tls_ca, tls_cert, tls_key, tls_key_password])

        if tls_mode == TLS_MODE_DEFAULT and not has_tls_files:
            # Default container runs insecure; keep previous behavior.
            connect_args["sslmode"] = TLS_MODE_DISABLE
        elif tls_mode != TLS_MODE_DEFAULT:
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
        # Enable autocommit to avoid transaction issues
        conn.autocommit = True
        return conn

    def get_databases(self, conn: Any) -> list[str]:
        """Get list of databases from CockroachDB."""
        cursor = conn.cursor()
        cursor.execute("SELECT database_name FROM [SHOW DATABASES] ORDER BY database_name")
        return [row[0] for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """CockroachDB has limited stored procedure support - return empty list."""
        return []
