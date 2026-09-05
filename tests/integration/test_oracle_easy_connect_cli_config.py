"""Regression coverage for Oracle Easy Connect CLI configuration."""

from __future__ import annotations

import argparse

import pytest

from sqlit.domains.connections.cli.helpers import (
    add_schema_arguments,
    build_connection_config_from_args,
)
from sqlit.domains.connections.providers.catalog import get_provider_schema


@pytest.mark.parametrize("db_type", ["oracle", "oracle_legacy"])
def test_cli_builds_oracle_easy_connect_options_into_config(db_type: str) -> None:
    schema = get_provider_schema(db_type)
    parser = argparse.ArgumentParser()
    add_schema_arguments(parser, schema, include_name=True, name_required=True)

    args = parser.parse_args(
        [
            "--name",
            "secure-oracle",
            "--server",
            "localhost",
            "--database",
            "service-name.com",
            "--username",
            "testuser",
            "--oracle-protocol",
            "tcps",
            "--oracle-easy-connect-parameters",
            "ssl_server_dn_match=no&retry_count=3",
        ]
    )

    config = build_connection_config_from_args(schema, args, name=args.name)

    assert config.get_option("oracle_protocol") == "tcps"
    assert config.get_option("oracle_easy_connect_parameters") == ("ssl_server_dn_match=no&retry_count=3")
