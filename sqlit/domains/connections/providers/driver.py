"""Driver dependency descriptors and import helpers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class DriverDescriptor:
    driver_name: str
    import_names: tuple[str, ...]
    extra_name: str | None
    package_name: str | None


@runtime_checkable
class DriverResolver(Protocol):
    def import_module(self, module_name: str) -> Any: ...
    def should_skip(self, provider: Any) -> bool: ...
    def is_missing(self, provider: Any) -> bool: ...


@dataclass
class DefaultDriverResolver:
    def import_module(self, module_name: str) -> Any:
        return importlib.import_module(module_name)

    def should_skip(self, provider: Any) -> bool:
        return False

    def is_missing(self, provider: Any) -> bool:
        return False


@dataclass
class ConfigurableDriverResolver:
    missing_db_types: set[str] = field(default_factory=set)
    force_import_error: bool = False
    skip_checks: bool = False

    def __post_init__(self) -> None:
        self._missing_db_types = {item.strip().lower() for item in self.missing_db_types if item and item.strip()}

    def import_module(self, module_name: str) -> Any:
        if self.force_import_error:
            raise ImportError(f"No module named '{module_name}'")
        return importlib.import_module(module_name)

    def should_skip(self, provider: Any) -> bool:
        return self.skip_checks

    def is_missing(self, provider: Any) -> bool:
        db_type = getattr(getattr(provider, "metadata", None), "db_type", "")
        db_type = db_type.lower() if db_type else ""
        return db_type in self._missing_db_types


def attach_driver_resolver(provider: Any, resolver: DriverResolver) -> None:
    adapter = getattr(provider, "connection_factory", None)
    if adapter is None:
        return
    setter = getattr(adapter, "set_driver_resolver", None)
    if callable(setter):
        setter(resolver)
    else:
        adapter._driver_resolver = resolver


def import_driver_module(
    module_name: str,
    *,
    driver_name: str,
    extra_name: str | None,
    package_name: str | None,
    resolver: DriverResolver | None = None,
) -> Any:
    """Import a driver module, raising MissingDriverError with detail if it fails."""
    loader = resolver.import_module if resolver else importlib.import_module

    if not extra_name or not package_name:
        return loader(module_name)

    try:
        return loader(module_name)
    except ImportError as e:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        raise MissingDriverError(
            driver_name,
            extra_name,
            package_name,
            module_name=module_name,
            import_error=str(e),
        ) from e


def ensure_driver_available(driver: DriverDescriptor, resolver: DriverResolver | None = None) -> None:
    if not driver.import_names:
        return
    for module_name in driver.import_names:
        import_driver_module(
            module_name,
            driver_name=driver.driver_name,
            extra_name=driver.extra_name,
            package_name=driver.package_name,
            resolver=resolver,
        )


def ensure_provider_driver_available(provider: Any, resolver: DriverResolver | None = None) -> None:
    driver = getattr(provider, "driver", None)
    if driver is None:
        return

    resolver = resolver or DefaultDriverResolver()
    attach_driver_resolver(provider, resolver)
    if resolver.should_skip(provider):
        return

    if resolver.is_missing(provider):
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        raise MissingDriverError(
            driver.driver_name,
            driver.extra_name or "",
            driver.package_name or "",
            module_name=None,
            import_error=None,
        )

    ensure_driver_available(driver, resolver=resolver)
