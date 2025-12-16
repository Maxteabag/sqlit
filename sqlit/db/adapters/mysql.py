"""MySQL adapter using mysql-connector-python."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..schema import get_default_port
from .base import MySQLBaseAdapter

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class MySQLAdapter(MySQLBaseAdapter):
    """Adapter for MySQL using mysql-connector-python."""

    @property
    def name(self) -> str:
        return "MySQL"

    @property
    def install_extra(self) -> str:
        return "mysql"

    @property
    def install_package(self) -> str:
        return "mysql-connector-python"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("mysql.connector",)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MySQL database."""
        try:
            import mysql.connector
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        port = int(config.port or get_default_port("mysql"))
        return mysql.connector.connect(
            host=config.server,
            port=port,
            database=config.database or None,
            user=config.username,
            password=config.password,
            connection_timeout=10,
        )
