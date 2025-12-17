"""Cloudflare D1 database adapter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .base import ColumnInfo, DatabaseAdapter, TableInfo

if TYPE_CHECKING:
    import requests

    from ...config import ConnectionConfig


@dataclass
class D1Connection:
    """Holds connection details for a D1 database."""

    session: requests.Session
    account_id: str
    database_id: str


class D1Adapter(DatabaseAdapter):
    """Adapter for Cloudflare D1."""

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("requests",)

    def _api_base_url(self) -> str:
        return os.environ.get("D1_API_BASE_URL", "https://api.cloudflare.com").rstrip("/")

    @property
    def name(self) -> str:
        """Human-readable name for this database type."""
        return "Cloudflare D1"

    @property
    def install_extra(self) -> str:
        return "d1"

    @property
    def install_package(self) -> str:
        return "requests"

    @property
    def supports_multiple_databases(self) -> bool:
        """D1 supports multiple databases under a single account."""
        return True

    @property
    def supports_stored_procedures(self) -> bool:
        """D1 is SQLite-based and does not support stored procedures."""
        return False

    def connect(self, config: ConnectionConfig) -> D1Connection:
        """Establishes a 'connection' to D1 by preparing authenticated session."""
        try:
            import requests
        except ImportError as e:
            from ...db.exceptions import MissingDriverError

            if not self.install_extra or not self.install_package:
                raise e
            raise MissingDriverError(self.name, self.install_extra, self.install_package) from e

        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {config.password}"})
        account_id = config.server

        if not config.database:
            raise ValueError("Database name is required for Cloudflare D1 connection.")

        database_id = self._find_database_id_by_name(session, account_id, config.database)
        if not database_id:
            raise ConnectionError(f"Cloudflare D1 database '{config.database}' not found.")

        return D1Connection(session=session, account_id=account_id, database_id=database_id)

    def _get_all_databases(self, session: requests.Session, account_id: str) -> list[dict[str, Any]]:
        """Fetches all D1 databases for an account."""
        api_url = f"{self._api_base_url()}/client/v4/accounts/{account_id}/d1/database"
        response = session.get(api_url)
        response.raise_for_status()
        data = cast(dict[str, Any], response.json())
        result = data.get("result", [])
        if not isinstance(result, list):
            return []
        return [cast(dict[str, Any], item) for item in result if isinstance(item, dict)]

    def _find_database_id_by_name(self, session: requests.Session, account_id: str, name: str) -> str | None:
        """Finds a D1 database's UUID by its name."""
        databases = self._get_all_databases(session, account_id)
        for db in databases:
            if db.get("name") == name:
                return db.get("uuid")
        return None

    def get_databases(self, conn: D1Connection) -> list[str]:
        """Gets a list of all database names for the account."""
        databases = self._get_all_databases(conn.session, conn.account_id)
        return [db["name"] for db in databases if "name" in db]

    def _execute(self, conn: D1Connection, query: str) -> dict[str, Any]:
        """Internal method to run a command on the D1 execute endpoint."""
        api_url = f"{self._api_base_url()}/client/v4/accounts/{conn.account_id}/d1/database/{conn.database_id}/execute"
        response = conn.session.post(api_url, json={"sql": query})
        response.raise_for_status()
        # The result is a list containing a single result object
        data = cast(dict[str, Any], response.json())
        result_list = data.get("result", [])
        if not isinstance(result_list, list) or not result_list or not isinstance(result_list[0], dict):
            raise RuntimeError("Unexpected D1 API response format")
        return cast(dict[str, Any], result_list[0])

    def get_tables(self, conn: D1Connection, database: str | None = None) -> list[TableInfo]:
        """Gets tables using PRAGMA."""
        result = self._execute(conn, "PRAGMA table_list;")
        tables = []
        rows = result.get("results", [])
        if not isinstance(rows, list):
            return []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("type") == "table" and not row.get("name", "").startswith("sqlite_"):
                tables.append((row.get("schema", ""), row.get("name", "")))
        return tables

    def get_views(self, conn: D1Connection, database: str | None = None) -> list[TableInfo]:
        """Gets views using PRAGMA."""
        result = self._execute(conn, "PRAGMA table_list;")
        views = []
        rows = result.get("results", [])
        if not isinstance(rows, list):
            return []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("type") == "view":
                views.append((row.get("schema", ""), row.get("name", "")))
        return views

    def get_columns(
        self, conn: D1Connection, table: str, database: str | None = None, schema: str | None = None
    ) -> list[ColumnInfo]:
        """Gets table columns using PRAGMA."""
        result = self._execute(conn, f"PRAGMA table_info({self.quote_identifier(table)});")
        rows = result.get("results", [])
        if not isinstance(rows, list):
            return []
        cols: list[ColumnInfo] = []
        for col in rows:
            if not isinstance(col, dict):
                continue
            name = col.get("name")
            data_type = col.get("type")
            # pk > 0 indicates column is part of primary key
            pk_value = col.get("pk", 0)
            is_pk = isinstance(pk_value, int) and pk_value > 0
            if isinstance(name, str) and isinstance(data_type, str):
                cols.append(ColumnInfo(name=name, data_type=data_type, is_primary_key=is_pk))
        return cols

    def get_procedures(self, conn: D1Connection, database: str | None = None) -> list[str]:
        """Returns an empty list as D1 does not support stored procedures."""
        return []

    def quote_identifier(self, name: str) -> str:
        """Quotes an identifier with double quotes."""
        return f'"{name}"'

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Builds a standard SELECT ... LIMIT query."""
        return f"SELECT * FROM {self.quote_identifier(table)} LIMIT {limit}"

    def execute_query(
        self, conn: D1Connection, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]:
        """Executes a query and returns results in the expected format."""
        result = self._execute(conn, query)
        rows_dicts = result.get("results", [])
        if not isinstance(rows_dicts, list):
            return [], [], False
        rows_dicts = [row for row in rows_dicts if isinstance(row, dict)]

        if not rows_dicts:
            return [], [], False

        columns = [str(k) for k in rows_dicts[0].keys()]
        rows = [tuple(row.values()) for row in rows_dicts]

        # D1 doesn't have a concept of server-side cursor, so we can't easily tell if truncated
        # unless we add `LIMIT max_rows + 1` to the query, which is complex here.
        # For now, we assume not truncated.
        truncated = False
        if max_rows is not None and len(rows) > max_rows:
            rows = rows[:max_rows]
            truncated = True

        return columns, rows, truncated

    def execute_non_query(self, conn: D1Connection, query: str) -> int:
        """Executes a non-query statement and returns rows affected."""
        result = self._execute(conn, query)
        meta = result.get("meta", {})
        # D1 provides `rows_written` for mutations.
        if not isinstance(meta, dict):
            return 0
        return int(meta.get("rows_written", 0) or 0)
