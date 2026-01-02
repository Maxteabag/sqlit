"""Test helpers for building ConnectionConfig instances with legacy-style inputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig as _ConnectionConfig
from sqlit.domains.connections.domain.config import FileEndpoint, TcpEndpoint, TunnelConfig


class _ConnectionConfigFactory:
    def __call__(self, **kwargs: Any) -> _ConnectionConfig:
        name = str(kwargs.pop("name", ""))
        db_type = str(kwargs.pop("db_type", "mssql"))
        source = kwargs.pop("source", None)
        connection_url = kwargs.pop("connection_url", None)

        extra_options = dict(kwargs.pop("extra_options", {}) or {})
        options = dict(kwargs.pop("options", {}) or {})

        # Capture legacy top-level auth fields into options.
        for key in ("auth_type", "trusted_connection"):
            if key in kwargs and key not in options:
                options[key] = kwargs.pop(key)

        endpoint = kwargs.pop("endpoint", None)
        tunnel = kwargs.pop("tunnel", None)

        file_path = kwargs.pop("file_path", None)
        if file_path is None:
            file_path = options.pop("file_path", None)

        if endpoint is None:
            if file_path:
                endpoint = FileEndpoint(path=str(file_path))
            else:
                endpoint = TcpEndpoint(
                    host=str(kwargs.pop("server", "")),
                    port=str(kwargs.pop("port", "")),
                    database=str(kwargs.pop("database", "")),
                    username=str(kwargs.pop("username", "")),
                    password=kwargs.pop("password", None),
                )

        if tunnel is None:
            ssh_enabled = kwargs.pop("ssh_enabled", None)
            ssh_host = str(kwargs.pop("ssh_host", ""))
            ssh_port = str(kwargs.pop("ssh_port", "22"))
            ssh_username = str(kwargs.pop("ssh_username", ""))
            ssh_auth_type = str(kwargs.pop("ssh_auth_type", "key"))
            ssh_password = kwargs.pop("ssh_password", None)
            ssh_key_path = str(kwargs.pop("ssh_key_path", ""))

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

        # Any remaining kwargs get folded into options (legacy behavior).
        for key, value in list(kwargs.items()):
            if key not in options:
                options[key] = value

        return _ConnectionConfig(
            name=name,
            db_type=db_type,
            endpoint=endpoint,
            tunnel=tunnel,
            source=source,
            connection_url=connection_url,
            extra_options=extra_options,
            options=options,
        )

    def from_dict(self, data: Mapping[str, Any]) -> _ConnectionConfig:
        if "endpoint" in data:
            return _ConnectionConfig.from_dict(data)
        return self(**dict(data))

    def __getattr__(self, name: str) -> Any:
        return getattr(_ConnectionConfig, name)


ConnectionConfig = _ConnectionConfigFactory()
