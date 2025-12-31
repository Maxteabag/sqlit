"""Driver dependency descriptors and import helpers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DriverDescriptor:
    driver_name: str
    import_names: tuple[str, ...]
    extra_name: str | None
    package_name: str | None


def import_driver_module(
    module_name: str,
    *,
    driver_name: str,
    extra_name: str | None,
    package_name: str | None,
    runtime: Any | None = None,
) -> Any:
    """Import a driver module, raising MissingDriverError with detail if it fails."""
    mock_driver_error = bool(getattr(getattr(runtime, "mock", None), "driver_error", False))
    if mock_driver_error and extra_name and package_name:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        raise MissingDriverError(
            driver_name,
            extra_name,
            package_name,
            module_name=module_name,
            import_error=f"No module named '{module_name}'",
        )

    if not extra_name or not package_name:
        return importlib.import_module(module_name)

    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        raise MissingDriverError(
            driver_name,
            extra_name,
            package_name,
            module_name=module_name,
            import_error=str(e),
        ) from e


def ensure_driver_available(driver: DriverDescriptor, runtime: Any | None = None) -> None:
    if not driver.import_names:
        return
    for module_name in driver.import_names:
        import_driver_module(
            module_name,
            driver_name=driver.driver_name,
            extra_name=driver.extra_name,
            package_name=driver.package_name,
            runtime=runtime,
        )


def ensure_provider_driver_available(provider: Any, runtime: Any | None = None) -> None:
    driver = getattr(provider, "driver", None)
    if driver is None:
        return

    mock_missing = getattr(getattr(runtime, "mock", None), "missing_drivers", None)
    requested = {item.strip().lower() for item in mock_missing or [] if item.strip()}
    db_type = getattr(getattr(provider, "metadata", None), "db_type", "").lower()
    if db_type and db_type in requested:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        raise MissingDriverError(
            driver.driver_name,
            driver.extra_name or "",
            driver.package_name or "",
            module_name=None,
            import_error=None,
        )

    ensure_driver_available(driver, runtime=runtime)
