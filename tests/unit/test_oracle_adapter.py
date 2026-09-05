"""Unit tests for Oracle adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from tests.helpers import ConnectionConfig


class TestOracleAdapterSchemaIntrospection:
    """Regression coverage for issue #295."""

    def test_get_tables_returns_all_accessible_schema_owners(self):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ("COMMON", "CUSTOMERS"),
            ("REPORTING", "MONTHLY_TOTALS"),
        ]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        tables = OracleAdapter().get_tables(conn)

        assert tables == [
            ("COMMON", "CUSTOMERS"),
            ("REPORTING", "MONTHLY_TOTALS"),
        ]
        assert "all_tables" in cursor.execute.call_args.args[0].lower()

    def test_get_views_returns_all_accessible_schema_owners(self):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        cursor = MagicMock()
        cursor.fetchall.return_value = [("COMMON", "ACTIVE_CUSTOMERS")]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        assert OracleAdapter().get_views(conn) == [("COMMON", "ACTIVE_CUSTOMERS")]
        assert "all_views" in cursor.execute.call_args.args[0].lower()

    def test_get_columns_scopes_cross_schema_table_and_primary_key(self):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        pk_cursor = MagicMock()
        pk_cursor.fetchall.return_value = [("ID",)]
        columns_cursor = MagicMock()
        columns_cursor.fetchall.return_value = [
            ("ID", "NUMBER"),
            ("NAME", "VARCHAR2"),
        ]
        conn = MagicMock()
        conn.cursor.side_effect = [pk_cursor, columns_cursor]

        columns = OracleAdapter().get_columns(conn, "Customers", schema="Reporting")

        assert [(column.name, column.is_primary_key) for column in columns] == [
            ("ID", True),
            ("NAME", False),
        ]
        pk_sql = pk_cursor.execute.call_args.args[0].lower()
        columns_sql = columns_cursor.execute.call_args.args[0].lower()
        assert "all_constraints" in pk_sql
        assert "all_cons_columns" in pk_sql
        assert "all_tab_columns" in columns_sql
        expected_params = {"table_name": "Customers", "owner_name": "Reporting"}
        assert pk_cursor.execute.call_args.args[1] == expected_params
        assert columns_cursor.execute.call_args.args[1] == expected_params

    def test_legacy_select_qualifies_cross_schema_table(self):
        from sqlit.domains.connections.providers.oracle_legacy.adapter import (
            OracleLegacyAdapter,
        )

        query = OracleLegacyAdapter().build_select_query("CUSTOMERS", 100, schema="COMMON")

        assert query == ('SELECT * FROM (SELECT * FROM "COMMON"."CUSTOMERS") WHERE ROWNUM <= 100')

    def test_select_qualifies_cross_schema_table(self):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        query = OracleAdapter().build_select_query("Customers", 100, schema="Reporting")

        assert query == ('SELECT * FROM "Reporting"."Customers" FETCH FIRST 100 ROWS ONLY')

    @pytest.mark.parametrize(
        ("method", "dictionary_view", "rows", "expected"),
        [
            ("get_procedures", "all_procedures", [("REPORTING", "REFRESH_TOTALS")], ["REPORTING.REFRESH_TOTALS"]),
            ("get_indexes", "all_indexes", [("INDEX_OWNER", "IX_TOTALS", "TABLE_OWNER", "MONTHLY_TOTALS", "UNIQUE")], None),
            ("get_triggers", "all_triggers", [("TRIGGER_OWNER", "TRG_TOTALS", "TABLE_OWNER", "MONTHLY_TOTALS")], None),
            ("get_sequences", "all_sequences", [("REPORTING", "TOTALS_SEQ")], None),
        ],
    )
    def test_auxiliary_objects_include_accessible_schema_owners(self, method, dictionary_view, rows, expected):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        conn = MagicMock()
        conn.cursor.return_value = cursor

        result = getattr(OracleAdapter(), method)(conn)

        assert dictionary_view in cursor.execute.call_args.args[0].lower()
        if expected is not None:
            assert result == expected
        else:
            assert result[0].name.endswith("." + rows[0][1])
            if method in {"get_indexes", "get_triggers"}:
                assert result[0].table_name == "TABLE_OWNER.MONTHLY_TOTALS"

    @pytest.mark.parametrize(
        ("method", "dictionary_view", "args"),
        [
            ("get_index_definition", "all_indexes", ("REPORTING.IX_TOTALS", "REPORTING.MONTHLY_TOTALS")),
            ("get_trigger_definition", "all_triggers", ("REPORTING.TRG_TOTALS", "REPORTING.MONTHLY_TOTALS")),
            ("get_sequence_definition", "all_sequences", ("REPORTING.TOTALS_SEQ",)),
        ],
    )
    def test_auxiliary_definition_uses_qualified_owner(self, method, dictionary_view, args):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cursor

        getattr(OracleAdapter(), method)(conn, *args)

        calls = [call.args for call in cursor.execute.call_args_list]
        assert any(dictionary_view in sql.lower() for sql, *_ in calls)
        assert any("REPORTING" in repr(params) for _, params in calls)

    def test_quoted_dotted_auxiliary_owner_round_trips(self):
        from sqlit.domains.connections.providers.oracle.adapter import (
            OracleAdapter,
            _dictionary_qualified_name,
        )

        qualified = _dictionary_qualified_name("REPORT.ING", "IX.A")
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cursor

        OracleAdapter().get_index_definition(conn, qualified, "T")

        assert cursor.execute.call_args_list[0].args[1] == ("IX.A", "REPORT.ING")

    def test_unqualified_auxiliary_definition_preserves_oracle_uppercase_lookup(self):
        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cursor

        OracleAdapter().get_sequence_definition(conn, "test_sequence")

        assert cursor.execute.call_args.args[1] == ("TEST_SEQUENCE", None)
class TestOracleAdapterClientMode:
    """Regression coverage for Oracle databases that require Thick mode."""

    def test_connect_defaults_to_thin_mode(self):
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
            )

            OracleAdapter().connect(config)

            mock_oracledb.init_oracle_client.assert_not_called()

    def test_thin_mode_rejects_process_already_initialized_as_thick(self):
        mock_oracledb = MagicMock()
        mock_oracledb.is_thin_mode.return_value = False

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                options={"oracle_client_mode": "thin"},
            )

            with pytest.raises(ValueError, match="Restart sqlit"):
                OracleAdapter().connect(config)

            mock_oracledb.connect.assert_not_called()

    def test_connect_enables_thick_mode_before_connecting(self):
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                options={"oracle_client_mode": "thick"},
            )

            OracleAdapter().connect(config)

            mock_oracledb.init_oracle_client.assert_called_once_with()
            assert mock_oracledb.method_calls.index(call.init_oracle_client()) < mock_oracledb.method_calls.index(
                call.connect(
                    user="testuser",
                    password="testpass",
                    dsn="localhost:1521/ORCL",
                )
            )

    def test_connect_passes_configured_client_library_path(self):
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                options={
                    "oracle_client_mode": "thick",
                    "oracle_client_lib_dir": "/opt/oracle/instantclient",
                },
            )

            OracleAdapter().connect(config)

            mock_oracledb.init_oracle_client.assert_called_once_with(
                lib_dir="/opt/oracle/instantclient"
            )

    def test_connect_reports_thick_mode_prerequisites(self):
        mock_oracledb = MagicMock()
        mock_oracledb.init_oracle_client.side_effect = RuntimeError("DPI-1047")

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                options={"oracle_client_mode": "thick"},
            )

            with pytest.raises(
                ValueError, match="Install Oracle Client libraries"
            ) as exc_info:
                OracleAdapter().connect(config)

            assert isinstance(exc_info.value.__cause__, RuntimeError)
            assert "DPI-1047" in str(exc_info.value)
            mock_oracledb.connect.assert_not_called()

    def test_schema_only_shows_library_directory_for_thick_mode(self):
        from sqlit.domains.connections.providers.oracle.schema import SCHEMA

        fields = {field.name: field for field in SCHEMA.fields}

        assert fields["oracle_client_mode"].default == "thin"
        assert [option.value for option in fields["oracle_client_mode"].options] == [
            "thin",
            "thick",
        ]
        visible_when = fields["oracle_client_lib_dir"].visible_when
        assert visible_when is not None
        assert visible_when({"oracle_client_mode": "thin"}) is False
        assert visible_when({"oracle_client_mode": "thick"}) is True

    def test_oracle_legacy_still_defaults_to_thick_mode(self):
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle_legacy.adapter import (
                OracleLegacyAdapter,
            )

            config = ConnectionConfig(
                name="test",
                db_type="oracle_legacy",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
            )

            OracleLegacyAdapter().connect(config)

            mock_oracledb.init_oracle_client.assert_called_once_with()


class TestOracleAdapterRole:
    """Test Oracle adapter handles role/mode parameter correctly."""

    def test_connect_normal_role_no_mode(self):
        """Test that normal role doesn't pass mode parameter."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
                options={"oracle_role": "normal"},
            )

            adapter.connect(config)

            # Verify connect was called without mode parameter
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert "mode" not in call_kwargs
            assert call_kwargs["user"] == "testuser"
            assert call_kwargs["password"] == "testpass"
            assert call_kwargs["dsn"] == "localhost:1521/ORCL"

    def test_connect_sysdba_role_passes_mode(self):
        """Test that sysdba role passes AUTH_MODE_SYSDBA."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="sys",
                password="syspass",
                options={"oracle_role": "sysdba"},
            )

            adapter.connect(config)

            # Verify connect was called with mode=AUTH_MODE_SYSDBA
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["mode"] == 2  # AUTH_MODE_SYSDBA
            assert call_kwargs["user"] == "sys"
            assert call_kwargs["password"] == "syspass"

    def test_connect_sysoper_role_passes_mode(self):
        """Test that sysoper role passes AUTH_MODE_SYSOPER."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="sys",
                password="syspass",
                options={"oracle_role": "sysoper"},
            )

            adapter.connect(config)

            # Verify connect was called with mode=AUTH_MODE_SYSOPER
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["mode"] == 4  # AUTH_MODE_SYSOPER

    def test_connect_default_role_when_not_set(self):
        """Test that missing oracle_role defaults to no mode parameter."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            # Create config without oracle_role (uses default "normal")
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
            )

            adapter.connect(config)

            # Verify connect was called without mode parameter
            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert "mode" not in call_kwargs


class TestOracleAdapterConnectionType:
    """Test Oracle adapter handles connection type (Service Name vs SID) correctly."""

    def test_connect_service_name_format(self):
        """Test that service_name connection type uses slash separator."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="XEPDB1",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "service_name"},
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            # Service name uses slash separator: host:port/service_name
            assert call_kwargs["dsn"] == "localhost:1521/XEPDB1"

    def test_connect_tcps_with_easy_connect_parameters(self):
        """Issue #261: protocol and parameters must be included in the DSN."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="service-name.com",
                username="testuser",
                password="testpass",
                options={
                    "oracle_connection_type": "service_name",
                    "oracle_protocol": "tcps",
                    "oracle_easy_connect_parameters": ("ssl_server_dn_match=no&retry_count=3"),
                },
            )

            adapter.connect(config)

            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["dsn"] == ("tcps://localhost:1521/service-name.com?ssl_server_dn_match=no&retry_count=3")

    def test_connect_easy_connect_parameters_accept_leading_question_mark(self):
        """Users may paste Easy Connect parameters with their separator."""
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="XEPDB1",
                username="testuser",
                password="testpass",
                options={"oracle_easy_connect_parameters": "?expire_time=2"},
            )

            OracleAdapter().connect(config)

            assert mock_oracledb.connect.call_args.kwargs["dsn"] == ("localhost:1521/XEPDB1?expire_time=2")

    def test_connect_rejects_unknown_oracle_protocol(self):
        """Configs outside the schema must not silently discard bad protocols."""
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="XEPDB1",
                username="testuser",
                password="testpass",
                options={"oracle_protocol": "udp"},
            )

            with pytest.raises(ValueError, match="Default, TCP, or TCPS"):
                OracleAdapter().connect(config)

            mock_oracledb.connect.assert_not_called()

    def test_connect_sid_ignores_easy_connect_options(self):
        """Easy Connect protocol and parameters do not apply to SID descriptors."""
        mock_oracledb = MagicMock()

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                username="testuser",
                password="testpass",
                options={
                    "oracle_connection_type": "sid",
                    "oracle_sid": "ORCL",
                    "oracle_protocol": "tcps",
                    "oracle_easy_connect_parameters": "ssl_server_dn_match=no",
                },
            )

            OracleAdapter().connect(config)

            mock_oracledb.makedsn.assert_called_once_with("localhost", 1521, sid="ORCL")
            assert mock_oracledb.connect.call_args.kwargs["dsn"] is (mock_oracledb.makedsn.return_value)

    def test_tcps_easy_connect_dsn_parses_in_real_driver(self):
        """The issue #261 DSN must be accepted by python-oracledb itself."""
        oracledb = pytest.importorskip("oracledb")
        params = oracledb.ConnectParams()

        params.parse_connect_string("tcps://localhost:1521/service-name.com?ssl_server_dn_match=no")

        assert params.protocol == "tcps"
        assert params.host == "localhost"
        assert params.port == 1521
        assert params.service_name == "service-name.com"
        assert params.ssl_server_dn_match is False

    def test_connect_sid_format(self):
        """SID connection type must go through oracledb.makedsn — see issue #106.

        The legacy host:port:SID Easy-Connect form is rejected by thin-mode with
        DPY-4027, so the adapter must use makedsn to emit a TNS descriptor.
        """
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "sid", "oracle_sid": "ORCL"},
            )

            adapter.connect(config)

            mock_oracledb.makedsn.assert_called_once_with("localhost", 1521, sid="ORCL")
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            assert call_kwargs["dsn"] is mock_oracledb.makedsn.return_value

    def test_connect_sid_backward_compat_uses_database_field(self):
        """Test that SID falls back to database field for backward compatibility."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            # Old config style: oracle_sid not set, database used instead
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="LEGACY_SID",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "sid"},
            )

            adapter.connect(config)

            mock_oracledb.makedsn.assert_called_once_with("localhost", 1521, sid="LEGACY_SID")

    def test_connect_default_connection_type_is_service_name(self):
        """Test that missing oracle_connection_type defaults to service_name format."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            # Create config without oracle_connection_type
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="localhost",
                port="1521",
                database="ORCL",
                username="testuser",
                password="testpass",
            )

            adapter.connect(config)

            mock_oracledb.connect.assert_called_once()
            call_kwargs = mock_oracledb.connect.call_args.kwargs
            # Should default to service name format with slash
            assert call_kwargs["dsn"] == "localhost:1521/ORCL"

    def test_connect_sid_with_custom_port(self):
        """Test SID format works with non-default port."""
        mock_oracledb = MagicMock()
        mock_oracledb.AUTH_MODE_SYSDBA = 2
        mock_oracledb.AUTH_MODE_SYSOPER = 4

        with patch.dict("sys.modules", {"oracledb": mock_oracledb}):
            from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

            adapter = OracleAdapter()
            config = ConnectionConfig(
                name="test",
                db_type="oracle",
                server="db.example.com",
                port="1522",
                username="testuser",
                password="testpass",
                options={"oracle_connection_type": "sid", "oracle_sid": "PROD"},
            )

            adapter.connect(config)

            mock_oracledb.makedsn.assert_called_once_with("db.example.com", 1522, sid="PROD")

    def test_sid_dsn_parses_in_real_driver(self):
        """Issue #106 regression: adapter must produce a DSN that thin-mode accepts.

        Calls the adapter against a port that is guaranteed closed so the driver
        is forced to parse the DSN but cannot complete a network connection.
        If parsing fails (DPY-4027), we've regressed.
        """
        oracledb = pytest.importorskip("oracledb")

        from sqlit.domains.connections.providers.oracle.adapter import OracleAdapter

        adapter = OracleAdapter()
        config = ConnectionConfig(
            name="test",
            db_type="oracle",
            server="127.0.0.1",
            port="1",  # reserved port — guaranteed no Oracle listener
            username="x",
            password="x",
            options={"oracle_connection_type": "sid", "oracle_sid": "FREE"},
        )

        with pytest.raises(oracledb.DatabaseError) as exc_info:
            adapter.connect(config)

        message = str(exc_info.value)
        assert "DPY-4027" not in message, f"issue #106 regression: SID DSN rejected at parse step: {message}"
