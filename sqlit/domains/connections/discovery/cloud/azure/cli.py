"""Azure CLI helpers for discovery."""

from __future__ import annotations

import json
import subprocess

from .cache import clear_azure_cache
from .models import AzureAccount, AzureStatus, AzureSubscription


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
    except Exception as exc:
        return False, str(exc)


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


def get_azure_account() -> AzureAccount | None:
    """Get the currently logged-in Azure account info.

    Returns:
        AzureAccount if logged in, None otherwise.
    """
    success, output = _run_az_command(
        ["account", "show", "--query", "{user:user.name, tenant:tenantDisplayName}", "-o", "json"],
        timeout=10,
    )
    if not success:
        return None

    try:
        data = json.loads(output)
        return AzureAccount(
            username=data.get("user", ""),
            tenant_name=data.get("tenant"),
        )
    except (json.JSONDecodeError, KeyError):
        return None


def azure_logout() -> bool:
    """Log out from Azure CLI.

    Returns:
        True if logout succeeded, False otherwise.
    """
    success, _ = _run_az_command(["logout"], timeout=10)
    if success:
        clear_azure_cache()
    return success


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
