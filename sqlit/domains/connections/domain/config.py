"""Connection domain models and enums."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DatabaseType(str, Enum):
    ATHENA = "athena"
    BIGQUERY = "bigquery"
    CLICKHOUSE = "clickhouse"
    COCKROACHDB = "cockroachdb"
    D1 = "d1"
    DUCKDB = "duckdb"
    FIREBIRD = "firebird"
    MARIADB = "mariadb"
    MSSQL = "mssql"
    MYSQL = "mysql"
    ORACLE = "oracle"
    POSTGRESQL = "postgresql"
    REDSHIFT = "redshift"
    SNOWFLAKE = "snowflake"
    SQLITE = "sqlite"
    SUPABASE = "supabase"
    TURSO = "turso"


# Display order: sqlite first, then by popularity
DATABASE_TYPE_DISPLAY_ORDER: list[DatabaseType] = [
    DatabaseType.SQLITE,
    DatabaseType.POSTGRESQL,
    DatabaseType.MYSQL,
    DatabaseType.MSSQL,
    DatabaseType.MARIADB,
    DatabaseType.ORACLE,
    DatabaseType.SNOWFLAKE,
    DatabaseType.BIGQUERY,
    DatabaseType.DUCKDB,
    DatabaseType.REDSHIFT,
    DatabaseType.CLICKHOUSE,
    DatabaseType.COCKROACHDB,
    DatabaseType.SUPABASE,
    DatabaseType.TURSO,
    DatabaseType.D1,
    DatabaseType.ATHENA,
    DatabaseType.FIREBIRD,
]


def get_database_type_labels() -> dict[DatabaseType, str]:
    from sqlit.domains.connections.providers.metadata import get_display_name

    return {db_type: get_display_name(db_type.value) for db_type in DatabaseType}


class AuthType(Enum):
    WINDOWS = "windows"
    SQL_SERVER = "sql"
    AD_PASSWORD = "ad_password"
    AD_INTERACTIVE = "ad_interactive"
    AD_INTEGRATED = "ad_integrated"
    AD_DEFAULT = "ad_default"


AUTH_TYPE_LABELS = {
    AuthType.WINDOWS: "Windows Authentication",
    AuthType.SQL_SERVER: "SQL Server Authentication",
    AuthType.AD_PASSWORD: "Microsoft Entra Password",
    AuthType.AD_INTERACTIVE: "Microsoft Entra MFA",
    AuthType.AD_INTEGRATED: "Microsoft Entra Integrated",
    AuthType.AD_DEFAULT: "Microsoft Entra Default (CLI)",
}


@dataclass
class TcpEndpoint:
    host: str = ""
    port: str = ""
    database: str = ""
    username: str = ""
    password: str | None = None
    kind: str = "tcp"


@dataclass
class FileEndpoint:
    path: str = ""
    kind: str = "file"


@dataclass
class TunnelConfig:
    enabled: bool = False
    host: str = ""
    port: str = "22"
    username: str = ""
    auth_type: str = "key"  # key|password
    password: str | None = None
    key_path: str = ""


@dataclass
class ConnectionConfig:
    """Database connection configuration."""

    name: str
    db_type: str = "mssql"
    endpoint: TcpEndpoint | FileEndpoint = field(default_factory=TcpEndpoint)
    tunnel: TunnelConfig | None = None
    source: str | None = None
    connection_url: str | None = None
    extra_options: dict[str, str] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConnectionConfig:
        payload = dict(data)

        db_type = payload.get("db_type")
        if not isinstance(db_type, str) or not db_type:
            payload["db_type"] = "mssql"

        raw_options = payload.pop("options", None)
        options: dict[str, Any] = {}
        if isinstance(raw_options, dict):
            options.update(raw_options)

        # Capture legacy top-level auth fields into options.
        for key in ("auth_type", "trusted_connection"):
            if key in payload and key not in options:
                options[key] = payload.pop(key)

        endpoint_data = payload.pop("endpoint", None)
        endpoint: TcpEndpoint | FileEndpoint | None = None
        if isinstance(endpoint_data, dict):
            endpoint_kind = str(endpoint_data.get("kind", "tcp"))
            if endpoint_kind == "file":
                endpoint = FileEndpoint(path=str(endpoint_data.get("path", "")))
            else:
                endpoint = TcpEndpoint(
                    host=str(endpoint_data.get("host", "")),
                    port=str(endpoint_data.get("port", "")),
                    database=str(endpoint_data.get("database", "")),
                    username=str(endpoint_data.get("username", "")),
                    password=endpoint_data.get("password", None),
                )
        else:
            file_path = payload.pop("file_path", None)
            if file_path is None:
                file_path = options.pop("file_path", None)
            if file_path:
                endpoint = FileEndpoint(path=str(file_path))
            else:
                endpoint = TcpEndpoint(
                    host=str(payload.pop("server", payload.pop("host", ""))),
                    port=str(payload.pop("port", "")),
                    database=str(payload.pop("database", "")),
                    username=str(payload.pop("username", "")),
                    password=payload.pop("password", None),
                )

        tunnel = None
        tunnel_data = payload.pop("tunnel", None)
        if isinstance(tunnel_data, dict):
            enabled = bool(tunnel_data.get("enabled", False))
            if enabled:
                tunnel = TunnelConfig(
                    enabled=True,
                    host=str(tunnel_data.get("host", "")),
                    port=str(tunnel_data.get("port", "22")),
                    username=str(tunnel_data.get("username", "")),
                    auth_type=str(tunnel_data.get("auth_type", "key")),
                    password=tunnel_data.get("password", None),
                    key_path=str(tunnel_data.get("key_path", "")),
                )
        else:
            ssh_enabled = payload.pop("ssh_enabled", None)
            ssh_host = str(payload.pop("ssh_host", ""))
            ssh_port = str(payload.pop("ssh_port", "22"))
            ssh_username = str(payload.pop("ssh_username", ""))
            ssh_auth_type = str(payload.pop("ssh_auth_type", "key"))
            ssh_password = payload.pop("ssh_password", None)
            ssh_key_path = str(payload.pop("ssh_key_path", ""))

            enabled_flag = str(ssh_enabled).lower() if ssh_enabled is not None else ""
            if ssh_host or enabled_flag in {"enabled", "true", "1", "yes"}:
                tunnel = TunnelConfig(
                    enabled=True,
                    host=ssh_host,
                    port=ssh_port or "22",
                    username=ssh_username,
                    auth_type=ssh_auth_type or "key",
                    password=ssh_password,
                    key_path=ssh_key_path,
                )

        base_fields = {
            "name",
            "db_type",
            "source",
            "connection_url",
            "extra_options",
        }
        for key in list(payload.keys()):
            if key in base_fields:
                continue
            if key not in options:
                options[key] = payload.pop(key)
            else:
                payload.pop(key)

        return cls(
            name=str(payload.get("name", "")),
            db_type=str(payload.get("db_type", "mssql")),
            endpoint=endpoint,
            tunnel=tunnel,
            source=payload.get("source"),
            connection_url=payload.get("connection_url"),
            extra_options=dict(payload.get("extra_options") or {}),
            options=options,
        )

    def get_option(self, name: str, default: Any | None = None) -> Any:
        return self.options.get(name, default)

    def set_option(self, name: str, value: Any) -> None:
        self.options[name] = value

    def get_field_value(self, name: str, default: Any = "") -> Any:
        values = self.to_form_values()
        return values.get(name, default)

    def get_db_type(self) -> DatabaseType:
        try:
            return DatabaseType(self.db_type)
        except ValueError:
            return next(iter(DatabaseType))

    def to_form_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "name": self.name,
            "db_type": self.db_type,
            "source": self.source,
            "connection_url": self.connection_url,
            "extra_options": self.extra_options,
        }

        if isinstance(self.endpoint, FileEndpoint):
            values["file_path"] = self.endpoint.path
        else:
            values.update(
                {
                    "server": self.endpoint.host,
                    "port": self.endpoint.port,
                    "database": self.endpoint.database,
                    "username": self.endpoint.username,
                    "password": self.endpoint.password,
                }
            )

        if self.tunnel and self.tunnel.enabled:
            values.update(
                {
                    "ssh_enabled": "enabled",
                    "ssh_host": self.tunnel.host,
                    "ssh_port": self.tunnel.port,
                    "ssh_username": self.tunnel.username,
                    "ssh_auth_type": self.tunnel.auth_type,
                    "ssh_password": self.tunnel.password,
                    "ssh_key_path": self.tunnel.key_path,
                }
            )
        else:
            values["ssh_enabled"] = "disabled"

        values.update(self.options)
        return values

    def to_dict(self, *, include_passwords: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "db_type": self.db_type,
            "source": self.source,
            "connection_url": self.connection_url,
            "extra_options": dict(self.extra_options),
            "options": dict(self.options),
        }

        if isinstance(self.endpoint, FileEndpoint):
            data["endpoint"] = {
                "kind": "file",
                "path": self.endpoint.path,
            }
        else:
            data["endpoint"] = {
                "kind": "tcp",
                "host": self.endpoint.host,
                "port": self.endpoint.port,
                "database": self.endpoint.database,
                "username": self.endpoint.username,
                "password": self.endpoint.password if include_passwords else None,
            }

        if self.tunnel and self.tunnel.enabled:
            data["tunnel"] = {
                "enabled": True,
                "host": self.tunnel.host,
                "port": self.tunnel.port,
                "username": self.tunnel.username,
                "auth_type": self.tunnel.auth_type,
                "password": self.tunnel.password if include_passwords else None,
                "key_path": self.tunnel.key_path,
            }
        else:
            data["tunnel"] = {"enabled": False}

        return data

    def with_endpoint(self, **kwargs: Any) -> ConnectionConfig:
        from dataclasses import replace

        if not isinstance(self.endpoint, TcpEndpoint):
            return self
        endpoint = replace(self.endpoint, **kwargs)
        return replace(self, endpoint=endpoint)

    def with_tunnel(self, **kwargs: Any) -> ConnectionConfig:
        from dataclasses import replace

        if self.tunnel is None:
            return self
        tunnel = replace(self.tunnel, **kwargs)
        return replace(self, tunnel=tunnel)

    def get_source_emoji(self) -> str:
        return get_source_emoji(self.source)

    @property
    def tcp_endpoint(self) -> TcpEndpoint | None:
        if isinstance(self.endpoint, TcpEndpoint):
            return self.endpoint
        return None

    @property
    def file_endpoint(self) -> FileEndpoint | None:
        if isinstance(self.endpoint, FileEndpoint):
            return self.endpoint
        return None


SOURCE_EMOJIS: dict[str, str] = {
    "docker": "🐳 ",
    "azure": "",
}


def get_source_emoji(source: str | None) -> str:
    if source is None:
        return ""
    return SOURCE_EMOJIS.get(source, "")
