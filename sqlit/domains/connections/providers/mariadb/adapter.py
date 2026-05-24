"""MariaDB adapter using PyMySQL (pure Python)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.adapters.base import SequenceInfo
from sqlit.domains.connections.providers.mysql.base import MySQLBaseAdapter
from sqlit.domains.connections.providers.registry import get_default_port
from sqlit.domains.connections.providers.tls import (
    TLS_MODE_DEFAULT,
    TLS_MODE_DISABLE,
    get_tls_files,
    get_tls_mode,
    tls_mode_verifies_cert,
    tls_mode_verifies_hostname,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class MariaDBAdapter(MySQLBaseAdapter):
    """Adapter for MariaDB using PyMySQL.

    PyMySQL speaks the MySQL/MariaDB wire protocol and is pure Python, so it
    works on any platform without a system-level C library. It also handles
    legacy charsets like TIS-620 and Latin1 that the MariaDB C connector
    cannot read.
    """

    @property
    def name(self) -> str:
        return "MariaDB"

    @property
    def install_extra(self) -> str:
        return "mariadb"

    @property
    def install_package(self) -> str:
        return "PyMySQL"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("pymysql",)

    @property
    def supports_sequences(self) -> bool:
        """MariaDB 10.3+ supports sequences."""
        return getattr(self, "_supports_sequences", True)

    def get_post_connect_warnings(self, config: ConnectionConfig) -> list[str]:
        if self.supports_sequences:
            return []
        version = getattr(self, "_server_version_str", None)
        if isinstance(version, str) and version:
            return [f"MariaDB {version} does not support sequences (requires 10.3+)"]
        return ["MariaDB does not support sequences (requires 10.3+)"]

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MariaDB database."""
        pymysql = self._import_driver_module(
            "pymysql",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("MariaDB connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("mariadb"))
        host = endpoint.host
        if host and host.lower() == "localhost":
            host = "127.0.0.1"
        connect_args: dict[str, Any] = {
            "host": host,
            "port": port,
            "database": endpoint.database or None,
            "user": endpoint.username,
            "password": endpoint.password,
            "connect_timeout": 10,
            "autocommit": True,
            "charset": "utf8mb4",
        }

        tls_mode = get_tls_mode(config)
        tls_ca, tls_cert, tls_key, _ = get_tls_files(config)
        has_tls_files = any([tls_ca, tls_cert, tls_key])
        if tls_mode != TLS_MODE_DISABLE and (tls_mode != TLS_MODE_DEFAULT or has_tls_files):
            import ssl

            ssl_params: dict[str, Any] = {}
            if tls_ca:
                ssl_params["ca"] = tls_ca
            if tls_cert:
                ssl_params["cert"] = tls_cert
            if tls_key:
                ssl_params["key"] = tls_key

            if tls_mode_verifies_cert(tls_mode):
                ssl_params["cert_reqs"] = ssl.CERT_REQUIRED
            else:
                ssl_params["cert_reqs"] = ssl.CERT_NONE

            ssl_params["check_hostname"] = tls_mode_verifies_hostname(tls_mode)
            connect_args["ssl"] = ssl_params

        connect_args.update(config.extra_options)
        conn = pymysql.connect(**connect_args)

        # Auto-sync charset with server to handle legacy encodings (e.g., TIS-620, Latin1).
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT @@character_set_database")
            row = cursor.fetchone()
            if row:
                server_charset = row[0]
                if server_charset and server_charset.lower() != "utf8mb4":
                    conn.set_charset(server_charset)
            cursor.close()
        except Exception:
            pass

        self._supports_sequences = self._detect_sequences_support(conn)
        return conn

    def _detect_sequences_support(self, conn: Any) -> bool:
        """Determine whether the server supports sequences (MariaDB 10.3+)."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            row = cursor.fetchone()
        except Exception:
            return True

        if not row or not isinstance(row[0], str):
            return True

        self._server_version_str = row[0]
        match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", row[0])
        if not match:
            return True

        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3) or 0)
        return (major, minor, patch) >= (10, 3, 0)

    def get_sequences(self, conn: Any, database: str | None = None) -> list[SequenceInfo]:
        """Get sequences from MariaDB 10.3+."""
        if not self.supports_sequences:
            return []
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = %s "
                "ORDER BY sequence_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT sequence_name FROM information_schema.sequences "
                "WHERE sequence_schema = DATABASE() "
                "ORDER BY sequence_name"
            )
        return [SequenceInfo(name=row[0]) for row in cursor.fetchall()]

    def get_sequence_definition(
        self, conn: Any, sequence_name: str, database: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a MariaDB sequence."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT start_value, increment, minimum_value, maximum_value, cycle_option "
                "FROM information_schema.sequences "
                "WHERE sequence_schema = %s AND sequence_name = %s",
                (database, sequence_name),
            )
        else:
            cursor.execute(
                "SELECT start_value, increment, minimum_value, maximum_value, cycle_option "
                "FROM information_schema.sequences "
                "WHERE sequence_schema = DATABASE() AND sequence_name = %s",
                (sequence_name,),
            )
        row = cursor.fetchone()
        if row:
            return {
                "name": sequence_name,
                "start_value": row[0],
                "increment": row[1],
                "min_value": row[2],
                "max_value": row[3],
                "cycle": row[4] == 1,
            }
        return {
            "name": sequence_name,
            "start_value": None,
            "increment": None,
            "min_value": None,
            "max_value": None,
            "cycle": None,
        }
