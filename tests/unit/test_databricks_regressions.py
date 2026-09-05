"""Regressions in Databricks configuration, auth, and legacy catalog browsing."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from sqlit.domains.connections.app.url_parser import parse_connection_url
from sqlit.domains.connections.cli.prompts import _needs_db_prompt, prompt_for_password
from sqlit.domains.connections.domain.passwords import needs_db_password
from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter
from tests.helpers import ConnectionConfig


@pytest.mark.parametrize('auth', ['pat', 'oauth-u2m', 'oauth-m2m'])
def test_valid_auth_does_not_prompt_for_an_unrelated_database_password(auth):
    cfg = ConnectionConfig(name='test', db_type='databricks', server='host', options={
        'auth_type': auth, 'access_token': 'PAT', 'client_id': 'client', 'client_secret': 'SECRET',
        'http_path': '/sql/1.0/warehouses/example'})
    assert not needs_db_password(cfg)
    assert not _needs_db_prompt(cfg)
    with patch('getpass.getpass', side_effect=AssertionError('Unexpected password prompt')):
        assert prompt_for_password(cfg) is cfg


def test_browser_auth_does_not_execute_password_command():
    cfg = ConnectionConfig(name='test', db_type='databricks', server='host',
        options={'auth_type': 'oauth-u2m'}, password_command='should-not-run')
    with patch('sqlit.domains.connections.cli.prompts.run_password_command', side_effect=AssertionError('Unexpected password command')):
        prompt_for_password(cfg)


@pytest.mark.parametrize('auth_query', ['', '&auth_type=oauth-m2m&client_id=client&client_secret=SECRET'])
def test_url_parameters_reach_validation_and_secrets_are_redacted(auth_query):
    cfg = parse_connection_url('databricks://token:PAT@host/workspace?http_path=%2Fsql%2F1.0%2Fwarehouses%2Fexample&schema=demo' + auth_query)
    assert cfg.get_option('http_path') == '/sql/1.0/warehouses/example'
    assert cfg.get_option('schema') == 'demo'
    assert cfg.tcp_endpoint.database == 'workspace'
    assert 'PAT' not in str(cfg.to_dict(include_passwords=False))
    assert 'SECRET' not in str(cfg.to_dict(include_passwords=False))


def test_m2m_uses_secret_loaded_from_protected_credential_slot():
    cfg = ConnectionConfig(name='test', db_type='databricks', server='host', password='SECRET',
        options={'auth_type': 'oauth-m2m', 'client_id': 'client', 'http_path': '/sql/1.0/warehouses/example'})
    sql = MagicMock()
    adapter = DatabricksAdapter()
    with patch.object(adapter, '_import_driver_module', return_value=sql), patch(
        'sqlit.domains.connections.providers.databricks.adapter._build_m2m_credentials_provider', return_value='provider'
    ) as factory:
        adapter.connect(cfg)
    factory.assert_called_once_with('host', 'client', 'SECRET')
    assert sql.connect.call_args.kwargs['credentials_provider'] == 'provider'


@pytest.mark.parametrize(('method', 'table_type'), [('get_tables', 'TABLE'), ('get_views', 'VIEW')])
def test_hive_catalog_uses_connector_metadata_instead_of_information_schema(method, table_type):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [SimpleNamespace(TABLE_CAT='hive_metastore', TABLE_SCHEM='demo', TABLE_NAME='example')]
    assert getattr(DatabricksAdapter(), method)(conn, 'hive_metastore') == [('demo', 'example')]
    cursor.tables.assert_called_once_with(catalog_name='hive_metastore', table_types=[table_type])
    cursor.execute.assert_not_called()
    cursor.close.assert_called_once()


def test_hive_column_metadata_filters_wildcard_matches():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [
        SimpleNamespace(TABLE_CAT='hive_metastore', TABLE_SCHEM='demo', TABLE_NAME='a_b', COLUMN_NAME='correct', TYPE_NAME='INT'),
        SimpleNamespace(TABLE_CAT='hive_metastore', TABLE_SCHEM='demo', TABLE_NAME='axb', COLUMN_NAME='wrong', TYPE_NAME='INT'),
    ]
    columns = DatabricksAdapter().get_columns(conn, 'a_b', 'hive_metastore', 'demo')
    assert [c.name for c in columns] == ['correct']
    cursor.columns.assert_called_once_with(catalog_name='hive_metastore', schema_name='demo', table_name='a_b')
    cursor.execute.assert_not_called()
    cursor.close.assert_called_once()


def test_m2m_factory_builds_valid_sdk_configuration():
    sdk = pytest.importorskip('databricks.sdk.core')
    from sqlit.domains.connections.providers.databricks.adapter import _build_m2m_credentials_provider

    def headers():
        return {'Authorization': 'Bearer SYNTHETIC_ACCESS'}

    class StaticCredentials:
        def __call__(self, config):
            return headers

        def auth_type(self):
            return 'test'

    real_config = sdk.Config
    with (
        patch.object(real_config, '_resolve_host_metadata', return_value=None, create=True),
        patch.object(sdk, 'Config', side_effect=lambda **kwargs: real_config(credentials_strategy=StaticCredentials(), **kwargs)),
        patch.object(sdk, 'oauth_service_principal', return_value=headers) as authenticate,
    ):
        factory = _build_m2m_credentials_provider('example.invalid', 'client', 'SYNTHETIC_SECRET')
        assert factory() is headers
        config = authenticate.call_args.args[0]
        assert config.host == 'https://example.invalid'
        assert config.client_id == 'client'
        assert config.client_secret == 'SYNTHETIC_SECRET'
