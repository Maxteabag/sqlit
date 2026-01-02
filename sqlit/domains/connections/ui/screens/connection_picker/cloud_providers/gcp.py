"""GCP-specific UI adapter for the cloud connection picker."""

from __future__ import annotations

from typing import Any, cast

from textual.widgets.tree import TreeNode

from sqlit.domains.connections.discovery.cloud import ProviderState
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.ui.screens.connection_picker.cloud_nodes import CloudNodeData
from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.base import (
    CloudProviderUIAdapter,
)
from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.utils import (
    format_saved_label,
)


class GCPCloudUIAdapter(CloudProviderUIAdapter):
    """UI adapter for GCP cloud providers."""

    provider_id = "gcp"

    def login_option_id(self, provider: Any) -> str:
        return cast(str, provider.LOGIN_ID)

    def account_option_id(self, provider: Any) -> str:
        return cast(str, provider.ACCOUNT_ID)

    def build_resources(
        self,
        parent: TreeNode,
        provider: Any,
        state: ProviderState,
        connections: list[ConnectionConfig],
        loading_databases: set[str],
    ) -> None:
        project = state.extra.get("project")
        instances = state.extra.get("instances", [])
        if project:
            project_node = parent.add(f"Project: {project}", expand=True)
            project_node.data = CloudNodeData(provider_id=self.provider_id)
        else:
            project_node = parent

        if not instances:
            project_node.add_leaf("[dim](no Cloud SQL instances)[/]")
            return

        for instance in instances:
            engine_display = instance.database_version.replace("_", " ")
            unavailable = " [dim](Unavailable)[/]" if instance.state != "RUNNABLE" else ""
            saved = self._is_instance_saved(connections, instance)
            label = format_saved_label(
                f"{instance.name} [{engine_display}]{unavailable}",
                saved,
            )
            inst_node = project_node.add_leaf(label)
            inst_node.data = CloudNodeData(
                provider_id=self.provider_id,
                option_id=f"{provider.INSTANCE_PREFIX}{instance.name}",
            )

    def on_provider_loaded(self, screen: Any, provider: Any, state: ProviderState) -> None:
        return None

    def switch_subscription(
        self,
        screen: Any,
        provider: Any,
        subscription_index: int,
    ) -> None:
        return None

    def _is_instance_saved(
        self,
        connections: list[ConnectionConfig],
        instance: Any,
    ) -> bool:
        for conn in connections:
            if conn.source != "gcp":
                continue
            if conn.options.get("gcp_connection_name") == instance.connection_name:
                return True
            endpoint = conn.tcp_endpoint
            if instance.ip_address and endpoint and endpoint.host == instance.ip_address:
                return True
        return False
