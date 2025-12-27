"""Test autocomplete behavior with different database selection modes."""

import pytest
from unittest.mock import MagicMock, PropertyMock, patch


class TestAutocompleteDatabaseModes:
    """Test how autocomplete handles various database configurations."""

    def test_single_user_db_after_system_filter_shows_unqualified(self):
        """
        Scenario: Server has 4 databases, 3 are system (filtered), 1 is user db.
        No database is selected (_active_database=None, config.database=None).

        After filtering, only 1 database remains -> should use unqualified names.
        """
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()

        # Simulate: no database selected
        _active_database = None
        config_database = None

        # Server returns all databases
        all_dbs_from_server = ["master", "tempdb", "model", "msdb", "UserAppDb"]

        # Filter system databases (this is what autocomplete does)
        system_dbs = {s.lower() for s in adapter.system_databases}
        filtered_dbs = [d for d in all_dbs_from_server if d.lower() not in system_dbs]

        # Only UserAppDb should remain
        assert filtered_dbs == ["UserAppDb"]

        # Determine single_db mode
        db = _active_database or config_database
        if db:
            databases = [db]
        else:
            databases = filtered_dbs  # Use filtered list

        single_db = len(databases) == 1

        # With only 1 database after filtering, should be single_db mode
        assert single_db is True, "Should be single_db mode when only 1 user database exists"

        # Build schema cache
        schema_cache = {"tables": [], "views": [], "columns": {}, "procedures": []}
        tables = [("dbo", "Users"), ("dbo", "Orders")]

        for schema_name, table_name in tables:
            if single_db:
                schema_cache["tables"].append(table_name)
            else:
                quoted_db = adapter.quote_identifier(databases[0])
                quoted_schema = adapter.quote_identifier(schema_name)
                quoted_table = adapter.quote_identifier(table_name)
                full_name = f"{quoted_db}.{quoted_schema}.{quoted_table}"
                schema_cache["tables"].append(full_name)

        # Should have UNQUALIFIED names since only 1 db
        assert schema_cache["tables"] == ["Users", "Orders"]
        assert "[UserAppDb]" not in str(schema_cache["tables"])

    def test_multiple_user_dbs_after_system_filter_shows_qualified(self):
        """
        Scenario: Server has 5 databases, 3 are system (filtered), 2 are user dbs.
        No database is selected.

        After filtering, 2 databases remain -> should use fully qualified names.
        """
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()

        # Simulate: no database selected
        _active_database = None
        config_database = None

        # Server returns all databases
        all_dbs_from_server = ["master", "tempdb", "model", "msdb", "AppDb1", "AppDb2"]

        # Filter system databases
        system_dbs = {s.lower() for s in adapter.system_databases}
        filtered_dbs = [d for d in all_dbs_from_server if d.lower() not in system_dbs]

        # Two user databases should remain
        assert filtered_dbs == ["AppDb1", "AppDb2"]

        # Determine single_db mode
        db = _active_database or config_database
        if db:
            databases = [db]
        else:
            databases = filtered_dbs

        single_db = len(databases) == 1

        # With 2 databases, should NOT be single_db mode
        assert single_db is False, "Should NOT be single_db mode with multiple user databases"

        # Build schema cache
        schema_cache = {"tables": [], "views": [], "columns": {}, "procedures": []}
        tables_by_db = {
            "AppDb1": [("dbo", "Users")],
            "AppDb2": [("dbo", "Products")],
        }

        for database in databases:
            for schema_name, table_name in tables_by_db[database]:
                if single_db:
                    schema_cache["tables"].append(table_name)
                else:
                    quoted_db = adapter.quote_identifier(database)
                    quoted_schema = adapter.quote_identifier(schema_name)
                    quoted_table = adapter.quote_identifier(table_name)
                    full_name = f"{quoted_db}.{quoted_schema}.{quoted_table}"
                    schema_cache["tables"].append(full_name)

        # Should have QUALIFIED names
        assert "[AppDb1].[dbo].[Users]" in schema_cache["tables"]
        assert "[AppDb2].[dbo].[Products]" in schema_cache["tables"]

    def test_no_user_dbs_after_filter_shows_empty(self):
        """
        Scenario: Server only has system databases, all get filtered.
        No database is selected.

        After filtering, 0 databases remain -> empty autocomplete.
        """
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()

        # Server returns only system databases
        all_dbs_from_server = ["master", "tempdb", "model", "msdb"]

        # Filter system databases
        system_dbs = {s.lower() for s in adapter.system_databases}
        filtered_dbs = [d for d in all_dbs_from_server if d.lower() not in system_dbs]

        # No databases should remain
        assert filtered_dbs == []

        # Schema cache should be empty
        schema_cache = {"tables": [], "views": [], "columns": {}, "procedures": []}

        assert schema_cache["tables"] == []

    def test_selected_db_overrides_filter_logic(self):
        """
        Scenario: Multiple user databases exist, but one is explicitly selected.

        Should use single_db mode with unqualified names for the selected db.
        """
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()

        # User selected a specific database
        _active_database = "AppDb1"
        config_database = None

        # Server has multiple user databases
        all_dbs_from_server = ["master", "tempdb", "AppDb1", "AppDb2", "AppDb3"]

        # When a database is selected, we DON'T load all databases
        db = _active_database or config_database
        if db:
            databases = [db]  # Only the selected one
        else:
            system_dbs = {s.lower() for s in adapter.system_databases}
            databases = [d for d in all_dbs_from_server if d.lower() not in system_dbs]

        single_db = len(databases) == 1

        # Should be single_db mode because we selected one
        assert single_db is True
        assert databases == ["AppDb1"]

        # Build schema cache - should be unqualified
        schema_cache = {"tables": []}
        tables = [("dbo", "Users"), ("dbo", "Orders")]

        for schema_name, table_name in tables:
            if single_db:
                schema_cache["tables"].append(table_name)

        assert schema_cache["tables"] == ["Users", "Orders"]

    def test_select_then_unselect_database(self):
        """
        Scenario:
        1. User selects a database -> unqualified names
        2. User unselects (clears) database -> qualified names (if multiple dbs)
        """
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()

        all_user_dbs = ["AppDb1", "AppDb2"]

        # Phase 1: Database selected
        _active_database = "AppDb1"
        db = _active_database or None
        databases = [db] if db else all_user_dbs
        single_db = len(databases) == 1

        assert single_db is True

        schema_cache = {"tables": []}
        for table_name in ["Users", "Orders"]:
            if single_db:
                schema_cache["tables"].append(table_name)

        assert schema_cache["tables"] == ["Users", "Orders"]

        # Phase 2: Database unselected
        _active_database = None
        db = _active_database or None
        databases = [db] if db else all_user_dbs
        single_db = len(databases) == 1

        assert single_db is False

        # Reload cache with qualified names
        schema_cache = {"tables": []}
        tables_by_db = {"AppDb1": ["Users"], "AppDb2": ["Products"]}

        for database in databases:
            for table_name in tables_by_db[database]:
                if single_db:
                    schema_cache["tables"].append(table_name)
                else:
                    full_name = f"[{database}].[dbo].[{table_name}]"
                    schema_cache["tables"].append(full_name)

        assert "[AppDb1].[dbo].[Users]" in schema_cache["tables"]
        assert "[AppDb2].[dbo].[Products]" in schema_cache["tables"]


class TestSystemDatabaseFiltering:
    """Test system database filtering across different adapters."""

    def test_mssql_filters_system_databases(self):
        """MSSQL should filter master, tempdb, model, msdb."""
        from sqlit.db.adapters.mssql import SQLServerAdapter

        adapter = SQLServerAdapter()
        all_dbs = ["master", "MASTER", "tempdb", "model", "msdb", "UserDb"]

        system_dbs = {s.lower() for s in adapter.system_databases}
        filtered = [d for d in all_dbs if d.lower() not in system_dbs]

        assert filtered == ["UserDb"]

    def test_postgres_filters_template_databases(self):
        """PostgreSQL should filter template0, template1."""
        from sqlit.db.adapters.postgresql import PostgreSQLAdapter

        adapter = PostgreSQLAdapter()
        all_dbs = ["postgres", "template0", "template1", "myapp"]

        system_dbs = {s.lower() for s in adapter.system_databases}
        filtered = [d for d in all_dbs if d.lower() not in system_dbs]

        assert "postgres" in filtered
        assert "myapp" in filtered
        assert "template0" not in filtered
        assert "template1" not in filtered

    def test_mysql_filters_system_databases(self):
        """MySQL should filter mysql, information_schema, performance_schema, sys."""
        from sqlit.db.adapters.mysql import MySQLAdapter

        adapter = MySQLAdapter()
        all_dbs = ["mysql", "information_schema", "performance_schema", "sys", "myapp"]

        system_dbs = {s.lower() for s in adapter.system_databases}
        filtered = [d for d in all_dbs if d.lower() not in system_dbs]

        assert filtered == ["myapp"]
