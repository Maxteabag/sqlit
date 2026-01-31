"""MotherDuck adapter for cloud DuckDB."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class MotherDuckAdapter(DuckDBAdapter):
    """Adapter for MotherDuck cloud DuckDB service."""

    @property
    def name(self) -> str:
        return "MotherDuck"

    @property
    def supports_process_worker(self) -> bool:
        """MotherDuck handles concurrency server-side."""
        return True

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to MotherDuck cloud database."""
        duckdb = self._import_driver_module(
            "duckdb",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )

        # Get database from file_path
        database = ""
        if config.file_endpoint and config.file_endpoint.path:
            database = config.file_endpoint.path.lstrip("/")

        # Get token from extra_options (URL) or options (UI)
        token = config.extra_options.get("motherduck_token", "")
        if not token:
            token = config.get_option("motherduck_token", "")

        if not database:
            raise ValueError("MotherDuck connections require a database name.")
        if not token:
            raise ValueError("MotherDuck connections require an access token.")

        conn_str = f"md:{database}?motherduck_token={token}"

        duckdb_any: Any = duckdb
        return duckdb_any.connect(conn_str)
