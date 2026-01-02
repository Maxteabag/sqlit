"""Azure SQL discovery helpers."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

from .cache import cache_databases, get_cached_databases, get_cached_servers
from .cli import _run_az_command, get_azure_status, get_azure_subscriptions
from .models import AzureSqlServer, AzureStatus

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


def check_entra_admin(
    server_name: str,
    resource_group: str,
    subscription_id: str | None = None,
) -> bool:
    """Check if a server has an Entra (Azure AD) admin configured.

    Args:
        server_name: Name of the SQL server.
        resource_group: Resource group containing the server.
        subscription_id: Optional subscription ID.

    Returns:
        True if Entra admin is configured, False otherwise.
    """
    args = [
        "sql", "server", "ad-admin", "list",
        "--server", server_name,
        "--resource-group", resource_group,
        "-o", "json",
    ]
    if subscription_id:
        args.extend(["--subscription", subscription_id])

    success, output = _run_az_command(args, timeout=15)
    if not success:
        return False

    try:
        data = json.loads(output)
        # If the list is non-empty, an Entra admin is configured
        return bool(data)
    except json.JSONDecodeError:
        return False


def check_entra_only_auth(
    server_name: str,
    resource_group: str,
    subscription_id: str | None = None,
) -> bool:
    """Check if a server only allows Entra authentication (SQL auth disabled).

    Args:
        server_name: Name of the SQL server.
        resource_group: Resource group containing the server.
        subscription_id: Optional subscription ID.

    Returns:
        True if only Entra auth is allowed, False if SQL auth is also allowed.
    """
    args = [
        "sql", "server", "ad-only-auth", "get",
        "--name", server_name,
        "--resource-group", resource_group,
        "-o", "json",
    ]
    if subscription_id:
        args.extend(["--subscription", subscription_id])

    success, output = _run_az_command(args, timeout=15)
    if not success:
        return False

    try:
        data = json.loads(output)
        return bool(data.get("azureAdOnlyAuthentication", False))
    except json.JSONDecodeError:
        return False


def get_azure_sql_servers(subscription_id: str | None = None) -> list[AzureSqlServer]:
    """Get list of Azure SQL servers.

    Args:
        subscription_id: Optional subscription ID to query. If None, uses current subscription.

    Returns:
        List of AzureSqlServer objects.
    """
    args = [
        "sql",
        "server",
        "list",
        "--query",
        (
            "[].{name:name, fqdn:fullyQualifiedDomainName, resourceGroup:resourceGroup, "
            "location:location, adminLogin:administratorLogin, state:state}"
        ),
        "-o",
        "json",
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
        success, sub_output = _run_az_command(
            ["account", "show", "--query", "{id:id, name:name}", "-o", "json"]
        )
        if success:
            try:
                sub_data = json.loads(sub_output)
                subscription_id = sub_data.get("id", "")
                sub_name = sub_data.get("name", "")
            except json.JSONDecodeError:
                pass

    # Build initial server list
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
                state=server.get("state", "Ready"),
            )
        )

    # Check Entra auth status for each server in parallel
    if servers:
        def check_entra_status(srv: AzureSqlServer) -> tuple[str, bool, bool]:
            """Check Entra auth status for a server."""
            has_admin = check_entra_admin(srv.name, srv.resource_group, srv.subscription_id)
            entra_only = False
            if has_admin:
                # Only check entra-only if admin is configured
                entra_only = check_entra_only_auth(srv.name, srv.resource_group, srv.subscription_id)
            return (srv.name, has_admin, entra_only)

        # Run checks in parallel
        entra_status: dict[str, tuple[bool, bool]] = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_entra_status, srv): srv for srv in servers}
            for future in as_completed(futures):
                try:
                    name, has_admin, entra_only = future.result()
                    entra_status[name] = (has_admin, entra_only)
                except Exception:
                    pass

        # Update servers with Entra status
        for srv in servers:
            if srv.name in entra_status:
                srv.has_entra_admin, srv.entra_only_auth = entra_status[srv.name]

    return servers


def get_azure_sql_databases(
    server_name: str,
    resource_group: str,
    subscription_id: str | None = None,
) -> list[str]:
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


def azure_server_to_connection_config(
    server: AzureSqlServer,
    database: str | None = None,
    use_sql_auth: bool = False,
) -> ConnectionConfig:
    """Convert an AzureSqlServer to a ConnectionConfig.

    Args:
        server: The Azure SQL server.
        database: Optional specific database name.
        use_sql_auth: If True, use SQL Server auth instead of Azure AD.

    Returns:
        ConnectionConfig ready for connection.
    """
    from sqlit.domains.connections.domain.config import ConnectionConfig

    # Common Azure metadata for firewall rule creation
    azure_options = {
        "azure_server_name": server.name,
        "azure_resource_group": server.resource_group,
        "azure_subscription_id": server.subscription_id,
    }

    config_data = {
        "name": f"{server.name}/{database}" if database else server.name,
        "db_type": "mssql",
        "endpoint": {
            "kind": "tcp",
            "host": server.fqdn,
            "port": "1433",
            "database": database or (server.databases[0] if server.databases else "master"),
            "username": server.admin_login or "" if use_sql_auth else "",
            "password": None,
        },
        "source": "azure",
        "options": {
            "auth_type": "sql" if use_sql_auth else "ad_default",
            **azure_options,
        },
    }
    return ConnectionConfig.from_dict(config_data)
