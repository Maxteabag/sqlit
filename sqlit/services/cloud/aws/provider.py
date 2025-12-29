"""AWS cloud provider implementation."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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


@dataclass
class AWSRDSInstance:
    """Represents an AWS RDS database instance."""

    identifier: str
    engine: str  # mysql, postgres, mariadb, oracle-ee, sqlserver-ex, etc.
    endpoint: str
    port: int
    status: str
    master_username: str
    db_name: str | None  # Initial database name
    region: str


@dataclass
class AWSRedshiftCluster:
    """Represents an AWS Redshift cluster."""

    identifier: str
    endpoint: str
    port: int
    status: str
    master_username: str
    db_name: str
    region: str


@dataclass
class RegionResources:
    """Resources discovered in a specific region."""

    region: str
    rds_instances: list[AWSRDSInstance] = field(default_factory=list)
    redshift_clusters: list[AWSRedshiftCluster] = field(default_factory=list)

    @property
    def has_resources(self) -> bool:
        return bool(self.rds_instances or self.redshift_clusters)


class AWSProvider:
    """AWS cloud provider for RDS/Redshift database discovery."""

    # Option ID prefixes
    ACCOUNT_ID = "_aws_account"
    LOGIN_ID = "_aws_login"
    RDS_PREFIX = "aws:rds:"
    REDSHIFT_PREFIX = "aws:redshift:"
    REGION_PREFIX = "_aws_region_"

    # Map RDS engine to our db_type
    ENGINE_MAP = {
        "mysql": "mysql",
        "postgres": "postgresql",
        "mariadb": "mariadb",
        "oracle-ee": "oracle",
        "oracle-se2": "oracle",
        "oracle-se1": "oracle",
        "oracle-se": "oracle",
        "sqlserver-ee": "mssql",
        "sqlserver-se": "mssql",
        "sqlserver-ex": "mssql",
        "sqlserver-web": "mssql",
        "aurora-mysql": "mysql",
        "aurora-postgresql": "postgresql",
    }

    # Common AWS regions to scan (covers most use cases)
    # Full list would be 20+ regions but this covers the major ones
    ALL_REGIONS = [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-central-1",
        "eu-north-1",
        "ap-northeast-1",
        "ap-northeast-2",
        "ap-northeast-3",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-south-1",
        "sa-east-1",
        "ca-central-1",
        "me-south-1",
        "af-south-1",
    ]

    @property
    def name(self) -> str:
        return "AWS"

    @property
    def id(self) -> str:
        return "aws"

    @property
    def prefix(self) -> str:
        return "aws:"

    def get_status(self) -> ProviderStatus:
        """Check if AWS CLI is available and logged in."""
        try:
            result = subprocess.run(
                ["aws", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                return ProviderStatus.CLI_NOT_INSTALLED
        except FileNotFoundError:
            return ProviderStatus.CLI_NOT_INSTALLED
        except Exception:
            return ProviderStatus.ERROR

        # Check if logged in
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return ProviderStatus.AVAILABLE
            return ProviderStatus.NOT_LOGGED_IN
        except Exception:
            return ProviderStatus.ERROR

    def get_account(self) -> AccountInfo | None:
        """Get the currently logged-in AWS account info."""
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--output", "json"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return None

            data = json.loads(result.stdout.decode())
            arn = data.get("Arn", "")
            account_id = data.get("Account", "")

            # Extract username from ARN
            # ARN format: arn:aws:iam::123456789012:user/username
            # or: arn:aws:sts::123456789012:assumed-role/role-name/session
            username = arn.split("/")[-1] if "/" in arn else arn.split(":")[-1]

            return AccountInfo(
                username=username,
                display_name=f"Account {account_id}",
                tenant=account_id,
            )
        except Exception:
            return None

    def login(self) -> bool:
        """Initiate AWS CLI login (SSO). Returns True on success."""
        try:
            result = subprocess.run(
                ["aws", "sso", "login"],
                capture_output=True,
                timeout=300,
            )
            return result.returncode == 0
        except Exception:
            return False

    def logout(self) -> bool:
        """Log out from AWS CLI. Returns True on success."""
        from .cache import clear_aws_cache

        try:
            result = subprocess.run(
                ["aws", "sso", "logout"],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                clear_aws_cache()
                return True
            return False
        except Exception:
            return False

    def discover(self, state: ProviderState, use_cache: bool = True) -> ProviderState:
        """Discover AWS RDS and Redshift resources across all regions."""
        from .cache import load_cached_data, save_aws_cache

        # Try cache first - this is fast and avoids CLI calls
        cached = None
        if use_cache:
            cached = load_cached_data()

        if cached is not None:
            # Cache hit - use cached data without any CLI calls
            regions_with_resources, account_info = cached
            account = AccountInfo(
                username=account_info.get("username") or "",
                display_name=account_info.get("display_name"),
                tenant=account_info.get("tenant"),
            ) if account_info.get("username") else None
        else:
            # No cache - full check and discovery
            status = self.get_status()
            if status != ProviderStatus.AVAILABLE:
                return ProviderState(status=status, loading=False)

            account = self.get_account()

            # Discover fresh
            regions_with_resources = self._discover_all_regions()
            # Save to cache with account info
            save_aws_cache(
                regions_with_resources,
                account_username=account.username if account else None,
                account_display_name=account.display_name if account else None,
                account_tenant=account.tenant if account else None,
            )

        # Build flat lists for backward compatibility
        all_rds_instances: list[AWSRDSInstance] = []
        all_redshift_clusters: list[AWSRedshiftCluster] = []

        for region_resources in regions_with_resources:
            all_rds_instances.extend(region_resources.rds_instances)
            all_redshift_clusters.extend(region_resources.redshift_clusters)

        # Build resources
        resources: list[CloudResource] = []

        for instance in all_rds_instances:
            resources.append(
                CloudResource(
                    id=f"rds_{instance.region}_{instance.identifier}",
                    name=instance.identifier,
                    resource_type="rds_instance",
                    provider="aws",
                    metadata={
                        "engine": instance.engine,
                        "endpoint": instance.endpoint,
                        "port": instance.port,
                        "status": instance.status,
                        "master_username": instance.master_username,
                        "db_name": instance.db_name,
                        "region": instance.region,
                    },
                )
            )

        for cluster in all_redshift_clusters:
            resources.append(
                CloudResource(
                    id=f"redshift_{cluster.region}_{cluster.identifier}",
                    name=cluster.identifier,
                    resource_type="redshift_cluster",
                    provider="aws",
                    metadata={
                        "endpoint": cluster.endpoint,
                        "port": cluster.port,
                        "status": cluster.status,
                        "master_username": cluster.master_username,
                        "db_name": cluster.db_name,
                        "region": cluster.region,
                    },
                )
            )

        return ProviderState(
            status=ProviderStatus.AVAILABLE,
            account=account,
            loading=False,
            resources=resources,
            extra={
                "regions_with_resources": regions_with_resources,
                "rds_instances": all_rds_instances,
                "redshift_clusters": all_redshift_clusters,
            },
        )

    def _discover_all_regions(self) -> list[RegionResources]:
        """Discover resources across all regions in parallel."""
        regions_with_resources: list[RegionResources] = []

        def discover_region(region: str) -> RegionResources:
            rds = self._discover_rds_instances(region)
            redshift = self._discover_redshift_clusters(region)
            return RegionResources(
                region=region,
                rds_instances=rds,
                redshift_clusters=redshift,
            )

        # Use thread pool to discover regions in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(discover_region, region): region
                for region in self.ALL_REGIONS
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result.has_resources:
                        regions_with_resources.append(result)
                except Exception:
                    pass

        # Sort by region name for consistent display
        regions_with_resources.sort(key=lambda r: r.region)
        return regions_with_resources

    def _discover_rds_instances(self, region: str) -> list[AWSRDSInstance]:
        """Discover RDS instances in the given region."""
        instances: list[AWSRDSInstance] = []

        try:
            result = subprocess.run(
                [
                    "aws", "rds", "describe-db-instances",
                    "--region", region,
                    "--output", "json",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                return instances

            data = json.loads(result.stdout.decode())
            for db in data.get("DBInstances", []):
                endpoint = db.get("Endpoint", {})
                if not endpoint:
                    continue

                instances.append(
                    AWSRDSInstance(
                        identifier=db.get("DBInstanceIdentifier", ""),
                        engine=db.get("Engine", ""),
                        endpoint=endpoint.get("Address", ""),
                        port=endpoint.get("Port", 3306),
                        status=db.get("DBInstanceStatus", ""),
                        master_username=db.get("MasterUsername", ""),
                        db_name=db.get("DBName"),
                        region=region,
                    )
                )
        except Exception:
            pass

        return instances

    def _discover_redshift_clusters(self, region: str) -> list[AWSRedshiftCluster]:
        """Discover Redshift clusters in the given region."""
        clusters: list[AWSRedshiftCluster] = []

        try:
            result = subprocess.run(
                [
                    "aws", "redshift", "describe-clusters",
                    "--region", region,
                    "--output", "json",
                ],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                return clusters

            data = json.loads(result.stdout.decode())
            for cluster in data.get("Clusters", []):
                endpoint = cluster.get("Endpoint", {})
                if not endpoint:
                    continue

                clusters.append(
                    AWSRedshiftCluster(
                        identifier=cluster.get("ClusterIdentifier", ""),
                        endpoint=endpoint.get("Address", ""),
                        port=endpoint.get("Port", 5439),
                        status=cluster.get("ClusterStatus", ""),
                        master_username=cluster.get("MasterUsername", ""),
                        db_name=cluster.get("DBName", "dev"),
                        region=region,
                    )
                )
        except Exception:
            pass

        return clusters

    def build_options(
        self,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
        filter_pattern: str = "",
    ) -> list[Option]:
        """Build UI options for AWS resources."""
        from ....utils import fuzzy_match, highlight_matches

        options: list[Option] = []

        # AWS header
        options.append(Option("[bold]AWS[/]", id="_header_aws", disabled=True))

        # Loading state
        if state.loading:
            options.append(
                Option("[dim italic]  Loading...[/]", id="_aws_loading", disabled=True)
            )
            return options

        # Handle different statuses
        if state.status == ProviderStatus.CLI_NOT_INSTALLED:
            options.append(
                Option(
                    "  [dim](AWS CLI not installed)[/]",
                    id="_aws_cli_missing",
                    disabled=True,
                )
            )
            return options

        if state.status == ProviderStatus.NOT_LOGGED_IN:
            options.append(
                Option("  🔑 Login to AWS...", id=self.LOGIN_ID)
            )
            return options

        if state.status == ProviderStatus.ERROR:
            options.append(
                Option(
                    "  [red]⚠ AWS CLI error[/]",
                    id="_aws_error",
                    disabled=True,
                )
            )
            return options

        if state.status == ProviderStatus.NOT_SUPPORTED:
            options.append(
                Option("[dim]  (coming soon)[/]", id="_aws_coming_soon", disabled=True)
            )
            return options

        # Show account
        if state.account:
            account_display = state.account.username
            if state.account.tenant:
                account_display = f"{account_display} ({state.account.tenant})"
            if len(account_display) > 45:
                account_display = account_display[:42] + "..."
            options.append(
                Option(f"  👤 {account_display}", id=self.ACCOUNT_ID)
            )

        # Get regions with resources
        regions_with_resources: list[RegionResources] = state.extra.get(
            "regions_with_resources", []
        )

        if not regions_with_resources:
            options.append(
                Option(
                    "    [dim](no databases found in any region)[/]",
                    id="_aws_no_resources",
                    disabled=True,
                )
            )
            return options

        # Show resources grouped by region with tree lines
        for region_idx, region_resources in enumerate(regions_with_resources):
            region = region_resources.region
            is_last_region = region_idx == len(regions_with_resources) - 1
            region_branch = "└── " if is_last_region else "├── "
            region_cont = "    " if is_last_region else "│   "

            # Region header
            options.append(
                Option(
                    f"    {region_branch}[green]📍 {region}[/]",
                    id=f"{self.REGION_PREFIX}{region}",
                    disabled=True,
                )
            )

            # Build list of all resources in this region (filtered)
            region_items: list[tuple[str, str, str, str, bool]] = []  # (id, display, type_label, status, saved)

            for instance in region_resources.rds_instances:
                matches, indices = fuzzy_match(filter_pattern, instance.identifier)
                if not matches and filter_pattern:
                    continue
                display = (
                    highlight_matches(instance.identifier, indices)
                    if filter_pattern
                    else instance.identifier
                )
                engine_display = instance.engine.replace("-", " ").title()
                status_icon = "🟢" if instance.status == "available" else "🟡"
                saved = self._is_rds_saved(instance, saved_connections)
                region_items.append((
                    f"{self.RDS_PREFIX}{region}:{instance.identifier}",
                    display,
                    engine_display,
                    status_icon,
                    saved,
                ))

            for cluster in region_resources.redshift_clusters:
                matches, indices = fuzzy_match(filter_pattern, cluster.identifier)
                if not matches and filter_pattern:
                    continue
                display = (
                    highlight_matches(cluster.identifier, indices)
                    if filter_pattern
                    else cluster.identifier
                )
                status_icon = "🟢" if cluster.status == "available" else "🟡"
                saved = self._is_redshift_saved(cluster, saved_connections)
                region_items.append((
                    f"{self.REDSHIFT_PREFIX}{region}:{cluster.identifier}",
                    display,
                    "Redshift",
                    status_icon,
                    saved,
                ))

            # Render items with tree lines
            for item_idx, (item_id, display, type_label, status_icon, saved) in enumerate(region_items):
                is_last_item = item_idx == len(region_items) - 1
                item_branch = "└── " if is_last_item else "├── "

                if saved:
                    options.append(
                        Option(
                            f"    {region_cont}{item_branch}[dim]{status_icon} {display} [{type_label}] ✓[/]",
                            id=item_id,
                        )
                    )
                else:
                    options.append(
                        Option(
                            f"    {region_cont}{item_branch}{status_icon} {display} [dim][{type_label}][/]",
                            id=item_id,
                        )
                    )

        return options

    def get_shortcuts(
        self,
        option_id: str,
        state: ProviderState,
    ) -> list[tuple[str, str]]:
        """Get keyboard shortcuts for the selected option."""
        if option_id == self.ACCOUNT_ID:
            return [("Logout", "l"), ("Switch", "w")]
        return []

    def handle_action(
        self,
        action: str,
        option_id: str,
        state: ProviderState,
        saved_connections: list[ConnectionConfig],
    ) -> SelectionResult:
        """Handle an action on an AWS option."""
        # Login action
        if option_id == self.LOGIN_ID:
            return SelectionResult(action="login")

        # Account actions
        if option_id == self.ACCOUNT_ID:
            if action == "logout":
                return SelectionResult(action="logout")
            elif action == "switch":
                return SelectionResult(action="login")
            return SelectionResult(action="none")

        # RDS instance selection (format: aws:rds:region:identifier)
        if option_id.startswith(self.RDS_PREFIX):
            rest = option_id.replace(self.RDS_PREFIX, "")
            if ":" in rest:
                region, identifier = rest.split(":", 1)
            else:
                # Backward compatibility
                identifier = rest
                region = None

            rds_instances = state.extra.get("rds_instances", [])
            instance = next(
                (i for i in rds_instances
                 if i.identifier == identifier and (region is None or i.region == region)),
                None
            )

            if instance:
                config = self._rds_to_config(instance)
                if action == "save":
                    if self._is_rds_saved(instance, saved_connections):
                        return SelectionResult(action="none")
                    return SelectionResult(action="save", config=config)
                return SelectionResult(action="connect", config=config)

        # Redshift cluster selection (format: aws:redshift:region:identifier)
        if option_id.startswith(self.REDSHIFT_PREFIX):
            rest = option_id.replace(self.REDSHIFT_PREFIX, "")
            if ":" in rest:
                region, identifier = rest.split(":", 1)
            else:
                # Backward compatibility
                identifier = rest
                region = None

            clusters = state.extra.get("redshift_clusters", [])
            cluster = next(
                (c for c in clusters
                 if c.identifier == identifier and (region is None or c.region == region)),
                None
            )

            if cluster:
                config = self._redshift_to_config(cluster)
                if action == "save":
                    if self._is_redshift_saved(cluster, saved_connections):
                        return SelectionResult(action="none")
                    return SelectionResult(action="save", config=config)
                return SelectionResult(action="connect", config=config)

        return SelectionResult(action="none")

    def is_my_option(self, option_id: str) -> bool:
        """Check if an option ID belongs to this provider."""
        if option_id is None:
            return False
        option_id = str(option_id)
        return (
            option_id.startswith(self.RDS_PREFIX)
            or option_id.startswith(self.REDSHIFT_PREFIX)
            or option_id in (self.ACCOUNT_ID, self.LOGIN_ID)
            or option_id.startswith("_aws_")
        )

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
        raise NotImplementedError("Use handle_action for config creation")

    def _is_rds_saved(
        self,
        instance: AWSRDSInstance,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if an RDS instance is already saved."""
        for conn in saved_connections:
            if conn.source != "aws":
                continue
            if conn.server == instance.endpoint:
                return True
        return False

    def _is_redshift_saved(
        self,
        cluster: AWSRedshiftCluster,
        saved_connections: list[ConnectionConfig],
    ) -> bool:
        """Check if a Redshift cluster is already saved."""
        for conn in saved_connections:
            if conn.source != "aws":
                continue
            if conn.server == cluster.endpoint:
                return True
        return False


    def _rds_to_config(self, instance: AWSRDSInstance) -> ConnectionConfig:
        """Convert an RDS instance to a connection config."""
        from ....config import ConnectionConfig

        db_type = self.ENGINE_MAP.get(instance.engine, "postgresql")

        return ConnectionConfig(
            name=instance.identifier,
            db_type=db_type,
            server=instance.endpoint,
            port=str(instance.port),
            database=instance.db_name or "",
            username=instance.master_username,
            password=None,  # Will prompt for password
            source="aws",
            options={
                "aws_rds_identifier": instance.identifier,
                "aws_region": instance.region,
                "aws_engine": instance.engine,
            },
        )

    def _redshift_to_config(self, cluster: AWSRedshiftCluster) -> ConnectionConfig:
        """Convert a Redshift cluster to a connection config."""
        from ....config import ConnectionConfig

        return ConnectionConfig(
            name=cluster.identifier,
            db_type="redshift",
            server=cluster.endpoint,
            port=str(cluster.port),
            database=cluster.db_name,
            username=cluster.master_username,
            password=None,  # Will prompt for password
            source="aws",
            options={
                "aws_redshift_identifier": cluster.identifier,
                "aws_region": cluster.region,
            },
        )


# Register the provider
_provider = AWSProvider()
register_provider(_provider)
