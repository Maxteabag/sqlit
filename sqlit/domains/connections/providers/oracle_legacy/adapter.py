"""Oracle legacy adapter using oracledb with ROWNUM pagination."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


class OracleLegacyAdapter(OracleAdapter):
    """Adapter for Oracle 11g and older using thick client mode."""

    _client_initialized = False
    _client_lib_dir: str | None = None

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

    def _ensure_thick_client(self, oracledb: Any, config: ConnectionConfig) -> None:
        mode = str(config.get_option("oracle_client_mode", "thick")).lower()
        if mode == "thin":
            return
        lib_dir = config.get_option("oracle_client_lib_dir") or None
        if OracleLegacyAdapter._client_initialized:
            return
        try:
            if lib_dir:
                oracledb.init_oracle_client(lib_dir=str(lib_dir))
            else:
                oracledb.init_oracle_client()
        except Exception as exc:
            raise ValueError(
                "Oracle thick client initialization failed. Install Oracle Instant Client "
                "and optionally set the client library path."
            ) from exc
        OracleLegacyAdapter._client_initialized = True
        OracleLegacyAdapter._client_lib_dir = str(lib_dir) if lib_dir else None

    def get_post_connect_warnings(self, config: ConnectionConfig) -> list[str]:
        mode = str(config.get_option("oracle_client_mode", "thick")).lower()
        if mode == "thin":
            return [
                "Oracle 11g typically requires the Thick client. Use Thick mode if you see connection errors."
            ]
        return []

    def connect(self, config: ConnectionConfig) -> Any:
        oracledb = self._import_driver_module(
            "oracledb",
            driver_name=self.name,
            extra_name=self.install_extra,
            package_name=self.install_package,
        )
        self._ensure_thick_client(oracledb, config)
        return super().connect(config)

    def build_select_query(self, table: str, limit: int, database: str | None = None, schema: str | None = None) -> str:
        """Build SELECT query with ROWNUM for Oracle 11g. Schema parameter is ignored."""
        return f'SELECT * FROM (SELECT * FROM "{table}") WHERE ROWNUM <= {limit}'
