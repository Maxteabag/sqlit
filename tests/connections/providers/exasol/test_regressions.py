"""Behavioral regressions for TLS policy, auth prompts and fixture failures."""
from __future__ import annotations

import ssl
from unittest.mock import MagicMock

import pytest

from sqlit.domains.connections.cli.prompts import _needs_db_prompt
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.domain.passwords import needs_db_password
from sqlit.domains.connections.providers.exasol.adapter import ExasolAdapter


def test_default_tls_retains_driver_certificate_validation():
    kwargs = ExasolAdapter()._tls_args(ConnectionConfig(name='test', db_type='exasol'))
    assert kwargs.get('encryption', True)
    assert kwargs.get('websocket_sslopt', {}).get('cert_reqs', ssl.CERT_REQUIRED) == ssl.CERT_REQUIRED


@pytest.mark.parametrize(('mode', 'check_hostname'), [('verify-ca', False), ('verify-full', True)])
def test_verifying_tls_modes_have_distinct_hostname_policy(mode, check_hostname):
    cfg = ConnectionConfig(name='test', db_type='exasol', options={'tls_mode': mode})
    ssl_options = ExasolAdapter()._tls_args(cfg)['websocket_sslopt']
    assert ssl_options['cert_reqs'] == ssl.CERT_REQUIRED
    assert ssl_options.get('check_hostname', True) is check_hostname


@pytest.mark.parametrize('auth', ['access_token', 'refresh_token'])
def test_provided_openid_secret_does_not_prompt_for_a_database_password(auth):
    cfg = ConnectionConfig(name='test', db_type='exasol', options={'authenticator': auth, auth: 'SYNTHETIC_SECRET'})
    assert not needs_db_password(cfg)
    assert not _needs_db_prompt(cfg)


def test_schema_setup_failure_fails_the_fixture_instead_of_skipping(monkeypatch):
    from tests.fixtures import exasol

    conn = MagicMock()
    conn.execute.side_effect = RuntimeError('seed statement failed')
    monkeypatch.setattr(exasol, '_connect', lambda: conn)
    setup = exasol.exasol_db.__wrapped__(True)
    with pytest.raises(RuntimeError, match='seed statement failed'):
        next(setup)
    conn.close.assert_called_once()


def test_required_live_server_cannot_pass_by_skipping(monkeypatch):
    from tests.fixtures import exasol

    monkeypatch.setenv('EXASOL_REQUIRE_LIVE', '1')
    monkeypatch.setattr(exasol, 'exasol_available', lambda: False)
    with pytest.raises(pytest.fail.Exception):
        exasol.exasol_server_ready.__wrapped__()
