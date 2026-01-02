"""Provider catalog and discovery."""

from __future__ import annotations

import pkgutil
from collections.abc import Iterable
from functools import cache, lru_cache
from importlib import import_module
from typing import cast

from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema

_PROVIDERS: dict[str, ProviderSpec] = {}
_DISCOVERED = False


def register_provider(spec: ProviderSpec) -> None:
    _PROVIDERS[spec.db_type] = spec


def _discover_providers() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return

    from sqlit.shared.app.startup_profiler import span as startup_span

    if __package__ is None:
        return
    with startup_span("provider_discovery"):
        package = import_module(__package__)
        for module_info in pkgutil.iter_modules(package.__path__):
            name = module_info.name
            if not module_info.ispkg:
                continue
            if name in {"adapters", "__pycache__"}:
                continue
            with startup_span(f"provider_import:{name}"):
                import_module(f"{__package__}.{name}.provider")

    _DISCOVERED = True


def _ensure_discovered() -> None:
    _discover_providers()


def get_supported_db_types() -> list[str]:
    _ensure_discovered()
    return list(_PROVIDERS.keys())


def get_provider_spec(db_type: str) -> ProviderSpec:
    _ensure_discovered()
    spec = _PROVIDERS.get(db_type)
    if spec is None:
        raise ValueError(f"Unknown database type: {db_type}")
    return spec


def _load_schema(module_name: str, attr_name: str) -> ConnectionSchema:
    module = import_module(module_name)
    schema = getattr(module, attr_name, None)
    if schema is None:
        raise ImportError(f"Schema '{attr_name}' not found in {module_name}")
    return cast(ConnectionSchema, schema)


def get_provider_schema(db_type: str) -> ConnectionSchema:
    spec = get_provider_spec(db_type)
    return _load_schema(*spec.schema_path)


def iter_provider_schemas() -> Iterable[ConnectionSchema]:
    _ensure_discovered()
    return (get_provider_schema(spec.db_type) for spec in _PROVIDERS.values())


def get_all_schemas() -> dict[str, ConnectionSchema]:
    _ensure_discovered()
    return {k: get_provider_schema(k) for k in _PROVIDERS}


@cache
def get_provider(db_type: str) -> DatabaseProvider:
    spec = get_provider_spec(db_type)
    if not spec.provider_factory:
        raise ValueError(f"Provider '{db_type}' does not define a provider_factory")
    return spec.provider_factory(spec)


@lru_cache(maxsize=1)
def get_url_scheme_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for db_type in get_supported_db_types():
        provider = get_provider(db_type)
        for scheme in provider.metadata.url_schemes:
            mapping[scheme.lower()] = db_type
    return mapping


def get_db_type_for_scheme(scheme: str) -> str | None:
    return get_url_scheme_map().get(scheme.lower())


def get_supported_url_schemes() -> set[str]:
    return set(get_url_scheme_map().keys())
