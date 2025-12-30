"""MySQL adapter using PyMySQL (pure Python)."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Any

from ..exceptions import MissingDriverError
from ..schema import get_default_port
from .base import MySQLBaseAdapter, import_driver_module

if TYPE_CHECKING:
    from ...config import ConnectionConfig


def _check_old_mysql_connector() -> bool:
    """Check if the old mysql-connector-python package is installed."""
    return importlib.util.find_spec("mysql.connector") is not None


class MySQLAdapter(MySQLBaseAdapter):
    """Adapter for MySQL using PyMySQL."""

    @classmethod
    def badge_label(cls) -> str:
        return "MySQL"

    @classmethod
    def url_schemes(cls) -> tuple[str, ...]:
        return ("mysql",)

    @classmethod
    def docker_image_patterns(cls) -> tuple[str, ...]:
        return ("mysql",)

    @classmethod
    def docker_env_vars(cls) -> dict[str, tuple[str, ...]]:
        return {
            "user": ("MYSQL_USER",),
            "password": ("MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"),
            "database": ("MYSQL_DATABASE",),
        }

    @classmethod
    def docker_default_user(cls) -> str | None:
        return "root"

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
            pymysql = import_driver_module(
                "pymysql",
                driver_name=self.name,
                extra_name=self.install_extra,
                package_name=self.install_package,
            )
        except MissingDriverError:
            # Check if user has the old mysql-connector-python installed
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

        port = int(config.port or get_default_port("mysql"))
        # PyMySQL resolves 'localhost' to ::1 (IPv6) which often fails.
        # Normalize to 127.0.0.1 to ensure TCP/IP connection works.
        host = config.server
        if host and host.lower() == "localhost":
            host = "127.0.0.1"
        return pymysql.connect(
            host=host,
            port=port,
            database=config.database or None,
            user=config.username,
            password=config.password,
            connect_timeout=10,
            autocommit=True,
            charset="utf8mb4",
        )
