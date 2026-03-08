"""Azure cloud discovery cache."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .models import AzureSqlServer, AzureSubscription

# Cache configuration
AZURE_CACHE_TTL_SECONDS = 300  # 5 minutes
AZURE_CACHE_FILE = Path(os.path.expanduser("~/.config/sqlit/azure_cache.json"))


@dataclass
class AzureCache:
    """Cached Azure discovery data."""

    timestamp: float
    subscriptions: list[dict]
    servers_by_subscription: dict[str, list[dict]]  # subscription_id -> servers
    databases_by_server: dict[str, list[str]]  # "server_name:resource_group" -> databases


def _get_server_cache_key(server_name: str, resource_group: str) -> str:
    """Get cache key for a server's databases."""
    return f"{server_name}:{resource_group}"


def load_azure_cache() -> AzureCache | None:
    """Load Azure cache from disk if it exists and is valid.

    Returns:
        AzureCache if valid cache exists, None otherwise.
    """
    if not AZURE_CACHE_FILE.exists():
        return None

    try:
        data = json.loads(AZURE_CACHE_FILE.read_text(encoding="utf-8"))
        cache = AzureCache(
            timestamp=data.get("timestamp", 0),
            subscriptions=data.get("subscriptions", []),
            servers_by_subscription=data.get("servers_by_subscription", {}),
            databases_by_server=data.get("databases_by_server", {}),
        )

        # Check if cache is expired
        if time.time() - cache.timestamp > AZURE_CACHE_TTL_SECONDS:
            return None

        return cache
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def save_azure_cache(cache: AzureCache) -> None:
    """Save Azure cache to disk.

    Args:
        cache: The cache data to save.
    """
    try:
        AZURE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": cache.timestamp,
            "subscriptions": cache.subscriptions,
            "servers_by_subscription": cache.servers_by_subscription,
            "databases_by_server": cache.databases_by_server,
        }
        AZURE_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # Best effort caching


def clear_azure_cache() -> None:
    """Clear the Azure cache file."""
    try:
        AZURE_CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def get_cached_subscriptions() -> list[AzureSubscription] | None:
    """Get subscriptions from cache if available.

    Returns:
        List of subscriptions if cache is valid, None otherwise.
    """
    cache = load_azure_cache()
    if cache is None:
        return None

    return [
        AzureSubscription(
            id=sub["id"],
            name=sub["name"],
            is_default=sub.get("is_default", False),
        )
        for sub in cache.subscriptions
    ]


def get_cached_servers(subscription_id: str) -> list[AzureSqlServer] | None:
    """Get servers for a subscription from cache if available.

    Args:
        subscription_id: The subscription ID to get servers for.

    Returns:
        List of servers if cache is valid, None otherwise.
    """
    cache = load_azure_cache()
    if cache is None:
        return None

    servers_data = cache.servers_by_subscription.get(subscription_id)
    if servers_data is None:
        return None

    return [
        AzureSqlServer(
            name=s["name"],
            fqdn=s["fqdn"],
            resource_group=s["resource_group"],
            subscription_id=s["subscription_id"],
            subscription_name=s["subscription_name"],
            location=s["location"],
            admin_login=s.get("admin_login"),
            state=s.get("state", "Ready"),
            has_entra_admin=s.get("has_entra_admin", False),
            entra_only_auth=s.get("entra_only_auth", False),
            databases=s.get("databases", []),
        )
        for s in servers_data
    ]


def get_cached_databases(server_name: str, resource_group: str) -> list[str] | None:
    """Get databases for a server from cache if available.

    Args:
        server_name: Name of the SQL server.
        resource_group: Resource group containing the server.

    Returns:
        List of database names if cached, None otherwise.
    """
    cache = load_azure_cache()
    if cache is None:
        return None

    key = _get_server_cache_key(server_name, resource_group)
    return cache.databases_by_server.get(key)


def cache_databases(server_name: str, resource_group: str, databases: list[str]) -> None:
    """Cache databases for a server.

    Args:
        server_name: Name of the SQL server.
        resource_group: Resource group containing the server.
        databases: List of database names to cache.
    """
    cache = load_azure_cache()
    if cache is None:
        # Create minimal cache just for databases
        cache = AzureCache(
            timestamp=time.time(),
            subscriptions=[],
            servers_by_subscription={},
            databases_by_server={},
        )

    key = _get_server_cache_key(server_name, resource_group)
    cache.databases_by_server[key] = databases
    save_azure_cache(cache)


def cache_subscriptions_and_servers(
    subscriptions: list[AzureSubscription],
    servers: list[AzureSqlServer],
    subscription_id: str,
) -> None:
    """Cache subscriptions and servers.

    Args:
        subscriptions: List of subscriptions to cache.
        servers: List of servers to cache.
        subscription_id: The subscription ID these servers belong to.
    """
    cache = load_azure_cache()
    if cache is None:
        cache = AzureCache(
            timestamp=time.time(),
            subscriptions=[],
            servers_by_subscription={},
            databases_by_server={},
        )

    # Update timestamp
    cache.timestamp = time.time()

    # Cache subscriptions
    cache.subscriptions = [
        {"id": s.id, "name": s.name, "is_default": s.is_default}
        for s in subscriptions
    ]

    # Cache servers for this subscription
    cache.servers_by_subscription[subscription_id] = [
        {
            "name": s.name,
            "fqdn": s.fqdn,
            "resource_group": s.resource_group,
            "subscription_id": s.subscription_id,
            "subscription_name": s.subscription_name,
            "location": s.location,
            "admin_login": s.admin_login,
            "state": s.state,
            "has_entra_admin": s.has_entra_admin,
            "entra_only_auth": s.entra_only_auth,
            "databases": s.databases,
        }
        for s in servers
    ]

    save_azure_cache(cache)
