from __future__ import annotations

from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.providers.mysql.schema import SCHEMA as MYSQL_SCHEMA
from sqlit.domains.connections.providers.supabase.schema import SCHEMA as SUPABASE_SCHEMA
from sqlit.domains.connections.providers.validation import SchemaConfigValidator


def test_schema_validator_skips_hidden_required_fields() -> None:
    config = ConnectionConfig(
        name="legacy-mysql",
        db_type="mysql",
        endpoint=TcpEndpoint(
            host="localhost",
            port="3306",
            database="",
            username="root",
            password=None,
        ),
        tunnel=None,
    )

    SchemaConfigValidator(MYSQL_SCHEMA).validate(config)


def test_schema_validator_allows_missing_required_password() -> None:
    config = ConnectionConfig(
        name="legacy-supabase",
        db_type="supabase",
        endpoint=TcpEndpoint(
            host="",
            port="",
            database="",
            username="",
            password=None,
        ),
        options={
            "supabase_region": "eu-north-1",
            "supabase_project_id": "exampleprojectid",
        },
    )

    SchemaConfigValidator(SUPABASE_SCHEMA).validate(config)
