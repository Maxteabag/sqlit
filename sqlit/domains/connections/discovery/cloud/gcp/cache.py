"""GCP cloud discovery cache."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import GCPCloudSQLInstance

# Cache configuration
GCP_CACHE_TTL_SECONDS = 300  # 5 minutes
GCP_CACHE_FILE = Path(os.path.expanduser("~/.config/sqlit/gcp_cache.json"))


@dataclass
class GCPCache:
    """Cached GCP discovery data."""

    timestamp: float
    project: str = ""
    instances: list[dict] = field(default_factory=list)
    account_username: str | None = None


def load_gcp_cache() -> GCPCache | None:
    """Load GCP cache from disk if valid."""
    if not GCP_CACHE_FILE.exists():
        return None

    try:
        data = json.loads(GCP_CACHE_FILE.read_text(encoding="utf-8"))
        cache = GCPCache(
            timestamp=data.get("timestamp", 0),
            project=data.get("project", ""),
            instances=data.get("instances", []),
            account_username=data.get("account_username"),
        )

        # Check if cache is expired
        if time.time() - cache.timestamp > GCP_CACHE_TTL_SECONDS:
            return None

        return cache
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def save_gcp_cache(
    project: str,
    instances: list[GCPCloudSQLInstance],
    account_username: str | None = None,
) -> None:
    """Save GCP discovery data to cache."""
    try:
        GCP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        instances_data = [
            {
                "name": i.name,
                "database_version": i.database_version,
                "connection_name": i.connection_name,
                "ip_address": i.ip_address,
                "state": i.state,
                "region": i.region,
                "project": i.project,
            }
            for i in instances
        ]

        data = {
            "timestamp": time.time(),
            "project": project,
            "instances": instances_data,
            "account_username": account_username,
        }
        GCP_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # Best effort caching


def load_cached_data() -> tuple[str, list[GCPCloudSQLInstance], str | None] | None:
    """Load cached project, instances, and account info.

    Returns a tuple of (project, instances, account_username) or None if no valid cache.
    """
    from .provider import GCPCloudSQLInstance

    cache = load_gcp_cache()
    if cache is None:
        return None

    instances = [
        GCPCloudSQLInstance(
            name=i["name"],
            database_version=i["database_version"],
            connection_name=i["connection_name"],
            ip_address=i.get("ip_address"),
            state=i["state"],
            region=i["region"],
            project=i["project"],
        )
        for i in cache.instances
    ]

    return cache.project, instances, cache.account_username


def load_cached_instances(project: str) -> list[GCPCloudSQLInstance] | None:
    """Load cached instances for a project."""
    from .provider import GCPCloudSQLInstance

    cache = load_gcp_cache()
    if cache is None:
        return None

    # Check if same project
    if cache.project != project:
        return None

    return [
        GCPCloudSQLInstance(
            name=i["name"],
            database_version=i["database_version"],
            connection_name=i["connection_name"],
            ip_address=i.get("ip_address"),
            state=i["state"],
            region=i["region"],
            project=i["project"],
        )
        for i in cache.instances
    ]


def clear_gcp_cache() -> None:
    """Clear the GCP cache file."""
    try:
        GCP_CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
