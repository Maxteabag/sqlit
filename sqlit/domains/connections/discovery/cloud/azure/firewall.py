"""Azure SQL firewall helpers."""

from __future__ import annotations

import json
import re

from .cli import _run_az_command
from .models import AzureSqlServer


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
    # Pattern: "Client with IP address 'X.X.X.X' is not allowed"
    match = re.search(r"Client with IP address '(\d+\.\d+\.\d+\.\d+)'", error_message)
    if match:
        return match.group(1)
    return None


def is_firewall_error(error_message: str) -> bool:
    """Check if an error is an Azure SQL firewall error (error code 40615)."""
    return "sp_set_firewall_rule" in error_message


def parse_server_name_from_hostname(hostname: str) -> str | None:
    """Extract server name from Azure SQL hostname.

    Args:
        hostname: The server hostname (e.g., 'myserver.database.windows.net').

    Returns:
        The server name if it's an Azure SQL hostname, None otherwise.
    """
    if not hostname:
        return None
    hostname_lower = hostname.lower()
    if hostname_lower.endswith(".database.windows.net"):
        return hostname_lower.replace(".database.windows.net", "")
    return None


def lookup_azure_sql_server(server_name: str) -> AzureSqlServer | None:
    """Look up an Azure SQL server by name to get resource group and subscription.

    Args:
        server_name: The server name (not FQDN).

    Returns:
        AzureSqlServer if found, None otherwise.
    """
    # Use az sql server list with a filter to find the server
    args = [
        "sql", "server", "list",
        "--query", f"[?name=='{server_name}']",
        "-o", "json",
    ]
    success, output = _run_az_command(args, timeout=30)
    if not success:
        return None

    try:
        servers = json.loads(output)
        if servers and len(servers) > 0:
            server = servers[0]
            return AzureSqlServer(
                name=server.get("name", ""),
                fqdn=server.get("fullyQualifiedDomainName", ""),
                resource_group=server.get("resourceGroup", ""),
                subscription_id=server.get("subscriptionId", ""),
                subscription_name="",
                location=server.get("location", ""),
                state=server.get("state", "Ready"),
            )
    except (json.JSONDecodeError, KeyError):
        pass

    return None
