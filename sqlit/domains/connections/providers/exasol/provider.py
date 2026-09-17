"""Provider registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.exasol.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.exasol.adapter import ExasolAdapter

    return build_adapter_provider(spec, SCHEMA, ExasolAdapter())


def _display_info(config: ConnectionConfig) -> str:
    """Display host:port/SCHEMA — Exasol has no database layer, so schema is the scope."""
    endpoint = config.tcp_endpoint
    if not endpoint:
        return config.name

    port_part = f":{endpoint.port}" if endpoint.port else ""
    schema = config.get_option("schema", "")
    schema_part = f"/{schema}" if schema else ""
    info = f"{endpoint.host}{port_part}{schema_part}".strip()
    return info or config.name


SPEC = ProviderSpec(
    db_type="exasol",
    display_name="Exasol",
    schema_path=("sqlit.domains.connections.providers.exasol.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="8563",
    requires_auth=True,
    badge_label="Exasol",
    url_schemes=("exasol", "exa"),
    docker_detector=DockerDetector(
        image_patterns=("exasol/docker-db",),
        env_vars={},
        default_user="sys",
    ),
    display_info=_display_info,
    provider_factory=_provider_factory,
)

register_provider(SPEC)
