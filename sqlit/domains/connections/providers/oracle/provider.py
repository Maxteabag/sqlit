"""Provider registration."""

from collections.abc import Mapping

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerCredentials, DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.oracle.schema import SCHEMA


def _oracle_post_process(creds: DockerCredentials, env_vars: Mapping[str, str]) -> DockerCredentials:
    user = creds.user
    password = creds.password
    database = creds.database

    app_user = env_vars.get("APP_USER")
    app_password = env_vars.get("APP_USER_PASSWORD")
    if app_user and not app_password:
        user = "SYSTEM"
        password = env_vars.get("ORACLE_PASSWORD")

    if isinstance(database, str) and "," in database:
        database = database.split(",", 1)[0]

    return DockerCredentials(user=user, password=password, database=database)


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

    return build_adapter_provider(spec, SCHEMA, OracleAdapter())


SPEC = ProviderSpec(
    db_type="oracle",
    display_name="Oracle",
    schema_path=("sqlit.domains.connections.providers.oracle.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="1521",
    requires_auth=True,
    badge_label="Oracle",
    url_schemes=("oracle",),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("gvenzl/oracle-free", "oracle/database"),
        env_vars={
            "user": ("APP_USER",),
            "password": ("APP_USER_PASSWORD", "ORACLE_PASSWORD"),
            "database": ("ORACLE_DATABASE",),
        },
        default_user="SYSTEM",
        default_database="FREEPDB1",
        post_process=_oracle_post_process,
    ),
)

register_provider(SPEC)
