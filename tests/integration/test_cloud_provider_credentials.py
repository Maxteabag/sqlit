"""Opt-in real-service proof of CLI, protected persistence and adapter behavior.

Set SQLIT_LIVE_PROVIDER (databricks/exasol), SQLIT_LIVE_HOST and
SQLIT_LIVE_TOKEN. Databricks also needs SQLIT_LIVE_HTTP_PATH; Exasol needs
SQLIT_LIVE_USERNAME. The token is read only from the environment and passed to
CLI creation on stdin. The CLI must use a working OS keyring, never plaintext.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest

from sqlit.domains.connections.app.credentials import KeyringCredentialsService, is_keyring_usable
from sqlit.domains.connections.providers.registry import get_adapter, get_supported_db_types
from sqlit.domains.connections.store.connections import ConnectionStore


def test_saved_cloud_connection_survives_cli_reload_and_rename(tmp_path):
    provider = os.environ.get('SQLIT_LIVE_PROVIDER')
    if not provider:
        pytest.skip('Set SQLIT_LIVE_PROVIDER to run against an owned cloud test database')
    if provider not in {'databricks', 'exasol'} or provider not in get_supported_db_types():
        pytest.fail('Requested cloud provider is not available in this branch')
    required = ['SQLIT_LIVE_HOST', 'SQLIT_LIVE_TOKEN']
    required.append('SQLIT_LIVE_HTTP_PATH' if provider == 'databricks' else 'SQLIT_LIVE_USERNAME')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        pytest.fail(f'Missing live-test configuration: {missing}')
    if not is_keyring_usable():
        pytest.fail('Live saved-connection proof requires a working OS keyring')

    secret = os.environ['SQLIT_LIVE_TOKEN']
    host = os.environ['SQLIT_LIVE_HOST']
    catalog = os.environ.get('SQLIT_LIVE_CATALOG', 'workspace') if provider == 'databricks' else ''
    user = 'token' if provider == 'databricks' else os.environ['SQLIT_LIVE_USERNAME']
    port = '' if provider == 'databricks' else ':' + os.environ.get('SQLIT_LIVE_PORT', '8563')
    query = urlencode({'http_path': os.environ['SQLIT_LIVE_HTTP_PATH']}) if provider == 'databricks' else ''
    url = f'{provider}://{quote(user, safe="")}:{quote(secret, safe="")}@{host}{port}/{catalog}'
    if query:
        url += '?' + query
    name = 'sqlit-live-' + uuid.uuid4().hex
    renamed = name + '-renamed'
    env = dict(os.environ, SQLIT_CONFIG_DIR=str(tmp_path))
    # Do not forward the credential environment variable to CLI processes.
    env.pop('SQLIT_LIVE_TOKEN', None)
    (tmp_path / 'settings.json').write_text('{"allow_plaintext_credentials": false}')
    credentials = KeyringCredentialsService()
    store = ConnectionStore(credentials, file_path=tmp_path / 'connections.json')
    repo = Path(__file__).resolve().parents[2]

    def cli(*args, input_text=None):
        process = subprocess.run([sys.executable, '-m', 'sqlit.cli', *args],
            cwd=repo, env=env, input=input_text, text=True, capture_output=True, timeout=180)
        output = (process.stdout + process.stderr).replace(secret, '[REDACTED]')
        assert process.returncode == 0, output
        return process.stdout

    def assert_index_is_protected():
        leaked = secret in (tmp_path / 'connections.json').read_text()
        assert not leaked, 'Credential leaked into the saved connection index'
        assert not (tmp_path / 'credentials.json').exists(), 'Unexpected plaintext credential file'

    conn = None
    created = False
    adapter = get_adapter(provider)
    schema = ('SQLIT_TEST_' + uuid.uuid4().hex[:12]).lower() if provider == 'databricks' else 'SQLIT_TEST_' + uuid.uuid4().hex[:12].upper()
    q = adapter.quote_identifier
    namespace = f'{q(catalog)}.{q(schema)}' if catalog else q(schema)
    table_name = 'probe' if provider == 'databricks' else 'PROBE'
    view_name = 'probe_view' if provider == 'databricks' else 'PROBE_VIEW'
    table = namespace + '.' + q(table_name)
    try:
        cli('connections', 'add', '--name', name, '--url-stdin', input_text=url + '\n')
        assert_index_is_protected()
        result = json.loads(cli('query', '-c', name, '-q', 'SELECT 1 AS probe', '--format', 'json'))
        assert list(result[0].values()) == [1]
        config = store.get_by_name(name)
        assert config is not None
        conn = adapter.connect(config)
        adapter.execute_non_query(conn, f'CREATE SCHEMA {namespace}')
        created = True
        adapter.execute_non_query(conn, f'CREATE TABLE {table} (id INTEGER, label VARCHAR(40))')
        adapter.execute_non_query(conn, f"INSERT INTO {table} VALUES (1, 'alpha'), (2, 'beta'), (3, NULL)")
        _, rows, truncated = adapter.execute_query(conn, f'SELECT id, label FROM {table} ORDER BY id', max_rows=2)
        assert rows == [(1, 'alpha'), (2, 'beta')]
        assert truncated
        adapter.execute_non_query(conn, f'CREATE VIEW {namespace}.{q(view_name)} AS SELECT * FROM {table}')
        assert (schema, table_name) in adapter.get_tables(conn, catalog or None)
        assert (schema, view_name) in adapter.get_views(conn, catalog or None)
        columns = adapter.get_columns(conn, table_name, catalog or None, schema)
        assert [column.name.lower() for column in columns] == ['id', 'label']
        store.save_one(replace(store.load_all(load_credentials=False)[0], name=renamed), previous_name=name)
        assert_index_is_protected()
        result = json.loads(cli('query', '-c', renamed, '-q', f'SELECT COUNT(*) AS n FROM {table}', '--format', 'json'))
        assert list(result[0].values()) == [3]
    finally:
        try:
            if conn is not None:
                try:
                    if created:
                        adapter.execute_non_query(conn, f'DROP SCHEMA {namespace} CASCADE')
                finally:
                    conn.close()
        finally:
            for connection_name in (name, renamed):
                store.delete(connection_name)
                credentials.delete_all_for_connection(connection_name)
