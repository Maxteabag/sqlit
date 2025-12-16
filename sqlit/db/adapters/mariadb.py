"""MariaDB adapter using mariadb connector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..schema import get_default_port
from .base import ColumnInfo, MySQLBaseAdapter, TableInfo

if TYPE_CHECKING:
    from ...config import ConnectionConfig


class MariaDBAdapter(MySQLBaseAdapter):
    """Adapter for MariaDB using mariadb connector.

    MariaDB uses ? placeholders instead of %s, so we override the
    introspection methods that use parameterized queries.
    """

    @property
    def name(self) -> str:
        return "MariaDB"

    @property
    def install_extra(self) -> str:
        return "mariadb"

    @property
    def install_package(self) -> str:
        return "mariadb"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("mariadb",)

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MariaDB database."""
        try:
            import mariadb
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        port = int(config.port or get_default_port("mariadb"))
        mariadb_any: Any = mariadb
        return mariadb_any.connect(
            host=config.server,
            port=port,
            database=config.database or None,
            user=config.username,
            password=config.password,
            connect_timeout=10,
        )

    # MariaDB connector uses ? placeholders instead of %s, so override methods with params

    def get_tables(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of tables from MariaDB. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = ? AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (database,),
            )
        else:
            cursor.execute("SHOW TABLES")
        return [("", row[0]) for row in cursor.fetchall()]

    def get_views(self, conn: Any, database: str | None = None) -> list[TableInfo]:
        """Get list of views from MariaDB. Returns (schema, name) with empty schema."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT table_name FROM information_schema.views " "WHERE table_schema = ? ORDER BY table_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT table_name FROM information_schema.views " "WHERE table_schema = DATABASE() ORDER BY table_name"
            )
        return [("", row[0]) for row in cursor.fetchall()]

    def get_columns(
        self, conn: Any, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Get columns for a table from MariaDB. Schema parameter is ignored."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? "
                "ORDER BY ordinal_position",
                (database, table),
            )
        else:
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = ? "
                "ORDER BY ordinal_position",
                (table,),
            )
        return [ColumnInfo(name=row[0], data_type=row[1]) for row in cursor.fetchall()]

    def get_procedures(self, conn: Any, database: str | None = None) -> list[str]:
        """Get stored procedures from MariaDB."""
        cursor = conn.cursor()
        if database:
            cursor.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = ? AND routine_type = 'PROCEDURE' "
                "ORDER BY routine_name",
                (database,),
            )
        else:
            cursor.execute(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE' "
                "ORDER BY routine_name"
            )
        return [row[0] for row in cursor.fetchall()]
