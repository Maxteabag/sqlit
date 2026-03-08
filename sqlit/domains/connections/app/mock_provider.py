"""Helper for building mock providers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.adapter_provider import AdapterConfigValidator
from sqlit.domains.connections.providers.catalog import get_provider, get_provider_schema, get_provider_spec
from sqlit.domains.connections.providers.explorer_nodes import DefaultExplorerNodeProvider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderMetadata, SchemaCapabilities
from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema

from .mock_adapter_core import MockDatabaseAdapter


def build_mock_provider(db_type: str, adapter: MockDatabaseAdapter) -> DatabaseProvider:
    real_provider: DatabaseProvider | None
    try:
        real_provider = get_provider(db_type)
    except Exception:
        real_provider = None

    if real_provider is not None:
        metadata = real_provider.metadata
        schema = real_provider.schema
        driver = real_provider.driver
        docker_detector = real_provider.docker_detector

        def _display_info(config: ConnectionConfig) -> str:
            return real_provider.display_info(config)

        display_info = _display_info
    else:
        spec = None
        try:
            spec = get_provider_spec(db_type)
        except Exception:
            spec = None

        display_name = adapter.name or (spec.display_name if spec else db_type.upper())
        badge_label = spec.badge_label if spec and spec.badge_label else display_name
        metadata = ProviderMetadata(
            db_type=db_type,
            display_name=display_name,
            badge_label=badge_label,
            default_port=spec.default_port if spec else "",
            supports_ssh=spec.supports_ssh if spec else True,
            is_file_based=spec.is_file_based if spec else False,
            has_advanced_auth=spec.has_advanced_auth if spec else False,
            requires_auth=spec.requires_auth if spec else True,
            url_schemes=spec.url_schemes if spec else (),
        )
        schema = get_provider_schema(db_type) if spec else ConnectionSchema(
            db_type=db_type,
            display_name=display_name,
            fields=(),
            supports_ssh=metadata.supports_ssh,
            is_file_based=metadata.is_file_based,
            has_advanced_auth=metadata.has_advanced_auth,
            default_port=metadata.default_port,
            requires_auth=metadata.requires_auth,
        )
        driver = None
        docker_detector = None

        def _display_info(config: ConnectionConfig) -> str:
            endpoint = getattr(config, "endpoint", None)
            if endpoint and getattr(endpoint, "kind", "") == "file":
                return str(getattr(endpoint, "path", "")) or config.name
            tcp_endpoint = getattr(config, "tcp_endpoint", None)
            if tcp_endpoint is None:
                tcp_endpoint = endpoint
            if tcp_endpoint and getattr(tcp_endpoint, "kind", "") != "file":
                host = str(getattr(tcp_endpoint, "host", ""))
                port = str(getattr(tcp_endpoint, "port", ""))
                database = str(getattr(tcp_endpoint, "database", ""))
                db_part = f"/{database}" if database else ""
                port_part = f":{port}" if port else ""
                info = f"{host}{port_part}{db_part}".strip()
                if info:
                    return info
            return config.name

        display_info = _display_info

    capabilities = SchemaCapabilities(
        supports_multiple_databases=bool(getattr(adapter, "supports_multiple_databases", False)),
        supports_cross_database_queries=bool(getattr(adapter, "supports_cross_database_queries", False)),
        supports_stored_procedures=bool(getattr(adapter, "supports_stored_procedures", False)),
        supports_indexes=bool(getattr(adapter, "supports_indexes", False)),
        supports_triggers=bool(getattr(adapter, "supports_triggers", False)),
        supports_sequences=bool(getattr(adapter, "supports_sequences", False)),
        default_schema=str(getattr(adapter, "default_schema", "")),
        system_databases=frozenset(getattr(adapter, "system_databases", frozenset())),
    )

    def apply_database_override(config: ConnectionConfig, database: str | None) -> ConnectionConfig:
        override = getattr(adapter, "apply_database_override", None)
        if callable(override) and database:
            return cast(ConnectionConfig, override(config, database))
        return config

    def post_connect(conn: Any, config: ConnectionConfig) -> None:
        hook = getattr(adapter, "detect_capabilities", None)
        if callable(hook):
            hook(conn, config)

    def post_connect_warnings(config: ConnectionConfig) -> list[str]:
        getter = getattr(adapter, "get_post_connect_warnings", None)
        if callable(getter):
            return list(cast(Iterable[str], getter(config)))
        return []

    def get_auth_type(config: ConnectionConfig) -> Any | None:
        getter = getattr(adapter, "get_auth_type", None)
        if callable(getter):
            return getter(config)
        return None

    return DatabaseProvider(
        metadata=metadata,
        schema=schema,
        capabilities=capabilities,
        driver=driver,
        connection_factory=adapter,
        query_executor=adapter,
        schema_inspector=adapter,
        dialect=adapter,
        config_validator=AdapterConfigValidator(schema=schema, adapter=adapter),
        docker_detector=docker_detector,
        explorer_nodes=DefaultExplorerNodeProvider(),
        display_info=display_info,
        apply_database_override=apply_database_override,
        post_connect=post_connect,
        post_connect_warnings=post_connect_warnings,
        get_auth_type=get_auth_type,
    )
