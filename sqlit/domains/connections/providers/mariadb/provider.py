"""Provider registration."""

from collections.abc import Mapping

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerCredentials, DockerDetector
from sqlit.domains.connections.providers.mariadb.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _mariadb_post_process(creds: DockerCredentials, env_vars: Mapping[str, str]) -> DockerCredentials:
    user = creds.user
    if not user and (env_vars.get("MYSQL_ALLOW_EMPTY_PASSWORD") or env_vars.get("MYSQL_RANDOM_ROOT_PASSWORD")):
        user = "root"
    return DockerCredentials(user=user, password=creds.password, database=creds.database)


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.mariadb.adapter import MariaDBAdapter

    return build_adapter_provider(spec, SCHEMA, MariaDBAdapter())


SPEC = ProviderSpec(
    db_type="mariadb",
    display_name="MariaDB",
    schema_path=("sqlit.domains.connections.providers.mariadb.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="3306",
    requires_auth=True,
    badge_label="MariaDB",
    url_schemes=("mariadb",),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("mariadb",),
        env_vars={
            "user": ("MARIADB_USER", "MYSQL_USER"),
            "password": ("MARIADB_PASSWORD", "MARIADB_ROOT_PASSWORD", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"),
            "database": ("MARIADB_DATABASE", "MYSQL_DATABASE"),
        },
        default_user="root",
        default_user_requires_password=True,
        preferred_host="127.0.0.1",
        post_process=_mariadb_post_process,
    ),
)

register_provider(SPEC)
