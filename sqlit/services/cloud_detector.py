"""Cloud database auto-detection for Azure, AWS, and GCP.

This module provides functionality to detect cloud database resources
using CLI tools (az, aws, gcloud) and extract connection details.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ConnectionConfig

# Cache configuration
AZURE_CACHE_TTL_SECONDS = 300  # 5 minutes
AZURE_CACHE_FILE = Path(os.path.expanduser("~/.config/sqlit/azure_cache.json"))


class AzureStatus(Enum):
    """Status of Azure CLI availability."""

    AVAILABLE = "available"
    NOT_LOGGED_IN = "not_logged_in"
    CLI_NOT_INSTALLED = "cli_not_installed"
    ERROR = "error"


@dataclass
class AzureSubscription:
    """An Azure subscription."""

    id: str
    name: str
    is_default: bool = False


@dataclass
class AzureSqlServer:
    """A detected Azure SQL Server with connection details."""

    name: str
    fqdn: str  # Fully qualified domain name (e.g., server.database.windows.net)
    resource_group: str
    subscription_id: str
    subscription_name: str
    location: str
    admin_login: str | None = None
    databases: list[str] = field(default_factory=list)

    def get_display_name(self) -> str:
        """Get a display name for the server."""
        return f"{self.name} ({self.location})"


# --- Azure Cache Functions ---


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
            "databases": s.databases,
        }
        for s in servers
    ]

    save_azure_cache(cache)


# --- Azure CLI Functions ---


def _run_az_command(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Run an Azure CLI command and return (success, output/error).

    Args:
        args: Command arguments (without 'az' prefix).
        timeout: Command timeout in seconds.

    Returns:
        Tuple of (success, output_or_error_message).
    """
    try:
        result = subprocess.run(
            ["az"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except FileNotFoundError:
        return False, "CLI_NOT_INSTALLED"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def get_azure_status() -> AzureStatus:
    """Check if Azure CLI is available and logged in.

    Returns:
        AzureStatus indicating the current state.
    """
    success, output = _run_az_command(["account", "show"], timeout=10)
    if not success:
        if output == "CLI_NOT_INSTALLED":
            return AzureStatus.CLI_NOT_INSTALLED
        if "az login" in output.lower() or "not logged in" in output.lower():
            return AzureStatus.NOT_LOGGED_IN
        return AzureStatus.ERROR
    return AzureStatus.AVAILABLE


def get_azure_subscriptions() -> list[AzureSubscription]:
    """Get list of Azure subscriptions the user has access to.

    Returns:
        List of AzureSubscription objects.
    """
    success, output = _run_az_command(
        ["account", "list", "--query", "[].{id:id, name:name, isDefault:isDefault}", "-o", "json"]
    )
    if not success:
        return []

    try:
        data = json.loads(output)
        return [
            AzureSubscription(
                id=sub["id"],
                name=sub["name"],
                is_default=sub.get("isDefault", False),
            )
            for sub in data
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def get_azure_sql_servers(subscription_id: str | None = None) -> list[AzureSqlServer]:
    """Get list of Azure SQL servers.

    Args:
        subscription_id: Optional subscription ID to query. If None, uses current subscription.

    Returns:
        List of AzureSqlServer objects.
    """
    args = [
        "sql", "server", "list",
        "--query", "[].{name:name, fqdn:fullyQualifiedDomainName, resourceGroup:resourceGroup, location:location, adminLogin:administratorLogin}",
        "-o", "json",
    ]
    if subscription_id:
        args.extend(["--subscription", subscription_id])

    success, output = _run_az_command(args, timeout=60)
    if not success:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    # Get subscription info for display
    sub_name = ""
    if subscription_id:
        subs = get_azure_subscriptions()
        for sub in subs:
            if sub.id == subscription_id:
                sub_name = sub.name
                break
    else:
        # Get current subscription name
        success, sub_output = _run_az_command(["account", "show", "--query", "{id:id, name:name}", "-o", "json"])
        if success:
            try:
                sub_data = json.loads(sub_output)
                subscription_id = sub_data.get("id", "")
                sub_name = sub_data.get("name", "")
            except json.JSONDecodeError:
                pass

    servers = []
    for server in data:
        servers.append(
            AzureSqlServer(
                name=server.get("name", ""),
                fqdn=server.get("fqdn", ""),
                resource_group=server.get("resourceGroup", ""),
                subscription_id=subscription_id or "",
                subscription_name=sub_name,
                location=server.get("location", ""),
                admin_login=server.get("adminLogin"),
            )
        )

    return servers


def get_azure_sql_databases(server_name: str, resource_group: str, subscription_id: str | None = None) -> list[str]:
    """Get list of databases on an Azure SQL server.

    Args:
        server_name: Name of the SQL server.
        resource_group: Resource group containing the server.
        subscription_id: Optional subscription ID.

    Returns:
        List of database names.
    """
    args = [
        "sql", "db", "list",
        "--server", server_name,
        "--resource-group", resource_group,
        "--query", "[].name",
        "-o", "json",
    ]
    if subscription_id:
        args.extend(["--subscription", subscription_id])

    success, output = _run_az_command(args, timeout=60)
    if not success:
        return []

    try:
        databases = json.loads(output)
        # Filter out system databases
        return [db for db in databases if db.lower() != "master"]
    except json.JSONDecodeError:
        return []


def detect_azure_sql_resources(
    subscription_id: str | None = None,
    use_cache: bool = True,
) -> tuple[AzureStatus, list[AzureSqlServer]]:
    """Detect Azure SQL resources (without databases - use lazy loading).

    Args:
        subscription_id: Optional subscription ID to query.
        use_cache: If True, try to use cached data first.

    Returns:
        Tuple of (AzureStatus, list of AzureSqlServer).
        Note: Server.databases will be empty - use load_databases_for_server() for lazy loading.
    """
    # Try cache first
    if use_cache and subscription_id:
        cached_servers = get_cached_servers(subscription_id)
        if cached_servers is not None:
            return AzureStatus.AVAILABLE, cached_servers

    status = get_azure_status()
    if status != AzureStatus.AVAILABLE:
        return status, []

    servers = get_azure_sql_servers(subscription_id)

    # NOTE: Databases are NOT fetched here anymore - they're lazy loaded
    # when the user expands a server in the UI

    return AzureStatus.AVAILABLE, servers


def load_databases_for_server(
    server: AzureSqlServer,
    use_cache: bool = True,
) -> list[str]:
    """Lazy load databases for a specific server.

    Args:
        server: The server to load databases for.
        use_cache: If True, try to use cached data first.

    Returns:
        List of database names.
    """
    # Try cache first
    if use_cache:
        cached = get_cached_databases(server.name, server.resource_group)
        if cached is not None:
            return cached

    # Fetch from Azure
    databases = get_azure_sql_databases(
        server.name,
        server.resource_group,
        server.subscription_id,
    )

    # Cache the result
    cache_databases(server.name, server.resource_group, databases)

    return databases


def add_azure_firewall_rule(
    server_name: str,
    resource_group: str,
    ip_address: str,
    subscription_id: str | None = None,
) -> tuple[bool, str]:
    """Add a firewall rule to allow an IP address to access the Azure SQL server.

    Args:
        server_name: Name of the SQL server.
        resource_group: Resource group containing the server.
        ip_address: IP address to allow.
        subscription_id: Optional subscription ID.

    Returns:
        Tuple of (success, message).
    """
    rule_name = f"sqlit-{ip_address.replace('.', '-')}"
    args = [
        "sql", "server", "firewall-rule", "create",
        "--resource-group", resource_group,
        "--server", server_name,
        "--name", rule_name,
        "--start-ip-address", ip_address,
        "--end-ip-address", ip_address,
    ]
    if subscription_id:
        args.extend(["--subscription", subscription_id])

    success, output = _run_az_command(args, timeout=30)
    if success:
        return True, f"Firewall rule '{rule_name}' created for IP {ip_address}"
    else:
        return False, f"Failed to create firewall rule: {output}"


def parse_ip_from_firewall_error(error_message: str) -> str | None:
    """Extract IP address from Azure SQL firewall error message.

    Args:
        error_message: The error message from the connection attempt.

    Returns:
        The IP address if found, None otherwise.
    """
    import re
    # Pattern: "Client with IP address 'X.X.X.X' is not allowed"
    match = re.search(r"Client with IP address '(\d+\.\d+\.\d+\.\d+)'", error_message)
    if match:
        return match.group(1)
    return None


def is_firewall_error(error_message: str) -> bool:
    """Check if an error is an Azure SQL firewall error."""
    return "is not allowed to access the server" in error_message


def azure_server_to_connection_config(
    server: AzureSqlServer,
    database: str | None = None,
    use_sql_auth: bool = False,
) -> "ConnectionConfig":
    """Convert an AzureSqlServer to a ConnectionConfig.

    Args:
        server: The Azure SQL server.
        database: Optional specific database name.
        use_sql_auth: If True, use SQL Server auth instead of Azure AD.

    Returns:
        ConnectionConfig ready for connection.
    """
    from ..config import ConnectionConfig

    # Common Azure metadata for firewall rule creation
    azure_options = {
        "azure_server_name": server.name,
        "azure_resource_group": server.resource_group,
        "azure_subscription_id": server.subscription_id,
    }

    if use_sql_auth:
        return ConnectionConfig(
            name=f"{server.name}/{database}" if database else server.name,
            db_type="mssql",
            server=server.fqdn,
            port="1433",
            database=database or (server.databases[0] if server.databases else "master"),
            username=server.admin_login or "",  # Pre-fill admin login if available
            password=None,  # Will prompt for password
            source="azure",
            options={"auth_type": "sql", **azure_options},
        )
    else:
        return ConnectionConfig(
            name=f"{server.name}/{database}" if database else server.name,
            db_type="mssql",
            server=server.fqdn,
            port="1433",
            database=database or (server.databases[0] if server.databases else "master"),
            username="",  # Not needed for AD_DEFAULT
            password=None,  # Not needed for AD_DEFAULT
            source="azure",
            options={"auth_type": "ad_default", **azure_options},
        )
