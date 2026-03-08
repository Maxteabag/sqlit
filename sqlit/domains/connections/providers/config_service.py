"""Provider-aware config normalization and validation."""

from __future__ import annotations

from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.catalog import get_provider


def normalize_connection_config(config: ConnectionConfig) -> ConnectionConfig:
    provider = get_provider(config.db_type)
    normalized = provider.config_validator.normalize(config)
    provider.config_validator.validate(normalized)
    return normalized


def validate_database_required(config: Any, database: str | None) -> None:
    db_type = getattr(config, "db_type", config)
    try:
        provider = get_provider(str(db_type))
    except Exception:
        return
    if provider.capabilities.supports_cross_database_queries:
        return
    if database:
        return
    raise ValueError(
        f"{provider.metadata.display_name} requires a database to be specified. "
        "Each database is isolated and cross-database queries are not supported."
    )
