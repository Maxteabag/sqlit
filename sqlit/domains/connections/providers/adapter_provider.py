"""Adapter-based provider construction."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig

from sqlit.domains.connections.providers.driver import DriverDescriptor
from sqlit.domains.connections.providers.explorer_nodes import DefaultExplorerNodeProvider
from sqlit.domains.connections.providers.model import (
    ConfigValidator,
    DatabaseProvider,
    ProviderMetadata,
    ProviderSpec,
    SchemaCapabilities,
)
from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema
from sqlit.domains.connections.providers.validation import SchemaConfigValidator


@dataclass
class AdapterConfigValidator(ConfigValidator):
    schema: ConnectionSchema
    adapter: Any

    def normalize(self, config: Any) -> Any:
        config = SchemaConfigValidator(self.schema).normalize(config)
        normalize = getattr(self.adapter, "normalize_config", None)
        if callable(normalize):
            return normalize(config)
        return config

    def validate(self, config: Any) -> None:
        SchemaConfigValidator(self.schema).validate(config)
        validate = getattr(self.adapter, "validate_config", None)
        if callable(validate):
            validate(config)


def _build_metadata(spec: ProviderSpec, url_schemes: tuple[str, ...]) -> ProviderMetadata:
    badge_label = spec.badge_label or spec.display_name
    if not badge_label:
        badge_label = spec.db_type.upper()
    return ProviderMetadata(
        db_type=spec.db_type,
        display_name=spec.display_name,
        badge_label=badge_label,
        default_port=spec.default_port,
        supports_ssh=spec.supports_ssh,
        is_file_based=spec.is_file_based,
        has_advanced_auth=spec.has_advanced_auth,
        requires_auth=spec.requires_auth,
        url_schemes=url_schemes,
    )


def _default_display_info(config: ConnectionConfig) -> str:
    if config.file_endpoint:
        return config.file_endpoint.path or config.name

    endpoint = config.tcp_endpoint
    if endpoint:
        db_part = f"/{endpoint.database}" if endpoint.database else ""
        port_part = f":{endpoint.port}" if endpoint.port else ""
        info = f"{endpoint.host}{port_part}{db_part}".strip()
        if info:
            return info

    return config.name


def build_adapter_provider(spec: ProviderSpec, schema: ConnectionSchema, adapter: Any) -> DatabaseProvider:
    url_schemes = spec.url_schemes

    driver = DriverDescriptor(
        driver_name=getattr(adapter, "name", spec.display_name),
        import_names=tuple(getattr(adapter, "driver_import_names", ())),
        extra_name=getattr(adapter, "install_extra", None),
        package_name=getattr(adapter, "install_package", None),
    )

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

    def display_info(config: ConnectionConfig) -> str:
        if spec.display_info:
            return spec.display_info(config)
        return _default_display_info(config)

    def apply_database_override(config: Any, database: str | None) -> Any:
        override = getattr(adapter, "apply_database_override", None)
        if callable(override) and database:
            return override(config, database)
        return config

    def post_connect(conn: Any, config: Any) -> None:
        hook = getattr(adapter, "detect_capabilities", None)
        if callable(hook):
            hook(conn, config)

    def post_connect_warnings(config: Any) -> list[str]:
        getter = getattr(adapter, "get_post_connect_warnings", None)
        if callable(getter):
            return list(cast(Iterable[str], getter(config)))
        return []

    def get_auth_type(config: Any) -> Any | None:
        getter = getattr(adapter, "get_auth_type", None)
        if callable(getter):
            return getter(config)
        return None

    return DatabaseProvider(
        metadata=_build_metadata(spec, url_schemes),
        schema=schema,
        capabilities=capabilities,
        driver=driver,
        connection_factory=adapter,
        query_executor=adapter,
        schema_inspector=adapter,
        dialect=adapter,
        config_validator=AdapterConfigValidator(schema=schema, adapter=adapter),
        docker_detector=spec.docker_detector,
        explorer_nodes=DefaultExplorerNodeProvider(),
        display_info=display_info,
        apply_database_override=apply_database_override,
        post_connect=post_connect,
        post_connect_warnings=post_connect_warnings,
        get_auth_type=get_auth_type,
    )
