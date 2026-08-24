"""Oracle legacy adapter using oracledb with ROWNUM pagination."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class OracleLegacyAdapter(OracleAdapter):
    """Adapter for Oracle 11g and older using thick client mode."""

    _client_mode_default = "thick"

    @property
    def name(self) -> str:
        return "Oracle Legacy"

    @property
    def install_extra(self) -> str:
        return "oracle"

    @property
    def install_package(self) -> str:
        return "oracledb"

    @property
    def driver_import_names(self) -> tuple[str, ...]:
        return ("oracledb",)

    def get_post_connect_warnings(self, config: ConnectionConfig) -> list[str]:
        mode = str(config.get_option("oracle_client_mode", "thick")).lower()
        if mode == "thin":
            return [
                "Oracle 11g typically requires the Thick client. Use Thick mode if you see connection errors."
            ]
        return []

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build a schema-aware SELECT query with Oracle 11g ROWNUM pagination."""
        qualified = self.catalog_qualified_name(database, schema, table)
        return f"SELECT * FROM (SELECT * FROM {qualified}) WHERE ROWNUM <= {limit}"

    def build_filtered_select_query(self, table: str, column: str, value: Any, limit: int, database: str | None = None, schema: str | None = None) -> str:
        qualified = self.catalog_qualified_name(database, schema, table)
        predicate = f"{self.quote_identifier(column)} = {self.quote_literal(value)}"
        return f"SELECT * FROM (SELECT * FROM {qualified} WHERE {predicate}) WHERE ROWNUM <= {limit}"
