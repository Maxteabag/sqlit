"""AWS cloud discovery cache."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import AWSRDSInstance, AWSRedshiftCluster, RegionResources

# Cache configuration
AWS_CACHE_TTL_SECONDS = 300  # 5 minutes
AWS_CACHE_FILE = Path(os.path.expanduser("~/.config/sqlit/aws_cache.json"))


@dataclass
class AWSCache:
    """Cached AWS discovery data."""

    timestamp: float
    regions_with_resources: list[dict] = field(default_factory=list)
    account_username: str | None = None
    account_display_name: str | None = None
    account_tenant: str | None = None


def load_aws_cache() -> AWSCache | None:
    """Load AWS cache from disk if valid."""
    if not AWS_CACHE_FILE.exists():
        return None

    try:
        data = json.loads(AWS_CACHE_FILE.read_text(encoding="utf-8"))
        cache = AWSCache(
            timestamp=data.get("timestamp", 0),
            regions_with_resources=data.get("regions_with_resources", []),
            account_username=data.get("account_username"),
            account_display_name=data.get("account_display_name"),
            account_tenant=data.get("account_tenant"),
        )

        # Check if cache is expired
        if time.time() - cache.timestamp > AWS_CACHE_TTL_SECONDS:
            return None

        return cache
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def save_aws_cache(
    regions_with_resources: list["RegionResources"],
    account_username: str | None = None,
    account_display_name: str | None = None,
    account_tenant: str | None = None,
) -> None:
    """Save AWS discovery data to cache."""
    try:
        AWS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable format
        regions_data = []
        for region in regions_with_resources:
            region_dict = {
                "region": region.region,
                "rds_instances": [
                    {
                        "identifier": i.identifier,
                        "engine": i.engine,
                        "endpoint": i.endpoint,
                        "port": i.port,
                        "status": i.status,
                        "master_username": i.master_username,
                        "db_name": i.db_name,
                        "region": i.region,
                    }
                    for i in region.rds_instances
                ],
                "redshift_clusters": [
                    {
                        "identifier": c.identifier,
                        "endpoint": c.endpoint,
                        "port": c.port,
                        "status": c.status,
                        "master_username": c.master_username,
                        "db_name": c.db_name,
                        "region": c.region,
                    }
                    for c in region.redshift_clusters
                ],
            }
            regions_data.append(region_dict)

        data = {
            "timestamp": time.time(),
            "regions_with_resources": regions_data,
            "account_username": account_username,
            "account_display_name": account_display_name,
            "account_tenant": account_tenant,
        }
        AWS_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # Best effort caching


def load_cached_data() -> tuple[list["RegionResources"], dict] | None:
    """Load cached regions with resources and account info.

    Returns a tuple of (regions, account_info) or None if no valid cache.
    """
    from .provider import AWSRDSInstance, AWSRedshiftCluster, RegionResources

    cache = load_aws_cache()
    if cache is None:
        return None

    regions = []
    for region_data in cache.regions_with_resources:
        rds_instances = [
            AWSRDSInstance(
                identifier=i["identifier"],
                engine=i["engine"],
                endpoint=i["endpoint"],
                port=i["port"],
                status=i["status"],
                master_username=i["master_username"],
                db_name=i.get("db_name"),
                region=i["region"],
            )
            for i in region_data.get("rds_instances", [])
        ]
        redshift_clusters = [
            AWSRedshiftCluster(
                identifier=c["identifier"],
                endpoint=c["endpoint"],
                port=c["port"],
                status=c["status"],
                master_username=c["master_username"],
                db_name=c["db_name"],
                region=c["region"],
            )
            for c in region_data.get("redshift_clusters", [])
        ]
        regions.append(
            RegionResources(
                region=region_data["region"],
                rds_instances=rds_instances,
                redshift_clusters=redshift_clusters,
            )
        )

    account_info = {
        "username": cache.account_username,
        "display_name": cache.account_display_name,
        "tenant": cache.account_tenant,
    }

    return regions, account_info


def load_cached_regions() -> list["RegionResources"] | None:
    """Load cached regions with resources."""
    from .provider import AWSRDSInstance, AWSRedshiftCluster, RegionResources

    cache = load_aws_cache()
    if cache is None:
        return None

    regions = []
    for region_data in cache.regions_with_resources:
        rds_instances = [
            AWSRDSInstance(
                identifier=i["identifier"],
                engine=i["engine"],
                endpoint=i["endpoint"],
                port=i["port"],
                status=i["status"],
                master_username=i["master_username"],
                db_name=i.get("db_name"),
                region=i["region"],
            )
            for i in region_data.get("rds_instances", [])
        ]
        redshift_clusters = [
            AWSRedshiftCluster(
                identifier=c["identifier"],
                endpoint=c["endpoint"],
                port=c["port"],
                status=c["status"],
                master_username=c["master_username"],
                db_name=c["db_name"],
                region=c["region"],
            )
            for c in region_data.get("redshift_clusters", [])
        ]
        regions.append(
            RegionResources(
                region=region_data["region"],
                rds_instances=rds_instances,
                redshift_clusters=redshift_clusters,
            )
        )

    return regions


def clear_aws_cache() -> None:
    """Clear the AWS cache file."""
    try:
        AWS_CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        pass
