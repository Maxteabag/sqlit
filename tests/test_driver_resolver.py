"""Tests for driver resolver dependency injection."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.driver import ConfigurableDriverResolver, DriverDescriptor, ensure_provider_driver_available
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.providers.model import ProviderMetadata


class _StubProvider:
    def __init__(self, db_type: str) -> None:
        self.metadata = ProviderMetadata(
            db_type=db_type,
            display_name="Stub",
            badge_label="STUB",
            default_port="",
            supports_ssh=False,
            is_file_based=False,
            has_advanced_auth=False,
            requires_auth=False,
            url_schemes=(),
        )
        self.driver = DriverDescriptor(
            driver_name="StubDriver",
            import_names=(),
            extra_name="stub",
            package_name="stub-driver",
        )


def test_driver_resolver_marks_missing_driver() -> None:
    resolver = ConfigurableDriverResolver(missing_db_types={"postgresql"})
    provider = _StubProvider("postgresql")

    with pytest.raises(MissingDriverError):
        ensure_provider_driver_available(provider, resolver=resolver)


def test_driver_resolver_allows_unlisted_driver() -> None:
    resolver = ConfigurableDriverResolver(missing_db_types={"postgresql"})
    provider = _StubProvider("sqlite")

    ensure_provider_driver_available(provider, resolver=resolver)
