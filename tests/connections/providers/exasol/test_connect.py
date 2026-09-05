"""Tests for the kwargs ExasolAdapter.connect() passes to pyexasol.

The driver is faked by seeding sys.modules, which importlib.import_module - and
so _import_driver_module - returns without touching the filesystem. That keeps
these tests passing with the exasol extra absent, which the default CI unit job
requires. _import_driver_module is deliberately NOT patched: the driver_name /
extra_name / package_name plumbing that produces sqlit's install prompt is part
of what is under test, and patching it would let a mistyped module name pass.

Every kwarg name is spelled as a literal string. MagicMock accepts any keyword,
so a pyexasol rename cannot fail these tests - it has to surface as a visible
diff in this file instead. Only the Docker integration test can validate the
driver's actual contract.
"""

from __future__ import annotations

import ssl
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sqlit.domains.connections.domain.config import ConnectionConfig, FileEndpoint, TcpEndpoint
from sqlit.domains.connections.providers.exasol.adapter import ExasolAdapter
from sqlit.domains.connections.providers.registry import get_default_port

AUTHENTICATORS = ("password", "access_token", "refresh_token")


def _config(
    *,
    host: str = "db.example.com",
    port: str = "1234",
    username: str = "sys",
    password: str | None = "exasol",
    options: dict[str, Any] | None = None,
    extra_options: dict[str, str] | None = None,
) -> ConnectionConfig:
    return ConnectionConfig(
        name="test_exasol",
        db_type="exasol",
        endpoint=TcpEndpoint(host=host, port=port, username=username, password=password),
        options=dict(options or {}),
        extra_options=dict(extra_options or {}),
    )


def _connect_kwargs(config: ConnectionConfig) -> dict[str, Any]:
    """Run connect() against a faked pyexasol and return the recorded kwargs."""
    fake_driver = MagicMock()
    with patch.dict("sys.modules", {"pyexasol": fake_driver}):
        ExasolAdapter().connect(config)
    return dict(fake_driver.connect.call_args.kwargs)


# --- Credentials ------------------------------------------------------------
# The unused methods' keys must be ABSENT, not empty: pyexasol's _login()
# branches on token truthiness, so a present-but-empty access_token is falsy and
# silently falls back to password login - exactly the bug an emptiness-tolerant
# assertion would let through.


@pytest.mark.parametrize("options", [{}, {"authenticator": "password"}], ids=["unset", "explicit"])
def test_password_auth_sends_endpoint_credentials(options: dict[str, Any]) -> None:
    kwargs = _connect_kwargs(_config(options=options))

    assert kwargs["user"] == "sys"
    assert kwargs["password"] == "exasol"
    assert "access_token" not in kwargs
    assert "refresh_token" not in kwargs


def test_access_token_auth_sends_only_the_access_token() -> None:
    kwargs = _connect_kwargs(_config(options={"authenticator": "access_token", "access_token": "acc-tok"}))

    assert kwargs["access_token"] == "acc-tok"
    assert "user" not in kwargs
    assert "password" not in kwargs
    assert "refresh_token" not in kwargs


def test_refresh_token_auth_sends_only_the_refresh_token() -> None:
    kwargs = _connect_kwargs(_config(options={"authenticator": "refresh_token", "refresh_token": "ref-tok"}))

    assert kwargs["refresh_token"] == "ref-tok"
    assert "user" not in kwargs
    assert "password" not in kwargs
    assert "access_token" not in kwargs


# --- Endpoint, schema, autocommit -------------------------------------------


def test_dsn_joins_host_and_port_with_a_colon() -> None:
    assert _connect_kwargs(_config())["dsn"] == "db.example.com:1234"


def test_absent_port_falls_back_to_the_registered_default() -> None:
    kwargs = _connect_kwargs(_config(port=""))

    assert get_default_port("exasol") == "8563"
    assert kwargs["dsn"] == "db.example.com:8563"


def test_schema_option_is_forwarded_verbatim() -> None:
    assert _connect_kwargs(_config(options={"schema": "TEST_SQLIT"}))["schema"] == "TEST_SQLIT"


def test_unset_schema_is_sent_as_an_empty_string() -> None:
    kwargs = _connect_kwargs(_config())

    # Present-but-empty, not omitted: pyexasol reads "" as "no initial schema".
    assert "schema" in kwargs
    assert kwargs["schema"] == ""


@pytest.mark.parametrize("authenticator", AUTHENTICATORS)
def test_autocommit_is_enabled_for_every_authenticator(authenticator: str) -> None:
    assert _connect_kwargs(_config(options={"authenticator": authenticator}))["autocommit"] is True


def test_non_tcp_config_is_rejected_before_the_driver_is_called() -> None:
    config = ConnectionConfig(name="test_exasol", db_type="exasol", endpoint=FileEndpoint(path="exasol.db"))
    fake_driver = MagicMock()

    with patch.dict("sys.modules", {"pyexasol": fake_driver}), pytest.raises(ValueError, match="TCP-style endpoint"):
        ExasolAdapter().connect(config)

    fake_driver.connect.assert_not_called()


# --- TLS mode mapping -------------------------------------------------------


def test_tls_disable_turns_encryption_off() -> None:
    kwargs = _connect_kwargs(_config(options={"tls_mode": "disable"}))

    assert kwargs["encryption"] is False
    assert "websocket_sslopt" not in kwargs


@pytest.mark.parametrize("options", [{}, {"tls_mode": "default"}], ids=["unset", "explicit"])
def test_tls_default_preserves_driver_certificate_verification(options: dict[str, Any]) -> None:
    kwargs = _connect_kwargs(_config(options=options))

    assert kwargs["encryption"] is True
    assert "websocket_sslopt" not in kwargs


def test_tls_require_encrypts_without_verifying_the_certificate() -> None:
    kwargs = _connect_kwargs(_config(options={"tls_mode": "require"}))

    assert kwargs["encryption"] is True
    assert kwargs["websocket_sslopt"] == {"cert_reqs": ssl.CERT_NONE}


@pytest.mark.parametrize("tls_mode", ["verify-ca", "verify-full"])
def test_verifying_modes_request_certificate_validation(tls_mode: str) -> None:
    kwargs = _connect_kwargs(_config(options={"tls_mode": tls_mode}))

    assert kwargs["encryption"] is True
    assert kwargs["websocket_sslopt"]["cert_reqs"] == ssl.CERT_REQUIRED


@pytest.mark.parametrize("tls_mode", ["verify-ca", "verify-full"])
def test_verifying_modes_forward_configured_certificate_files(tls_mode: str) -> None:
    kwargs = _connect_kwargs(
        _config(
            options={
                "tls_mode": tls_mode,
                "tls_ca": "/certs/ca.pem",
                "tls_cert": "/certs/client.pem",
                "tls_key": "/certs/client.key",
            }
        )
    )

    assert kwargs["websocket_sslopt"] == {
        "cert_reqs": ssl.CERT_REQUIRED,
        "check_hostname": tls_mode == "verify-full",
        "ca_certs": "/certs/ca.pem",
        "certfile": "/certs/client.pem",
        "keyfile": "/certs/client.key",
    }


@pytest.mark.parametrize(
    "certificate_options",
    [{}, {"tls_ca": "", "tls_cert": "   ", "tls_key": ""}],
    ids=["unset", "whitespace"],
)
def test_unconfigured_certificate_files_are_omitted(certificate_options: dict[str, Any]) -> None:
    kwargs = _connect_kwargs(_config(options={"tls_mode": "verify-full", **certificate_options}))

    assert kwargs["websocket_sslopt"] == {"cert_reqs": ssl.CERT_REQUIRED, "check_hostname": True}


# --- extra_options ----------------------------------------------------------


def test_extra_options_reach_the_driver_verbatim() -> None:
    kwargs = _connect_kwargs(_config(extra_options={"connection_timeout": "30"}))

    assert kwargs["connection_timeout"] == "30"


def test_extra_options_override_computed_kwargs() -> None:
    # extra_options is applied last, so it wins over the tls_mode mapping and
    # over the schema option.
    kwargs = _connect_kwargs(
        _config(
            options={"tls_mode": "disable", "schema": "FROM_OPTIONS"},
            extra_options={"encryption": "True", "schema": "FROM_EXTRA"},
        )
    )

    assert kwargs["encryption"] == "True"
    assert kwargs["schema"] == "FROM_EXTRA"
