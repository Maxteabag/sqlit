"""MySQL adapter using PyMySQL (pure Python)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..schema import get_default_port
from .base import MySQLBaseAdapter, import_driver_module

if TYPE_CHECKING:
    from ...config import ConnectionConfig


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
        pymysql = import_driver_module(
            "pymysql",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        port = int(config.port or get_default_port("mysql"))
        return pymysql.connect(
            host=config.server,
            port=port,
            database=config.database or None,
            user=config.username,
            password=config.password,
            connect_timeout=10,
            autocommit=True,
            charset="utf8mb4",
        )
