"""Unit tests for Trino authentication configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sqlit.domains.connections.app.url_parser import parse_connection_url
from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.domain.passwords import needs_db_password
from sqlit.domains.connections.providers.exceptions import MissingDriverError
from sqlit.domains.connections.providers.trino.adapter import TrinoAdapter


def _config(*, password: str | None = None, options: dict[str, str] | None = None) -> ConnectionConfig:
    return ConnectionConfig(
        name="trino",
        db_type="trino",
        endpoint=TcpEndpoint(host="trino.example.com", port="8443", username="alice", password=password, database="hive"),
        options=options or {},
    )


def _connect(config: ConnectionConfig) -> tuple[MagicMock, MagicMock]:
    dbapi = MagicMock()
    auth = MagicMock()
    requests_kerberos = MagicMock()
    requests_kerberos.REQUIRED = auth.KerberosAuthentication.MUTUAL_REQUIRED
    requests_kerberos.OPTIONAL = auth.KerberosAuthentication.MUTUAL_OPTIONAL
    requests_kerberos.DISABLED = auth.KerberosAuthentication.MUTUAL_DISABLED
    with patch.dict(
        "sys.modules",
        {
            "trino.dbapi": dbapi,
            "trino.auth": auth,
            "requests_gssapi": MagicMock(),
            "requests_kerberos": requests_kerberos,
        },
    ):
        TrinoAdapter().connect(config)
    return dbapi, auth


def test_trino_none_authentication_omits_auth_argument():
    dbapi, auth = _connect(_config(password="ignored", options={"trino_auth_method": "none"}))

    assert "auth" not in dbapi.connect.call_args.kwargs
    auth.BasicAuthentication.assert_not_called()


def test_trino_existing_password_connection_uses_basic_authentication():
    dbapi, auth = _connect(_config(password="secret"))

    auth.BasicAuthentication.assert_called_once_with("alice", "secret")
    assert dbapi.connect.call_args.kwargs["auth"] is auth.BasicAuthentication.return_value


def test_trino_kerberos_authentication_passes_selected_options():
    dbapi, auth = _connect(
        _config(
            options={
                "trino_auth_method": "kerberos",
                "trino_kerberos_service_name": "trino",
                "trino_kerberos_hostname_override": "coordinator.example.com",
                "trino_kerberos_delegate": "true",
            }
        )
    )

    auth.KerberosAuthentication.assert_called_once_with(
        delegate=True,
        service_name="trino",
        hostname_override="coordinator.example.com",
    )
    assert dbapi.connect.call_args.kwargs["auth"] is auth.KerberosAuthentication.return_value


def test_trino_gssapi_defaults_to_http_service_and_endpoint_hostname():
    dbapi, auth = _connect(_config(options={"trino_auth_method": "gssapi"}))

    auth.GSSAPIAuthentication.assert_called_once_with(
        delegate=False,
        service_name="HTTP",
        hostname_override="trino.example.com",
    )
    assert dbapi.connect.call_args.kwargs["auth"] is auth.GSSAPIAuthentication.return_value


def test_trino_gssapi_preserves_remote_hostname_across_tunnel_rewrite():
    config = _config(options={"trino_auth_method": "gssapi"})
    tunneled_config = config.with_endpoint(host="127.0.0.1", port="12345")

    _, auth = _connect(tunneled_config)

    auth.GSSAPIAuthentication.assert_called_once_with(
        delegate=False,
        service_name="HTTP",
        hostname_override="trino.example.com",
    )
    assert "trino_kerberos_hostname_override" not in config.options


def test_trino_explicit_mutual_authentication_overrides_driver_default():
    _, auth = _connect(_config(options={"trino_auth_method": "kerberos", "trino_kerberos_mutual_authentication": "optional"}))

    auth.KerberosAuthentication.assert_called_once_with(
        delegate=False,
        mutual_authentication=auth.KerberosAuthentication.MUTUAL_OPTIONAL,
        service_name="HTTP",
    )


def test_trino_kerberos_missing_extra_opens_package_setup():
    dbapi = MagicMock()
    auth = MagicMock()
    with patch.dict("sys.modules", {"trino.dbapi": dbapi, "trino.auth": auth, "requests_kerberos": None}), pytest.raises(MissingDriverError) as error:
        TrinoAdapter().connect(_config(options={"trino_auth_method": "kerberos"}))

    assert error.value.extra_name == "trino-kerberos"
    assert error.value.package_name == "trino[kerberos]"


def test_trino_url_uses_kerberos_options_without_passing_them_to_driver():
    dbapi, auth = _connect(
        parse_connection_url(
            "trino://alice@trino.example.com:8443/hive?trino_auth_method=kerberos&trino_kerberos_service_name=trino&trino_kerberos_hostname_override=coordinator.example.com",
            name="Trino",
        )
    )

    auth.KerberosAuthentication.assert_called_once_with(
        delegate=False,
        service_name="trino",
        hostname_override="coordinator.example.com",
    )
    assert "trino_auth_method" not in dbapi.connect.call_args.kwargs


def test_trino_kerberos_connection_does_not_prompt_for_a_password():
    assert not needs_db_password(_config(options={"trino_auth_method": "kerberos"}))


def test_trino_url_promotes_authentication_options_for_form_editing():
    config = parse_connection_url("trino://alice@trino.example.com/hive?trino_auth_method=kerberos", name="Trino")

    assert config.options["trino_auth_method"] == "kerberos"
    assert "trino_auth_method" not in config.extra_options


def test_trino_schema_exposes_kerberos_authentication_options():
    from sqlit.domains.connections.providers.trino.schema import SCHEMA

    fields = {field.name: field for field in SCHEMA.fields}

    assert [option.value for option in fields["trino_auth_method"].options] == ["none", "basic", "kerberos", "gssapi"]
    assert fields["trino_auth_method"].default == "basic"
    assert fields["trino_kerberos_mutual_authentication"].default == "driver"
    assert fields["password"].visible_when is not None
    assert fields["trino_kerberos_service_name"].visible_when is not None
    assert not fields["trino_kerberos_service_name"].advanced
    assert not fields["trino_kerberos_hostname_override"].advanced
    assert fields["trino_kerberos_delegate"].advanced
    assert fields["trino_kerberos_mutual_authentication"].advanced
