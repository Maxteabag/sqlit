"""GCP cloud provider implementation (placeholder)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets.option_list import Option

from ..base import (
    AccountInfo,
    CloudResource,
    ProviderState,
    ProviderStatus,
    SelectionResult,
)
from ..registry import register_provider

if TYPE_CHECKING:
    from ....config import ConnectionConfig


class GCPProvider:
    """GCP cloud provider for Cloud SQL discovery (placeholder)."""

    @property
    def name(self) -> str:
        return "GCP"

    @property
    def id(self) -> str:
        return "gcp"

    @property
    def prefix(self) -> str:
        return "gcp:"

    def get_status(self) -> ProviderStatus:
        """Check if gcloud CLI is available and logged in."""
        return ProviderStatus.NOT_SUPPORTED

    def get_account(self) -> AccountInfo | None:
        """Get the currently logged-in GCP account info."""
        return None

    def login(self) -> bool:
        """Initiate gcloud CLI login."""
        return False

    def logout(self) -> bool:
        """Log out from gcloud CLI."""
        return False

    def discover(self, state: ProviderState) -> ProviderState:
        """Discover GCP Cloud SQL resources."""
        return ProviderState(
            status=ProviderStatus.NOT_SUPPORTED,
            loading=False,
        )

    def build_options(
        self,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
        filter_pattern: str = "",
    ) -> list[Option]:
        """Build UI options for GCP resources."""
        return [
            Option("[bold]GCP[/]", id="_header_gcp", disabled=True),
            Option("[dim]  (coming soon)[/]", id="_gcp_coming_soon", disabled=True),
        ]

    def get_shortcuts(
        self,
        option_id: str,
        state: ProviderState,
    ) -> list[tuple[str, str]]:
        """Get keyboard shortcuts for the selected option."""
        return []

    def handle_action(
        self,
        action: str,
        option_id: str,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
    ) -> SelectionResult:
        """Handle an action on a GCP option."""
        return SelectionResult(action="none")

    def is_my_option(self, option_id: str) -> bool:
        """Check if an option ID belongs to this provider."""
        if option_id is None:
            return False
        return str(option_id).startswith("gcp:") or str(option_id).startswith("_gcp_")

    def is_saved(
        self,
        resource: CloudResource,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if a resource is already saved."""
        return False

    def resource_to_config(
        self,
        resource: CloudResource,
        **kwargs: Any,
    ) -> ConnectionConfig:
        """Convert a cloud resource to a connection config."""
        raise NotImplementedError("GCP provider not yet implemented")


# Register the provider
_provider = GCPProvider()
register_provider(_provider)
