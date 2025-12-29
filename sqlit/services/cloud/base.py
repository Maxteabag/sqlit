"""Base protocol and types for cloud providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.widgets import OptionList
    from textual.widgets.option_list import Option

    from ...config import ConnectionConfig


class ProviderStatus(Enum):
    """Status of a cloud provider's CLI/SDK availability."""

    AVAILABLE = "available"
    NOT_LOGGED_IN = "not_logged_in"
    CLI_NOT_INSTALLED = "cli_not_installed"
    ERROR = "error"
    NOT_SUPPORTED = "not_supported"  # For placeholder providers


@dataclass
class AccountInfo:
    """Information about the logged-in cloud account."""

    username: str  # Email, ARN, or service account
    display_name: str | None = None
    tenant: str | None = None  # Azure tenant, AWS account, GCP project


@dataclass
class CloudResource:
    """A discovered cloud database resource."""

    id: str  # Unique identifier for this resource
    name: str
    resource_type: str  # "server", "database", "cluster", etc.
    provider: str  # "azure", "aws", "gcp"
    parent_id: str | None = None  # For hierarchical resources
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[CloudResource] = field(default_factory=list)


@dataclass
class ProviderState:
    """State for a cloud provider in the UI."""

    status: ProviderStatus | None = None
    account: AccountInfo | None = None
    loading: bool = False
    error: str | None = None
    resources: list[CloudResource] = field(default_factory=list)
    # Provider-specific state
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionResult:
    """Result of selecting a cloud resource."""

    action: str  # "connect", "save", "expand", "login", "logout", "switch", "none"
    config: ConnectionConfig | None = None
    resource: CloudResource | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CloudProvider(Protocol):
    """Protocol for cloud database providers.

    Each cloud provider (Azure, AWS, GCP) implements this protocol
    to provide discovery, authentication, and connection capabilities.
    """

    @property
    def name(self) -> str:
        """Display name of the provider (e.g., 'Azure', 'AWS', 'GCP')."""
        ...

    @property
    def id(self) -> str:
        """Unique identifier for this provider (e.g., 'azure', 'aws', 'gcp')."""
        ...

    @property
    def prefix(self) -> str:
        """Prefix for option IDs (e.g., 'azure:', 'aws:', 'gcp:')."""
        ...

    def get_status(self) -> ProviderStatus:
        """Check if the provider's CLI/SDK is available and authenticated."""
        ...

    def get_account(self) -> AccountInfo | None:
        """Get the currently logged-in account info."""
        ...

    def login(self) -> bool:
        """Initiate login flow. Returns True on success."""
        ...

    def logout(self) -> bool:
        """Log out from the provider. Returns True on success."""
        ...

    def discover(self, state: ProviderState) -> ProviderState:
        """Discover cloud resources. Returns updated state."""
        ...

    def build_options(
        self,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
        filter_pattern: str = "",
    ) -> list[Option]:
        """Build UI options for the connection picker."""
        ...

    def get_shortcuts(
        self,
        option_id: str,
        state: ProviderState,
    ) -> list[tuple[str, str]]:
        """Get keyboard shortcuts for the selected option.

        Returns list of (label, key) tuples, e.g., [("Logout", "l"), ("Switch", "w")]
        """
        ...

    def handle_action(
        self,
        action: str,
        option_id: str,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
    ) -> SelectionResult:
        """Handle an action (select, save, etc.) on an option.

        Args:
            action: The action to perform ("select", "save", etc.)
            option_id: The ID of the selected option
            state: Current provider state
            saved_connections: List of saved connections for duplicate checking

        Returns:
            SelectionResult indicating what happened
        """
        ...

    def is_my_option(self, option_id: str) -> bool:
        """Check if an option ID belongs to this provider."""
        ...

    def is_saved(
        self,
        resource: CloudResource,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if a resource is already saved as a connection."""
        ...

    def resource_to_config(
        self,
        resource: CloudResource,
        **kwargs: Any,
    ) -> ConnectionConfig:
        """Convert a cloud resource to a connection config."""
        ...
