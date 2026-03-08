"""Provider registration."""

from collections.abc import Mapping

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerCredentials, DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.mysql.schema import SCHEMA


def _mysql_post_process(creds: DockerCredentials, env_vars: Mapping[str, str]) -> DockerCredentials:
    user = creds.user
    if not user and (env_vars.get("MYSQL_ALLOW_EMPTY_PASSWORD") or env_vars.get("MYSQL_RANDOM_ROOT_PASSWORD")):
        user = "root"
    return DockerCredentials(user=user, password=creds.password, database=creds.database)


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.mysql.adapter import MySQLAdapter

    return build_adapter_provider(spec, SCHEMA, MySQLAdapter())


SPEC = ProviderSpec(
    db_type="mysql",
    display_name="MySQL",
    schema_path=("sqlit.domains.connections.providers.mysql.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="3306",
    requires_auth=True,
    badge_label="MySQL",
    url_schemes=("mysql",),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("mysql",),
        env_vars={
            "user": ("MYSQL_USER",),
            "password": ("MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"),
            "database": ("MYSQL_DATABASE",),
        },
        default_user="root",
        default_database="",
        default_user_requires_password=True,
        preferred_host="127.0.0.1",
        post_process=_mysql_post_process,
    ),
)

register_provider(SPEC)
