"""Contract test for apply_database_override on multi-db adapters.

Ensures adapters that advertise cross-database support can still set a
default/active database for unqualified queries.
"""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.catalog import get_provider, get_supported_db_types
from tests.helpers import ConnectionConfig


def _supports_database_override(db_type: str) -> bool:
    provider = get_provider(db_type)
    schema = provider.schema
    if getattr(schema, "is_file_based", False):
        return False
    if not provider.capabilities.supports_multiple_databases:
        return False
    if not provider.capabilities.supports_cross_database_queries:
        return False
    # Only include providers that expose a database field in the schema.
    if not any(field.name == "database" for field in schema.fields):
        return False
    return True


@pytest.mark.parametrize(
    "db_type",
    [db_type for db_type in get_supported_db_types() if _supports_database_override(db_type)],
)
def test_apply_database_override_sets_database(db_type: str) -> None:
    provider = get_provider(db_type)

    # Build a minimal TCP config with an empty database.
    config = ConnectionConfig(
        name=f"test-{db_type}",
        db_type=db_type,
        server="localhost",
        port=provider.metadata.default_port or "",
        database="",
        username="test-user",
        password="test-pass",
    )

    override = provider.apply_database_override(config, "test_db")
    endpoint = override.tcp_endpoint

    assert endpoint is not None, f"{db_type}: expected tcp_endpoint on override config"
    assert (
        endpoint.database == "test_db"
    ), f"{db_type}: apply_database_override did not set database on config"
