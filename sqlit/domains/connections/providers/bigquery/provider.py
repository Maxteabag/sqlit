"""Provider registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.bigquery.schema import SCHEMA
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerCredentials, DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec

if TYPE_CHECKING:
    from collections.abc import Mapping


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.bigquery.adapter import BigQueryAdapter

    return build_adapter_provider(spec, SCHEMA, BigQueryAdapter())


def _bigquery_docker_post_process(
    creds: DockerCredentials, env_vars: Mapping[str, str]
) -> DockerCredentials:
    """Extract project ID from emulator command args or use default."""
    # The emulator typically uses --project flag, but env vars take precedence
    # Default to 'test-project' which is common for local development
    return DockerCredentials(
        user=creds.user,
        password=creds.password,
        database=env_vars.get("BIGQUERY_DATASET", creds.database) or "test_sqlit",
    )


SPEC = ProviderSpec(
    db_type="bigquery",
    display_name="Google BigQuery",
    schema_path=("sqlit.domains.connections.providers.bigquery.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="9050",
    requires_auth=False,
    badge_label="BQ",
    url_schemes=("bigquery",),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("bigquery-emulator", "goccy/bigquery-emulator"),
        env_vars={
            "user": (),
            "password": (),
            "database": ("BIGQUERY_DATASET",),
        },
        default_user="",
        default_database="test_sqlit",
        preferred_host="test-project",  # Use as project ID, not actual host
        post_process=_bigquery_docker_post_process,
    ),
)

register_provider(SPEC)
