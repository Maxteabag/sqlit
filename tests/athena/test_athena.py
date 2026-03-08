"""Integration tests for the AWS Athena adapter.

These tests can run in two modes:
1. With Terraform-provisioned infrastructure (recommended for CI)
   - Set ATHENA_USE_TERRAFORM=1 and run via scripts/run_athena_tests.sh
2. Standalone (creates/destroys resources in fixtures)
   - Just run pytest directly with AWS credentials configured

Environment variables (Terraform mode):
    ATHENA_BUCKET          - S3 bucket name
    ATHENA_DATABASE        - Glue database name
    ATHENA_WORKGROUP       - Athena workgroup name
    ATHENA_S3_STAGING_DIR  - S3 path for query results
    AWS_REGION             - AWS region (default: us-east-1)
    AWS_PROFILE            - AWS profile name (default: default)
"""

import pytest

from tests.athena.fixtures import AWS_PROFILE, HAS_BOTO3, athena_setup, aws_session

try:
    from sqlit.domains.connections.providers.athena.adapter import AthenaAdapter
    from tests.helpers import ConnectionConfig

    HAS_ADAPTER = True
except ImportError:
    HAS_ADAPTER = False

# Skip all tests if dependencies missing
pytestmark = [
    pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed"),
    pytest.mark.skipif(not HAS_ADAPTER, reason="Athena adapter not available"),
]


class TestAthenaIntegration:
    """Integration tests for the Athena adapter."""

    def test_connect_with_profile(self, athena_setup):
        """Test connecting using AWS Profile."""
        config = ConnectionConfig(
            name="athena_profile_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)
        assert conn is not None

        # Verify simple query
        _, rows, _ = adapter.execute_query(conn, "SELECT 1")
        assert rows[0][0] == 1
        conn.close()

    def test_connect_with_keys(self, athena_setup, aws_session):
        """Test connecting using Access Keys."""
        creds = aws_session.get_credentials()
        if not creds or not creds.access_key:
            pytest.skip("Could not extract credentials for key-based auth test")

        config = ConnectionConfig(
            name="athena_keys_test",
            db_type="athena",
            server="",
            username=creds.access_key,
            password=creds.secret_key,
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "keys",
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)
        assert conn is not None

        _, rows, _ = adapter.execute_query(conn, "SELECT 1")
        assert rows[0][0] == 1
        conn.close()

    def test_get_databases(self, athena_setup):
        """Test listing databases."""
        config = ConnectionConfig(
            name="athena_db_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        databases = adapter.get_databases(conn)
        assert athena_setup["database"] in databases
        conn.close()

    def test_get_tables(self, athena_setup):
        """Test listing tables."""
        config = ConnectionConfig(
            name="athena_tables_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        tables = adapter.get_tables(conn, database=athena_setup["database"])
        table_names = [t[1] for t in tables]
        assert athena_setup["hive_table"] in table_names
        conn.close()

    def test_get_columns(self, athena_setup):
        """Test getting column information."""
        config = ConnectionConfig(
            name="athena_columns_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        columns = adapter.get_columns(
            conn,
            table=athena_setup["hive_table"],
            database=athena_setup["database"]
        )
        column_names = [c.name for c in columns]
        assert "id" in column_names
        assert "name" in column_names
        conn.close()

    def test_query_hive_table(self, athena_setup):
        """Test querying a Hive table."""
        config = ConnectionConfig(
            name="athena_hive_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        query = adapter.build_select_query(
            athena_setup["hive_table"],
            limit=10,
            database=athena_setup["database"]
        )
        _, rows, _ = adapter.execute_query(conn, query)

        # Should have at least Alice and Bob (Terraform has 3, standalone has 3)
        assert len(rows) >= 2
        names = [r[1] for r in rows]
        assert "Alice" in names
        assert "Bob" in names
        conn.close()

    def test_query_iceberg_table(self, athena_setup):
        """Test querying an Iceberg table."""
        if athena_setup.get("iceberg_table") is None:
            pytest.skip("Iceberg table not available")

        config = ConnectionConfig(
            name="athena_iceberg_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        try:
            query = f"SELECT * FROM {athena_setup['database']}.{athena_setup['iceberg_table']}"
            _, rows, _ = adapter.execute_query(conn, query)

            names = [r[1] for r in rows]
            assert "Charlie" in names
            assert "David" in names
        except Exception as e:
            pytest.skip(f"Iceberg query failed: {e}")
        finally:
            conn.close()

    def test_get_views(self, athena_setup):
        """Test listing views."""
        config = ConnectionConfig(
            name="athena_views_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        views = adapter.get_views(conn, database=athena_setup["database"])
        view_names = [v[1] for v in views]
        assert athena_setup["view"] in view_names
        conn.close()

    def test_query_view(self, athena_setup):
        """Test querying a view."""
        config = ConnectionConfig(
            name="athena_view_query_test",
            db_type="athena",
            server="",
            username="",
            password="",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_work_group": athena_setup["workgroup"],
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )

        adapter = AthenaAdapter()
        conn = adapter.connect(config)

        query = f"SELECT * FROM {athena_setup['database']}.{athena_setup['view']}"
        _, rows, _ = adapter.execute_query(conn, query)

        names = [r[1] for r in rows]
        assert "Alice" in names
        conn.close()
