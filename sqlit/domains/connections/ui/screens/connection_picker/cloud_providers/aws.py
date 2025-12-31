"""AWS-specific UI adapter for the cloud connection picker."""

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


class AWSCloudUIAdapter(CloudProviderUIAdapter):
    """UI adapter for AWS cloud providers."""

    provider_id = "aws"

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
        regions_with_resources = state.extra.get("regions_with_resources", [])
        if not regions_with_resources:
            parent.add_leaf("[dim](no databases found)[/]")
            return

        for region_resources in regions_with_resources:
            region = region_resources.region
            region_node = parent.add(f"Region: {region}", expand=True)
            region_node.data = CloudNodeData(provider_id=self.provider_id)

            for instance in region_resources.rds_instances:
                engine_display = instance.engine.replace("-", " ").title()
                unavailable = " [dim](Unavailable)[/]" if instance.status != "available" else ""
                saved = self._is_rds_saved(connections, instance)
                label = format_saved_label(
                    f"{instance.identifier} [{engine_display}]{unavailable}",
                    saved,
                )
                inst_node = region_node.add_leaf(label)
                inst_node.data = CloudNodeData(
                    provider_id=self.provider_id,
                    option_id=f"{provider.RDS_PREFIX}{region}:{instance.identifier}",
                )

            for cluster in region_resources.redshift_clusters:
                unavailable = " [dim](Unavailable)[/]" if cluster.status != "available" else ""
                saved = self._is_redshift_saved(connections, cluster)
                label = format_saved_label(
                    f"{cluster.identifier} [Redshift]{unavailable}",
                    saved,
                )
                cluster_node = region_node.add_leaf(label)
                cluster_node.data = CloudNodeData(
                    provider_id=self.provider_id,
                    option_id=f"{provider.REDSHIFT_PREFIX}{region}:{cluster.identifier}",
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

    def _is_rds_saved(
        self,
        connections: list[ConnectionConfig],
        instance: Any,
    ) -> bool:
        for conn in connections:
            if conn.source != "aws":
                continue
            endpoint = conn.tcp_endpoint
            if endpoint and endpoint.host == instance.endpoint:
                return True
        return False

    def _is_redshift_saved(
        self,
        connections: list[ConnectionConfig],
        cluster: Any,
    ) -> bool:
        for conn in connections:
            if conn.source != "aws":
                continue
            endpoint = conn.tcp_endpoint
            if endpoint and endpoint.host == cluster.endpoint:
                return True
        return False
