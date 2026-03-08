"""Azure discovery models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
    state: str = "Ready"  # Server state: Ready, Creating, Disabled, etc.
    has_entra_admin: bool = False  # Whether Entra (Azure AD) admin is configured
    entra_only_auth: bool = False  # Whether only Entra auth is allowed (SQL auth disabled)
    databases: list[str] = field(default_factory=list)

    def get_display_name(self) -> str:
        """Get a display name for the server."""
        return f"{self.name} ({self.location})"


@dataclass
class AzureAccount:
    """Current Azure account info."""

    username: str  # Email or service principal name
    tenant_name: str | None = None
