"""Integration tests for TLS options in CLI config building."""

from __future__ import annotations

import argparse

from sqlit.domains.connections.cli.helpers import add_schema_arguments, build_connection_config_from_args
from sqlit.domains.connections.providers.catalog import get_provider_schema


def test_cli_builds_tls_options_into_config():
    schema = get_provider_schema("postgresql")
    parser = argparse.ArgumentParser()
    add_schema_arguments(parser, schema, include_name=True, name_required=True)

    args = parser.parse_args(
        [
            "--name",
            "pg",
            "--server",
            "db.example.com",
            "--username",
            "user",
            "--tls-mode",
            "verify-ca",
            "--tls-ca",
            "/ca.pem",
            "--tls-cert",
            "/client.pem",
            "--tls-key",
            "/client.key",
        ]
    )

    config = build_connection_config_from_args(schema, args, name=args.name)

    assert config.options["tls_mode"] == "verify-ca"
    assert config.options["tls_ca"] == "/ca.pem"
    assert config.options["tls_cert"] == "/client.pem"
    assert config.options["tls_key"] == "/client.key"
