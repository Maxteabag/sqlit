"""MySQL adapter using PyMySQL (pure Python)."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.mysql.base import MySQLBaseAdapter
from sqlit.domains.connections.providers.exceptions import MissingDriverError
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


def _check_old_mysql_connector() -> bool:
    """Check if the old mysql-connector-python package is installed."""
    return importlib.util.find_spec("mysql.connector") is not None


class MySQLAdapter(MySQLBaseAdapter):
    """Adapter for MySQL using PyMySQL."""

    @property
    def name(self) -> str:
        return "MySQL"

    @property
    def install_extra(self) -> str:
        return "mysql"

    @property
    def install_package(self) -> str:
        return "PyMySQL"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("pymysql",)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MySQL database."""
        try:
            pymysql = self._import_driver_module(
                "pymysql",
                driver_name=self.name,
                extra_name=self.install_extra,
                package_name=self.install_package,
            )
        except MissingDriverError:
            if _check_old_mysql_connector():
                raise MissingDriverError(
                    self.name,
                    self.install_extra,
                    self.install_package,
                    module_name="pymysql",
                    import_error=(
                        "MySQL driver has changed from mysql-connector-python to PyMySQL.\n"
                        "Please uninstall the old package and install PyMySQL:\n"
                        "  pip uninstall mysql-connector-python\n"
                        "  pip install PyMySQL"
                    ),
                ) from None
            raise

        endpoint = config.tcp_endpoint
        if endpoint is None:
            raise ValueError("MySQL connections require a TCP-style endpoint.")
        port = int(endpoint.port or get_default_port("mysql"))
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

        conn = pymysql.connect(**connect_args)

        # Auto-sync charset with server to handle legacy encodings (e.g., TIS-620, Latin1).
        # This ensures data is read correctly when the database uses a non-UTF-8 charset.
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT @@character_set_database")
            row = cursor.fetchone()
            if row:
                server_charset = row[0]
                # Only switch if server uses a different charset than our default (utf8mb4)
                if server_charset and server_charset.lower() != "utf8mb4":
                    # Use set_charset() which both sends SET NAMES AND updates
                    # PyMySQL's internal encoding for proper byte decoding
                    conn.set_charset(server_charset)
            cursor.close()
        except Exception:
            # If charset sync fails, continue with default - better than failing completely
            pass

        return conn
