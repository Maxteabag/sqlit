"""Unit tests for Arrow Flight SQL adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.config import ConnectionConfig


class TestFlightSQLAdapter:
    """Test Flight SQL adapter operations."""

    def test_badge_label(self):
        """Test badge label for Flight SQL."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.badge_label() == "Flight"

    def test_url_schemes(self):
        """Test URL schemes for Flight SQL."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            schemes = FlightSQLAdapter.url_schemes()
            assert "flight" in schemes
            assert "grpc" in schemes
            assert "grpc+tls" in schemes

    def test_name(self):
        """Test adapter name."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.name == "Arrow Flight SQL"

    def test_install_info(self):
        """Test install extra and package info."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.install_extra == "flight"
            assert adapter.install_package == "adbc-driver-flightsql"

    def test_driver_import_names(self):
        """Test driver import names."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.driver_import_names == ("adbc_driver_flightsql",)

    def test_quote_identifier(self):
        """Test identifier quoting (ANSI SQL double quotes)."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.quote_identifier("table") == '"table"'
            assert adapter.quote_identifier('a"b') == '"a""b"'
            assert adapter.quote_identifier("my_table") == '"my_table"'

    def test_build_select_query_without_schema(self):
        """Test SELECT query building without schema."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            query = adapter.build_select_query("users", 100)
            assert query == 'SELECT * FROM "users" LIMIT 100'

    def test_build_select_query_with_schema(self):
        """Test SELECT query building with schema."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            query = adapter.build_select_query("users", 100, schema="public")
            assert query == 'SELECT * FROM "public"."users" LIMIT 100'

    def test_supports_properties(self):
        """Test capability properties."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.supports_multiple_databases is True
            assert adapter.supports_stored_procedures is False
            assert adapter.supports_indexes is False
            assert adapter.supports_triggers is False
            assert adapter.supports_sequences is False

    def test_arrow_table_to_tuples(self):
        """Test Arrow table to tuples conversion."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            # Mock Arrow table
            mock_table = MagicMock()
            mock_table.column_names = ["id", "name", "value"]
            mock_table.__len__ = lambda self: 2
            mock_table.to_pydict.return_value = {
                "id": [1, 2],
                "name": ["Alice", "Bob"],
                "value": [10.5, 20.3],
            }

            columns, rows = adapter._arrow_table_to_tuples(mock_table)

            assert columns == ["id", "name", "value"]
            assert len(rows) == 2
            assert rows[0] == (1, "Alice", 10.5)
            assert rows[1] == (2, "Bob", 20.3)

    def test_arrow_table_to_tuples_empty(self):
        """Test Arrow table to tuples conversion with empty table."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            # Mock empty Arrow table
            mock_table = MagicMock()
            mock_table.__len__ = lambda self: 0

            columns, rows = adapter._arrow_table_to_tuples(mock_table)

            assert columns == []
            assert rows == []

    def test_arrow_table_to_tuples_none(self):
        """Test Arrow table to tuples conversion with None."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            columns, rows = adapter._arrow_table_to_tuples(None)

            assert columns == []
            assert rows == []

    def test_get_procedures_empty(self):
        """Test that get_procedures returns empty list."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.get_procedures(MagicMock()) == []

    def test_get_indexes_empty(self):
        """Test that get_indexes returns empty list."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.get_indexes(MagicMock()) == []

    def test_get_triggers_empty(self):
        """Test that get_triggers returns empty list."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.get_triggers(MagicMock()) == []

    def test_get_sequences_empty(self):
        """Test that get_sequences returns empty list."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()
            assert adapter.get_sequences(MagicMock()) == []

    def test_docker_image_patterns(self):
        """Test docker image patterns for Flight SQL."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            patterns = FlightSQLAdapter.docker_image_patterns()
            assert "sqlflite" in patterns
            assert "flight-sql" in patterns
            assert "flightsql" in patterns

    def test_docker_env_vars(self):
        """Test docker environment variable mappings."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            env_vars = FlightSQLAdapter.docker_env_vars()
            assert "user" in env_vars
            assert "password" in env_vars
            assert "database" in env_vars
            assert "SQLFLITE_PASSWORD" in env_vars["password"]

    def test_docker_default_user(self):
        """Test docker default username."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            assert FlightSQLAdapter.docker_default_user() == ""

    def test_docker_default_port(self):
        """Test docker default port."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            assert FlightSQLAdapter.docker_default_port() == 31337


class TestFlightSQLAdapterConnect:
    """Test Flight SQL connection logic."""

    def _run_connect_test(self, config, expected_uri, expected_db_kwargs):
        """Helper to run a connect test with mocked modules."""
        import sys

        from sqlit.db.adapters.flight import FlightSQLAdapter

        mock_conn = MagicMock()
        mock_dbapi = MagicMock()
        mock_dbapi.connect.return_value = mock_conn

        # Create parent module mock and link it to the dbapi submodule
        mock_parent = MagicMock()
        mock_parent.dbapi = mock_dbapi

        # Pre-populate sys.modules - both parent and submodule
        sys.modules["adbc_driver_flightsql"] = mock_parent
        sys.modules["adbc_driver_flightsql.dbapi"] = mock_dbapi

        try:
            adapter = FlightSQLAdapter()
            conn = adapter.connect(config)

            # Verify connect was called with expected args
            mock_dbapi.connect.assert_called_once_with(
                expected_uri,
                db_kwargs=expected_db_kwargs,
            )
            return conn, mock_conn
        finally:
            # Clean up
            sys.modules.pop("adbc_driver_flightsql", None)
            sys.modules.pop("adbc_driver_flightsql.dbapi", None)

    def test_connect_basic_auth(self):
        """Test connection with basic auth."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="localhost",
            port="8815",
            username="testuser",
            password="testpass",
            options={"flight_auth_type": "basic"},
        )

        conn, mock_conn = self._run_connect_test(
            config,
            "grpc://localhost:8815",
            {"username": "testuser", "password": "testpass"},
        )
        assert conn == mock_conn

    def test_connect_token_auth(self):
        """Test connection with bearer token auth."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="localhost",
            port="8815",
            options={
                "flight_auth_type": "token",
                "flight_token": "my-jwt-token",
            },
        )

        conn, mock_conn = self._run_connect_test(
            config,
            "grpc://localhost:8815",
            {"adbc.flight.sql.authorization_header": "Bearer my-jwt-token"},
        )
        assert conn == mock_conn

    def test_connect_no_auth(self):
        """Test connection with no auth."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="localhost",
            port="8815",
            options={"flight_auth_type": "none"},
        )

        conn, mock_conn = self._run_connect_test(
            config,
            "grpc://localhost:8815",
            {},
        )
        assert conn == mock_conn

    def test_connect_auto_tls_port_443(self):
        """Test that port 443 automatically uses TLS."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="flight.example.com",
            port="443",
            options={"flight_auth_type": "none"},
        )

        self._run_connect_test(
            config,
            "grpc+tls://flight.example.com:443",
            {},
        )

    def test_connect_auto_tls_port_8443(self):
        """Test that port 8443 automatically uses TLS."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="flight.example.com",
            port="8443",
            options={"flight_auth_type": "none"},
        )

        self._run_connect_test(
            config,
            "grpc+tls://flight.example.com:8443",
            {},
        )

    def test_connect_tls_disabled_overrides_port(self):
        """Test that TLS can be explicitly disabled even on port 443."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="flight.example.com",
            port="443",
            options={
                "flight_auth_type": "none",
                "flight_use_tls": "disabled",
            },
        )

        self._run_connect_test(
            config,
            "grpc://flight.example.com:443",
            {},
        )

    def test_connect_default_port(self):
        """Test connection with default port (8815)."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="localhost",
            port="",  # Empty port
            options={"flight_auth_type": "none"},
        )

        self._run_connect_test(
            config,
            "grpc://localhost:8815",
            {},
        )

    def test_connect_stores_catalog(self):
        """Test that database is stored as _sqlit_catalog on connection."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="localhost",
            port="8815",
            database="my_catalog",
            options={"flight_auth_type": "none"},
        )

        conn, _ = self._run_connect_test(
            config,
            "grpc://localhost:8815",
            {},
        )
        # Verify catalog is stored
        assert conn._sqlit_catalog == "my_catalog"

    def test_connect_tls_skip_verify(self):
        """Test TLS with skip verify option."""
        config = ConnectionConfig(
            name="test",
            db_type="flight",
            server="localhost",
            port="443",
            options={
                "flight_auth_type": "none",
                "flight_skip_verify": "true",
            },
        )

        self._run_connect_test(
            config,
            "grpc+tls://localhost:443",
            {"adbc.flight.sql.client_option.tls_skip_verify": "true"},
        )


class TestFlightSQLAdapterExecute:
    """Test Flight SQL execution methods."""

    def test_execute_test_query(self):
        """Test execute_test_query uses cursor."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            adapter.execute_test_query(mock_conn)

            mock_cursor.execute.assert_called_once_with("SELECT 1")
            mock_cursor.fetchone.assert_called_once()

    def test_execute_query_with_arrow_table(self):
        """Test execute_query using Arrow table fetch."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            # Mock Arrow table
            mock_table = MagicMock()
            mock_table.column_names = ["id", "name"]
            mock_table.__len__ = lambda self: 2
            mock_table.to_pydict.return_value = {
                "id": [1, 2],
                "name": ["Alice", "Bob"],
            }

            mock_cursor = MagicMock()
            mock_cursor.fetch_arrow_table.return_value = mock_table

            mock_conn = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            columns, rows, truncated = adapter.execute_query(mock_conn, "SELECT * FROM test")

            assert columns == ["id", "name"]
            assert len(rows) == 2
            assert rows[0] == (1, "Alice")
            assert rows[1] == (2, "Bob")
            assert truncated is False

    def test_execute_query_with_max_rows(self):
        """Test execute_query with row limiting."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            # Mock Arrow table with more rows than max_rows
            mock_table = MagicMock()
            mock_table.column_names = ["id"]
            mock_table.__len__ = lambda self: 5
            mock_table.to_pydict.return_value = {
                "id": [1, 2, 3, 4, 5],
            }

            mock_cursor = MagicMock()
            mock_cursor.fetch_arrow_table.return_value = mock_table

            mock_conn = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            columns, rows, truncated = adapter.execute_query(
                mock_conn, "SELECT * FROM test", max_rows=3
            )

            assert len(rows) == 3
            assert truncated is True

    def test_execute_non_query(self):
        """Test execute_non_query returns rowcount."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            mock_cursor = MagicMock()
            mock_cursor.rowcount = 5

            mock_conn = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = adapter.execute_non_query(mock_conn, "INSERT INTO test VALUES (1)")

            assert result == 5
            mock_cursor.execute.assert_called_once_with("INSERT INTO test VALUES (1)")

    def test_execute_non_query_no_rowcount(self):
        """Test execute_non_query returns -1 when rowcount not available."""
        with patch.dict(
            "sys.modules",
            {"adbc_driver_flightsql": MagicMock(), "adbc_driver_flightsql.dbapi": MagicMock()},
        ):
            from sqlit.db.adapters.flight import FlightSQLAdapter

            adapter = FlightSQLAdapter()

            mock_cursor = MagicMock()
            mock_cursor.rowcount = -1

            mock_conn = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            result = adapter.execute_non_query(mock_conn, "CREATE TABLE test (id INT)")

            assert result == -1
