"""Provider registration for Apache Arrow Flight SQL."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.flight.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.flight.adapter import FlightSQLAdapter

    return build_adapter_provider(spec, SCHEMA, FlightSQLAdapter())


SPEC = ProviderSpec(
    db_type="flight",
    display_name="Arrow Flight SQL",
    schema_path=("sqlit.domains.connections.providers.flight.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="8815",
    requires_auth=False,
    badge_label="Flight",
    url_schemes=("flight", "grpc", "grpc+tls"),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("sqlflite", "flight-sql", "flightsql"),
        env_vars={
            "user": ("SQLFLITE_USER", "FLIGHT_USER"),
            "password": ("SQLFLITE_PASSWORD", "FLIGHT_PASSWORD"),
            "database": ("SQLFLITE_DATABASE", "FLIGHT_DATABASE"),
        },
        default_user="",
        default_port=31337,
    ),
)

register_provider(SPEC)
