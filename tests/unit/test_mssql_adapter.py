"""Unit tests for MSSQL adapter - specifically testing Azure SQL compatibility.

These tests verify that the MSSQL adapter uses USE [database] instead of
cross-database references like [Database].INFORMATION_SCHEMA.TABLES,
which are not supported in Azure SQL Database.

Azure SQL Database has two restrictions:
1. Cross-database references like [Database].INFORMATION_SCHEMA.TABLES don't work
2. USE statement to switch databases doesn't work either

The adapter handles both by:
1. Using USE [database] for regular SQL Server
2. Gracefully handling the USE failure for Azure SQL Database
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMSSQLAdapterNoCrossDatabaseReferences:
    """Test that MSSQL adapter avoids cross-database query syntax.

    Azure SQL Database does not support cross-database references like:
    - [Database].INFORMATION_SCHEMA.TABLES
    - [Database].sys.tables

    Instead, the adapter attempts USE [database] to switch context,
    and gracefully handles failure (Azure SQL Database).
    """

    @pytest.fixture
    def mock_mssql(self):
        """Create a mock mssql_python module."""
        mock = MagicMock()
        with patch.dict("sys.modules", {"mssql_python": mock}):
            yield mock

    @pytest.fixture
    def adapter(self, mock_mssql):
        """Create an MSSQL adapter instance."""
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
        return SQLServerAdapter()

    @pytest.fixture
    def mock_conn(self):
        """Create a mock connection with cursor."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        return conn

    def _get_executed_sql(self, mock_conn) -> list[str]:
        """Extract all SQL statements executed on the cursor."""
        cursor = mock_conn.cursor.return_value
        return [call[0][0] for call in cursor.execute.call_args_list]

    def _assert_no_cross_db_refs(self, sql_statements: list[str], database: str):
        """Assert no SQL contains cross-database references."""
        patterns = [
            f"[{database}].",
            f"[{database.lower()}].",
            f"[{database.upper()}].",
        ]
        for sql in sql_statements:
            for pattern in patterns:
                assert pattern not in sql, (
                    f"Found cross-database reference '{pattern}' in SQL: {sql}\n"
                    "This syntax is not supported in Azure SQL Database. "
                    "Use 'USE [database]' instead."
                )

    def _assert_uses_database_context(self, sql_statements: list[str], database: str):
        """Assert USE [database] is called before other queries."""
        assert len(sql_statements) >= 1, "Expected at least one SQL statement"
        use_stmt = sql_statements[0]
        assert use_stmt == f"USE [{database}]", (
            f"Expected first statement to be 'USE [{database}]', got: {use_stmt}"
        )

    def test_get_tables_uses_context_switch(self, adapter, mock_conn):
        """Test get_tables uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_tables(mock_conn, database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_views_uses_context_switch(self, adapter, mock_conn):
        """Test get_views uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_views(mock_conn, database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_columns_uses_context_switch(self, adapter, mock_conn):
        """Test get_columns uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_columns(mock_conn, table="Users", database=database, schema="dbo")

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_procedures_uses_context_switch(self, adapter, mock_conn):
        """Test get_procedures uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_procedures(mock_conn, database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_indexes_uses_context_switch(self, adapter, mock_conn):
        """Test get_indexes uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_indexes(mock_conn, database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_triggers_uses_context_switch(self, adapter, mock_conn):
        """Test get_triggers uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_triggers(mock_conn, database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_sequences_uses_context_switch(self, adapter, mock_conn):
        """Test get_sequences uses USE instead of cross-database reference."""
        database = "TestDB"
        adapter.get_sequences(mock_conn, database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_index_definition_uses_context_switch(self, adapter, mock_conn):
        """Test get_index_definition uses USE instead of cross-database reference."""
        database = "TestDB"
        mock_conn.cursor.return_value.fetchall.return_value = [
            (False, "NONCLUSTERED", "col1")
        ]
        adapter.get_index_definition(mock_conn, "IX_Test", "Users", database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_trigger_definition_uses_context_switch(self, adapter, mock_conn):
        """Test get_trigger_definition uses USE instead of cross-database reference."""
        database = "TestDB"
        mock_conn.cursor.return_value.fetchone.return_value = ("CREATE TRIGGER...", "AFTER")
        adapter.get_trigger_definition(mock_conn, "TR_Test", "Users", database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_get_sequence_definition_uses_context_switch(self, adapter, mock_conn):
        """Test get_sequence_definition uses USE instead of cross-database reference."""
        database = "TestDB"
        mock_conn.cursor.return_value.fetchone.return_value = (1, 1, 1, 9999, False)
        adapter.get_sequence_definition(mock_conn, "SEQ_Test", database=database)

        sql_statements = self._get_executed_sql(mock_conn)
        self._assert_uses_database_context(sql_statements, database)
        self._assert_no_cross_db_refs(sql_statements, database)

    def test_no_use_statement_when_no_database(self, adapter, mock_conn):
        """Test that USE is not called when database is None."""
        adapter.get_tables(mock_conn, database=None)

        sql_statements = self._get_executed_sql(mock_conn)
        assert len(sql_statements) == 1, "Expected only one SQL statement"
        assert not sql_statements[0].startswith("USE"), (
            "Should not call USE when database is None"
        )


class TestMSSQLAdapterQueries:
    """Test MSSQL adapter query correctness."""

    @pytest.fixture
    def mock_mssql(self):
        mock = MagicMock()
        with patch.dict("sys.modules", {"mssql_python": mock}):
            yield mock

    @pytest.fixture
    def adapter(self, mock_mssql):
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter
        return SQLServerAdapter()

    def test_get_tables_query_structure(self, adapter):
        """Test get_tables executes correct query."""
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor
        cursor.fetchall.return_value = [("dbo", "Users"), ("dbo", "Orders")]

        result = adapter.get_tables(mock_conn, database="TestDB")

        assert result == [("dbo", "Users"), ("dbo", "Orders")]
        # Verify query uses INFORMATION_SCHEMA without database prefix
        query_call = cursor.execute.call_args_list[-1]
        assert "INFORMATION_SCHEMA.TABLES" in query_call[0][0]
        assert "BASE TABLE" in query_call[0][0]

    def test_get_columns_returns_primary_keys(self, adapter):
        """Test get_columns correctly identifies primary keys."""
        mock_conn = MagicMock()
        cursor = MagicMock()
        mock_conn.cursor.return_value = cursor

        # First call returns PK columns, second returns all columns
        cursor.fetchall.side_effect = [
            [("id",)],  # Primary key columns
            [("id", "int"), ("name", "varchar"), ("email", "varchar")],  # All columns
        ]

        result = adapter.get_columns(mock_conn, "Users", database="TestDB", schema="dbo")

        assert len(result) == 3
        assert result[0].name == "id"
        assert result[0].is_primary_key is True
        assert result[1].name == "name"
        assert result[1].is_primary_key is False


class TestMSSQLAdapterAzureAdPreflight:
    """Pre-flight Entra-token check for ad_default auth.

    The pre-flight does three things:
    1. Surfaces credential-chain failures as an actionable AzureAdAuthError
       (vs the driver's generic "Login failed for user ''")
    2. Returns the JWT so connect() can hand it to the ODBC driver via
       SQL_COPT_SS_ACCESS_TOKEN, skipping the driver's redundant acquisition
    3. Caches the JWT on disk to avoid spawning `az` on every invocation
    """

    @pytest.fixture
    def ad_default_config(self):
        """Minimal ConnectionConfig stub with auth_type=ad_default."""
        from sqlit.domains.connections.domain.config import (
            ConnectionConfig,
            TcpEndpoint,
        )

        endpoint = TcpEndpoint(host="example.database.windows.net", port="1433", database="mydb")
        return ConnectionConfig(
            name="t",
            db_type="mssql",
            endpoint=endpoint,
            options={"auth_type": "ad_default"},
        )

    @pytest.fixture(autouse=True)
    def _empty_token_cache(self):
        """Patch out the token cache so tests don't depend on the user's
        ~/.config/sqlit/azure_sql_token.json file."""
        from sqlit.domains.connections.providers.mssql import token_cache

        with patch.object(token_cache, "load", return_value=None), \
                patch.object(token_cache, "save"):
            yield

    def test_preflight_surfaces_az_login_hint_on_credential_failure(self, ad_default_config):
        """When DefaultAzureCredential.get_token raises, we raise AzureAdAuthError
        with the actionable 'Please run az login' line and a one-line hint."""
        from sqlit.domains.connections.providers.mssql.adapter import (
            AzureAdAuthError,
            SQLServerAdapter,
        )

        chain_message = (
            "DefaultAzureCredential failed to retrieve a token from the included credentials.\n"
            "Attempted credentials:\n"
            "\tEnvironmentCredential: EnvironmentCredential authentication unavailable.\n"
            "\tAzureCliCredential: Please run 'az login' to set up an account\n"
            "\tAzurePowerShellCredential: Az.Account module >= 2.2.0 is not installed\n"
        )

        fake_azure_core = MagicMock()
        fake_azure_core_exceptions = MagicMock()

        class _ClientAuthError(Exception):
            pass

        fake_azure_core_exceptions.ClientAuthenticationError = _ClientAuthError

        fake_azure_identity = MagicMock()
        fake_credential = MagicMock()
        fake_credential.get_token.side_effect = _ClientAuthError(chain_message)
        fake_azure_identity.DefaultAzureCredential.return_value = fake_credential

        with patch.dict(
            "sys.modules",
            {
                "azure": MagicMock(),
                "azure.core": fake_azure_core,
                "azure.core.exceptions": fake_azure_core_exceptions,
                "azure.identity": fake_azure_identity,
            },
        ):
            adapter = SQLServerAdapter()
            with pytest.raises(AzureAdAuthError) as exc_info:
                adapter._preflight_azure_credentials(ad_default_config)

        message = str(exc_info.value)
        assert "Please run 'az login'" in message
        assert "Azure AD authentication failed" in message
        # The verbose chain dump should NOT be included when we extracted a
        # specific actionable line — keep the error tight, like sqlcmd does.
        assert "DefaultAzureCredential failed to retrieve" not in message

    def test_preflight_returns_none_when_azure_identity_missing(self, ad_default_config):
        """If azure-identity is not installed, we return None and let the
        ODBC driver handle auth (preserving the existing behavior)."""
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        import builtins

        real_import = builtins.__import__

        def _block_azure(name, *args, **kwargs):
            if name.startswith("azure."):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        adapter = SQLServerAdapter()
        with patch("builtins.__import__", side_effect=_block_azure):
            assert adapter._preflight_azure_credentials(ad_default_config) is None

    def test_preflight_skipped_for_non_ad_default_auth(self):
        """Pre-flight only runs for ad_default; sql/ad_password etc. return
        None and must not touch azure-identity at all."""
        from sqlit.domains.connections.domain.config import (
            ConnectionConfig,
            TcpEndpoint,
        )
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        endpoint = TcpEndpoint(host="h", port="1433", database="d", username="u", password="p")
        config = ConnectionConfig(
            name="t",
            db_type="mssql",
            endpoint=endpoint,
            options={"auth_type": "sql"},
        )

        adapter = SQLServerAdapter()
        assert adapter._preflight_azure_credentials(config) is None

    def test_preflight_uses_cached_token_without_calling_credential(self, ad_default_config):
        """A valid cached token is returned immediately — no az subprocess,
        no credential-chain probing."""
        from sqlit.domains.connections.providers.mssql import token_cache
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        cached = token_cache.CachedToken(token="cached-jwt-value", expires_on=9_999_999_999)
        fake_azure_identity = MagicMock()
        fake_azure_identity.DefaultAzureCredential.side_effect = AssertionError(
            "Credential must not be constructed on cache hit"
        )

        with patch.object(token_cache, "load", return_value=cached), \
                patch.dict("sys.modules", {
                    "azure": MagicMock(),
                    "azure.core": MagicMock(),
                    "azure.core.exceptions": MagicMock(),
                    "azure.identity": fake_azure_identity,
                }):
            adapter = SQLServerAdapter()
            assert adapter._preflight_azure_credentials(ad_default_config) == "cached-jwt-value"

    def test_preflight_saves_freshly_acquired_token_to_cache(self, ad_default_config):
        """After a successful credential acquisition, the JWT is persisted
        so subsequent invocations skip the az subprocess."""
        from sqlit.domains.connections.providers.mssql import token_cache
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        fake_token = MagicMock()
        fake_token.token = "freshly-acquired-jwt"
        fake_token.expires_on = 9_999_999_999

        fake_azure_identity = MagicMock()
        fake_credential = MagicMock()
        fake_credential.get_token.return_value = fake_token
        fake_azure_identity.DefaultAzureCredential.return_value = fake_credential

        with patch.object(token_cache, "save") as save_mock, \
                patch.dict("sys.modules", {
                    "azure": MagicMock(),
                    "azure.core": MagicMock(),
                    "azure.core.exceptions": MagicMock(),
                    "azure.identity": fake_azure_identity,
                }):
            adapter = SQLServerAdapter()
            result = adapter._preflight_azure_credentials(ad_default_config)

        assert result == "freshly-acquired-jwt"
        save_mock.assert_called_once_with("freshly-acquired-jwt", 9_999_999_999)


class TestMSSQLAdapterAccessTokenAttach:
    """connect() must hand the pre-acquired token directly to the ODBC driver
    via SQL_COPT_SS_ACCESS_TOKEN, *and* strip the conflicting
    `Authentication=ActiveDirectoryDefault` directive from the conn string.
    """

    def test_build_connection_string_omits_auth_directive_when_attaching_token(self):
        """With attach_token=True for ad_default, the conn string must NOT
        include `Authentication=...` — that directive would make the driver
        spawn `az` for its own token, defeating the whole optimization."""
        from sqlit.domains.connections.domain.config import (
            ConnectionConfig,
            TcpEndpoint,
        )
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        endpoint = TcpEndpoint(host="example.database.windows.net", port="1433", database="mydb")
        config = ConnectionConfig(
            name="t",
            db_type="mssql",
            endpoint=endpoint,
            options={"auth_type": "ad_default"},
        )

        adapter = SQLServerAdapter()
        without_attach = adapter._build_connection_string(config, attach_token=False)
        with_attach = adapter._build_connection_string(config, attach_token=True)

        assert "Authentication=ActiveDirectoryDefault" in without_attach
        assert "Authentication=" not in with_attach
        assert "SERVER=example.database.windows.net" in with_attach
        assert "DATABASE=mydb" in with_attach

    def test_access_token_struct_layout_matches_sql_server_protocol(self):
        """SQL_COPT_SS_ACCESS_TOKEN expects: 4-byte LE length prefix +
        UTF-16-LE token bytes. This is the exact layout the mssql-python
        driver builds internally; we replicate it so the driver accepts it."""
        from sqlit.domains.connections.providers.mssql.adapter import (
            _build_access_token_struct,
        )

        token = "abc"
        result = _build_access_token_struct(token)

        utf16 = token.encode("UTF-16-LE")  # 6 bytes for 3 ASCII chars
        assert len(utf16) == 6
        # 4-byte length prefix (LE) + the bytes
        assert result[:4] == (6).to_bytes(4, "little")
        assert result[4:] == utf16

    def test_connect_passes_token_via_attrs_before(self):
        """connect() must call mssql_python.connect() with
        attrs_before={SQL_COPT_SS_ACCESS_TOKEN: <struct>} when the pre-flight
        returns a token. This is what eliminates the duplicate auth round."""
        from sqlit.domains.connections.domain.config import (
            ConnectionConfig,
            TcpEndpoint,
        )
        from sqlit.domains.connections.providers.mssql.adapter import (
            SQL_COPT_SS_ACCESS_TOKEN,
            SQLServerAdapter,
            _build_access_token_struct,
        )

        endpoint = TcpEndpoint(host="example.database.windows.net", port="1433", database="mydb")
        config = ConnectionConfig(
            name="t",
            db_type="mssql",
            endpoint=endpoint,
            options={"auth_type": "ad_default"},
        )

        mock_mssql = MagicMock()
        mock_conn = MagicMock()
        mock_mssql.connect.return_value = mock_conn

        adapter = SQLServerAdapter()
        with patch.dict("sys.modules", {"mssql_python": mock_mssql}), \
                patch.object(SQLServerAdapter, "_preflight_azure_credentials",
                             return_value="my-jwt"):
            adapter.connect(config)

        assert mock_mssql.connect.call_count == 1
        _args, kwargs = mock_mssql.connect.call_args
        attrs = kwargs.get("attrs_before")
        assert attrs is not None
        assert SQL_COPT_SS_ACCESS_TOKEN in attrs
        assert attrs[SQL_COPT_SS_ACCESS_TOKEN] == _build_access_token_struct("my-jwt")

    def test_connect_passes_attrs_before_none_when_no_token(self):
        """For non-ad_default auth (no pre-acquired token), attrs_before is
        None and the driver uses its normal auth path."""
        from sqlit.domains.connections.domain.config import (
            ConnectionConfig,
            TcpEndpoint,
        )
        from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

        endpoint = TcpEndpoint(host="h", port="1433", database="d", username="u", password="p")
        config = ConnectionConfig(
            name="t",
            db_type="mssql",
            endpoint=endpoint,
            options={"auth_type": "sql"},
        )

        mock_mssql = MagicMock()
        mock_mssql.connect.return_value = MagicMock()

        adapter = SQLServerAdapter()
        with patch.dict("sys.modules", {"mssql_python": mock_mssql}):
            adapter.connect(config)

        _args, kwargs = mock_mssql.connect.call_args
        assert kwargs.get("attrs_before") is None


class TestMSSQLTokenCache:
    """File-backed cache for the SQL Entra access token — avoids spawning
    `az account get-access-token` on every cold `sqlit query` invocation."""

    def test_load_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        from sqlit.domains.connections.providers.mssql import token_cache

        monkeypatch.setattr(token_cache, "CACHE_FILE", tmp_path / "missing.json")
        assert token_cache.load() is None

    def test_load_returns_none_when_corrupt_json(self, tmp_path, monkeypatch):
        from sqlit.domains.connections.providers.mssql import token_cache

        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not json", encoding="utf-8")
        monkeypatch.setattr(token_cache, "CACHE_FILE", cache_file)
        assert token_cache.load() is None

    def test_load_returns_none_when_token_expired(self, tmp_path, monkeypatch):
        """A token already past its expiry is treated as a cache miss."""
        import json

        from sqlit.domains.connections.providers.mssql import token_cache

        cache_file = tmp_path / "cache.json"
        cache_file.write_text(json.dumps({"token": "x", "expires_on": 0}), encoding="utf-8")
        monkeypatch.setattr(token_cache, "CACHE_FILE", cache_file)
        assert token_cache.load() is None

    def test_load_returns_none_when_within_refresh_window(self, tmp_path, monkeypatch):
        """Tokens about to expire (within the 5-minute refresh window) are
        also treated as a miss so we don't hand the driver a stale token."""
        import json
        import time

        from sqlit.domains.connections.providers.mssql import token_cache

        cache_file = tmp_path / "cache.json"
        cache_file.write_text(
            json.dumps({"token": "x", "expires_on": int(time.time()) + 60}),
            encoding="utf-8",
        )
        monkeypatch.setattr(token_cache, "CACHE_FILE", cache_file)
        assert token_cache.load() is None

    def test_save_then_load_roundtrip(self, tmp_path, monkeypatch):
        import os
        import time

        from sqlit.domains.connections.providers.mssql import token_cache

        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(token_cache, "CACHE_FILE", cache_file)

        expires = int(time.time()) + 3600
        token_cache.save("my-jwt", expires)

        loaded = token_cache.load()
        assert loaded is not None
        assert loaded.token == "my-jwt"
        assert loaded.expires_on == expires
        # 0600 — owner read/write only
        assert oct(os.stat(cache_file).st_mode & 0o777) == "0o600"
