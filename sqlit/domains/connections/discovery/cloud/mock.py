"""Mock cloud provider data for demos and screenshots."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import AccountInfo, ProviderState, ProviderStatus

if TYPE_CHECKING:
    pass


def is_mock_cloud_enabled() -> bool:
    """Check if mock cloud mode is enabled."""
    return os.environ.get("SQLIT_MOCK_CLOUD") == "1"


def get_mock_azure_state() -> ProviderState:
    """Get mock Azure provider state with sample data."""
    from .azure.models import AzureSqlServer, AzureSubscription

    # Mock account
    account = AccountInfo(
        username="demo@contoso.com",
        display_name="Demo User",
        tenant="Contoso Corp",
    )

    # Mock subscriptions
    subscriptions = [
        AzureSubscription(
            id="sub-prod-001",
            name="Production",
            is_default=True,
        ),
        AzureSubscription(
            id="sub-dev-002",
            name="Development",
            is_default=False,
        ),
        AzureSubscription(
            id="sub-staging-003",
            name="Staging",
            is_default=False,
        ),
    ]

    # Mock servers for the active subscription (Production)
    servers = [
        AzureSqlServer(
            name="prod-sql-main",
            fqdn="prod-sql-main.database.windows.net",
            resource_group="rg-production",
            subscription_id="sub-prod-001",
            subscription_name="Production",
            location="eastus",
            admin_login="sqladmin",
            state="Ready",
            has_entra_admin=True,
            entra_only_auth=False,
            databases=["customers", "orders", "inventory"],
        ),
        AzureSqlServer(
            name="prod-sql-analytics",
            fqdn="prod-sql-analytics.database.windows.net",
            resource_group="rg-production",
            subscription_id="sub-prod-001",
            subscription_name="Production",
            location="westus2",
            admin_login="sqladmin",
            state="Ready",
            has_entra_admin=True,
            entra_only_auth=True,
            databases=["analytics", "reporting"],
        ),
        AzureSqlServer(
            name="prod-sql-backup",
            fqdn="prod-sql-backup.database.windows.net",
            resource_group="rg-production",
            subscription_id="sub-prod-001",
            subscription_name="Production",
            location="eastus2",
            admin_login="sqladmin",
            state="Paused",
            has_entra_admin=False,
            entra_only_auth=False,
            databases=["backup_db"],
        ),
    ]

    return ProviderState(
        status=ProviderStatus.AVAILABLE,
        account=account,
        loading=False,
        extra={
            "subscriptions": subscriptions,
            "servers": servers,
            "current_subscription_index": 0,
        },
    )


def get_mock_aws_state() -> ProviderState:
    """Get mock AWS provider state with sample data."""
    from .aws.provider import AWSRDSInstance, AWSRedshiftCluster, RegionResources

    # Mock account
    account = AccountInfo(
        username="arn:aws:iam::123456789012:user/demo-user",
        display_name="demo-user",
        tenant="123456789012",
    )

    # Mock regions with resources
    regions_with_resources = [
        RegionResources(
            region="us-east-1",
            rds_instances=[
                AWSRDSInstance(
                    identifier="prod-mysql-main",
                    engine="mysql",
                    endpoint="prod-mysql-main.abc123.us-east-1.rds.amazonaws.com",
                    port=3306,
                    status="available",
                    master_username="admin",
                    db_name="production",
                    region="us-east-1",
                ),
                AWSRDSInstance(
                    identifier="prod-postgres-api",
                    engine="postgres",
                    endpoint="prod-postgres-api.abc123.us-east-1.rds.amazonaws.com",
                    port=5432,
                    status="available",
                    master_username="postgres",
                    db_name="apidb",
                    region="us-east-1",
                ),
            ],
            redshift_clusters=[
                AWSRedshiftCluster(
                    identifier="analytics-warehouse",
                    endpoint="analytics-warehouse.abc123.us-east-1.redshift.amazonaws.com",
                    port=5439,
                    status="available",
                    master_username="admin",
                    db_name="analytics",
                    region="us-east-1",
                ),
            ],
        ),
        RegionResources(
            region="eu-west-1",
            rds_instances=[
                AWSRDSInstance(
                    identifier="eu-postgres-replica",
                    engine="postgres",
                    endpoint="eu-postgres-replica.xyz789.eu-west-1.rds.amazonaws.com",
                    port=5432,
                    status="available",
                    master_username="postgres",
                    db_name="replica",
                    region="eu-west-1",
                ),
            ],
            redshift_clusters=[],
        ),
        RegionResources(
            region="ap-southeast-1",
            rds_instances=[
                AWSRDSInstance(
                    identifier="apac-mysql-prod",
                    engine="mysql",
                    endpoint="apac-mysql-prod.def456.ap-southeast-1.rds.amazonaws.com",
                    port=3306,
                    status="available",
                    master_username="admin",
                    db_name="apac_prod",
                    region="ap-southeast-1",
                ),
            ],
            redshift_clusters=[],
        ),
    ]

    return ProviderState(
        status=ProviderStatus.AVAILABLE,
        account=account,
        loading=False,
        extra={
            "regions_with_resources": regions_with_resources,
        },
    )


def get_mock_gcp_state() -> ProviderState:
    """Get mock GCP provider state with sample data."""
    from .gcp.provider import GCPCloudSQLInstance

    # Mock account
    account = AccountInfo(
        username="demo@example-project.iam.gserviceaccount.com",
        display_name="demo@example-project.iam.gserviceaccount.com",
        tenant="example-project-12345",
    )

    # Mock Cloud SQL instances
    instances = [
        GCPCloudSQLInstance(
            name="prod-postgres-main",
            database_version="POSTGRES_15",
            connection_name="example-project-12345:us-central1:prod-postgres-main",
            ip_address="35.192.0.1",
            state="RUNNABLE",
            region="us-central1",
            project="example-project-12345",
        ),
        GCPCloudSQLInstance(
            name="prod-mysql-api",
            database_version="MYSQL_8_0",
            connection_name="example-project-12345:us-central1:prod-mysql-api",
            ip_address="35.192.0.2",
            state="RUNNABLE",
            region="us-central1",
            project="example-project-12345",
        ),
        GCPCloudSQLInstance(
            name="dev-postgres",
            database_version="POSTGRES_14",
            connection_name="example-project-12345:us-east1:dev-postgres",
            ip_address="35.193.0.1",
            state="RUNNABLE",
            region="us-east1",
            project="example-project-12345",
        ),
        GCPCloudSQLInstance(
            name="staging-mssql",
            database_version="SQLSERVER_2019_STANDARD",
            connection_name="example-project-12345:europe-west1:staging-mssql",
            ip_address="35.194.0.1",
            state="STOPPED",
            region="europe-west1",
            project="example-project-12345",
        ),
    ]

    return ProviderState(
        status=ProviderStatus.AVAILABLE,
        account=account,
        loading=False,
        extra={
            "instances": instances,
            "project": "example-project-12345",
        },
    )


def get_mock_cloud_states() -> dict[str, ProviderState]:
    """Get mock states for all cloud providers."""
    return {
        "azure": get_mock_azure_state(),
        "aws": get_mock_aws_state(),
        "gcp": get_mock_gcp_state(),
    }
