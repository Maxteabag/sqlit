"""Provider credentials must use the same protected slot as database passwords."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from sqlit.domains.connections.app.credentials import PlaintextCredentialsService
from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.providers.registry import get_supported_db_types
from sqlit.domains.connections.store.connections import ConnectionStore

CASES = [
    ('databricks', 'auth_type', 'pat', 'access_token'),
    ('databricks', 'auth_type', 'oauth-m2m', 'client_secret'),
    ('exasol', 'authenticator', 'access_token', 'access_token'),
    ('exasol', 'authenticator', 'refresh_token', 'refresh_token'),
]


def config_for(provider, selector, mode, field):
    return ConnectionConfig(
        name='protected', db_type=provider, endpoint=TcpEndpoint(host='example.invalid'),
        options={selector: mode, field: 'SYNTHETIC_SECRET',
                 'http_path': '/sql/1.0/warehouses/example', 'client_id': 'example-client'},
        connection_url=f'{provider}://user:SYNTHETIC_URL_SECRET@example.invalid?{field}=SYNTHETIC_SECRET',
    )


@pytest.mark.parametrize(('provider', 'selector', 'mode', 'field'), CASES)
def test_secret_uses_protected_slot_and_redacts_serialization(provider, selector, mode, field):
    config = config_for(provider, selector, mode, field)
    assert config.tcp_endpoint.password == 'SYNTHETIC_SECRET'
    assert field not in config.options
    assert config.get_option(field) == 'SYNTHETIC_SECRET'
    assert config.to_form_values()[field] == 'SYNTHETIC_SECRET'
    public = json.dumps(config.to_dict(include_passwords=False))
    assert 'SYNTHETIC_SECRET' not in public
    assert 'SYNTHETIC_URL_SECRET' not in public
    transported = ConnectionConfig.from_dict(config.to_dict())
    assert transported.get_option(field) == 'SYNTHETIC_SECRET'


@pytest.mark.parametrize(('provider', 'selector', 'mode', 'field'), CASES)
def test_store_reload_and_rename_keep_secret_out_of_index(tmp_path, provider, selector, mode, field):
    if provider not in get_supported_db_types():
        pytest.skip('Provider is not part of this branch')
    credentials = PlaintextCredentialsService()
    path = tmp_path / 'connections.json'
    store = ConnectionStore(credentials, file_path=path)
    config = config_for(provider, selector, mode, field)
    store.save_one(config)
    assert 'SYNTHETIC' not in path.read_text()
    assert credentials.get_password('protected') == 'SYNTHETIC_SECRET'
    loaded = store.load_all()[0]
    assert loaded.get_option(field) == 'SYNTHETIC_SECRET'
    renamed = replace(store.load_all(load_credentials=False)[0], name='renamed')
    store.save_one(renamed, previous_name='protected')
    assert credentials.get_password('protected') is None
    assert store.load_all()[0].get_option(field) == 'SYNTHETIC_SECRET'
    assert 'SYNTHETIC' not in path.read_text()


@pytest.mark.parametrize(('provider', 'selector', 'mode', 'field'), CASES)
def test_legacy_extra_options_secrets_are_protected(provider, selector, mode, field):
    config = ConnectionConfig(name='legacy', db_type=provider,
        options={selector: mode}, extra_options={field: 'SYNTHETIC_SECRET'})
    assert config.tcp_endpoint.password == 'SYNTHETIC_SECRET'
    assert field not in config.extra_options
    assert 'SYNTHETIC_SECRET' not in json.dumps(config.to_dict(include_passwords=False))


def test_switching_authentication_does_not_reuse_a_different_secret():
    config = config_for('databricks', 'auth_type', 'pat', 'access_token')
    config.set_option('auth_type', 'oauth-m2m')
    assert config.get_option('client_secret') is None
    config.set_option('client_secret', 'NEW_SECRET')
    assert config.tcp_endpoint.password == 'NEW_SECRET'


@pytest.mark.parametrize(('provider', 'selector', 'mode', 'field'), CASES)
def test_saving_another_connection_preserves_legacy_token(tmp_path, provider, selector, mode, field):
    if provider not in get_supported_db_types():
        pytest.skip('Provider is not part of this branch')
    config = config_for(provider, selector, mode, field)
    legacy = config.to_dict()
    legacy['endpoint']['password'] = None
    legacy['options'][field] = 'LEGACY_SECRET'
    path = tmp_path / 'connections.json'
    path.write_text(json.dumps({'version': 2, 'connections': [legacy]}))
    credentials = PlaintextCredentialsService()
    store = ConnectionStore(credentials, file_path=path)
    other = ConnectionConfig(name='unrelated', db_type='postgresql', endpoint=TcpEndpoint(host='localhost'))
    store.save_one(other)
    assert credentials.get_password('protected') == 'LEGACY_SECRET'
    assert 'LEGACY_SECRET' not in path.read_text()
    assert store.get_by_name('protected').get_option(field) == 'LEGACY_SECRET'


def test_failed_legacy_migration_preserves_original_file(tmp_path):
    from sqlit.domains.connections.app.credentials import CredentialsStoreError

    provider, selector, mode, field = next(case for case in CASES if case[0] in get_supported_db_types())
    legacy = config_for(provider, selector, mode, field).to_dict()
    legacy['endpoint']['password'] = None
    legacy['options'][field] = 'LEGACY_SECRET'
    path = tmp_path / 'connections.json'
    original = json.dumps({'version': 2, 'connections': [legacy]})
    path.write_text(original)

    class UnavailableCredentials(PlaintextCredentialsService):
        def set_password(self, name, password):
            raise CredentialsStoreError(connection_name=name, kind='db', action='store', reason=RuntimeError('locked'))

    store = ConnectionStore(UnavailableCredentials(), file_path=path)
    with pytest.raises(CredentialsStoreError):
        store.load_all()
    assert path.read_text() == original


@pytest.mark.parametrize('save_all', [False, True])
def test_auth_mode_change_without_a_new_secret_clears_old_credential(tmp_path, save_all):
    provider = 'databricks' if 'databricks' in get_supported_db_types() else 'exasol'
    selector = 'auth_type' if provider == 'databricks' else 'authenticator'
    old_mode, new_mode, new_field = ('pat', 'oauth-m2m', 'client_secret') if provider == 'databricks' else ('access_token', 'refresh_token', 'refresh_token')
    credentials = PlaintextCredentialsService()
    store = ConnectionStore(credentials, file_path=tmp_path / 'connections.json')
    store.save_one(config_for(provider, selector, old_mode, 'access_token'))
    changed = store.load_all(load_credentials=False)[0]
    changed.set_option(selector, new_mode)
    if save_all:
        store.save_all([changed])
    else:
        store.save_one(changed)
    assert credentials.get_password(changed.name) is None
    assert store.load_all()[0].get_option(new_field) is None


def test_empty_token_field_means_no_new_credential():
    config = ConnectionConfig(name='blank', db_type='databricks', options={'access_token': ''})
    assert config.tcp_endpoint.password is None


@pytest.mark.parametrize(('provider', 'selector', 'mode', 'field'), CASES)
def test_driver_restart_cache_does_not_persist_provider_secrets(tmp_path, monkeypatch, provider, selector, mode, field):
    from sqlit.domains.connections.ui import restart_cache

    path = tmp_path / 'restart.json'
    monkeypatch.setattr(restart_cache, 'get_restart_cache_path', lambda: path)
    values = config_for(provider, selector, mode, field).to_form_values()
    restart_cache.write_restart_cache({'version': 1, 'values': values})
    assert 'SYNTHETIC_SECRET' not in path.read_text()
    assert 'SYNTHETIC_URL_SECRET' not in path.read_text()
    assert values[field] == 'SYNTHETIC_SECRET'
