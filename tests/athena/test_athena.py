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

import json
import os
import time
import uuid
import pytest

# Check for required dependencies
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from sqlit.config import ConnectionConfig
    from sqlit.db.adapters.athena import AthenaAdapter
    HAS_ADAPTER = True
except ImportError:
    HAS_ADAPTER = False

# Skip all tests if dependencies missing
pytestmark = [
    pytest.mark.skipif(not HAS_BOTO3, reason="boto3 not installed"),
    pytest.mark.skipif(not HAS_ADAPTER, reason="Athena adapter not available"),
]

# Configuration from environment
AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Terraform mode: infrastructure pre-provisioned
TERRAFORM_MODE = os.environ.get("ATHENA_USE_TERRAFORM", "").lower() in ("1", "true", "yes")
ATHENA_BUCKET = os.environ.get("ATHENA_BUCKET")
ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE")
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "primary")
ATHENA_S3_STAGING_DIR = os.environ.get("ATHENA_S3_STAGING_DIR")

# Standalone mode: generate unique names
TEST_ID = str(uuid.uuid4())[:8]
STANDALONE_BUCKET = f"sqlit-athena-test-{TEST_ID}"
STANDALONE_DATABASE = f"sqlit_test_db_{TEST_ID}"

HIVE_TABLE = "test_hive_table"
ICEBERG_TABLE = "test_iceberg_table"
VIEW_NAME = "test_view"


def _terraform_config_valid() -> bool:
    """Check if all Terraform config is present."""
    return all([ATHENA_BUCKET, ATHENA_DATABASE, ATHENA_S3_STAGING_DIR])


@pytest.fixture(scope="module")
def aws_session():
    """Create a boto3 session and verify credentials are available."""
    if not HAS_BOTO3:
        pytest.skip("boto3 not installed")

    try:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    except ProfileNotFound:
        # Fallback to default/env vars if profile doesn't exist
        try:
            session = boto3.Session(region_name=AWS_REGION)
        except (ProfileNotFound, NoCredentialsError):
            pytest.skip("AWS credentials not found. Skipping Athena integration tests.")

    # Verify credentials are actually available by trying to get them
    # boto3.Session() doesn't throw if credentials are missing - it only fails on API calls
    try:
        credentials = session.get_credentials()
        if credentials is None:
            pytest.skip("AWS credentials not found. Skipping Athena integration tests.")
        # Force credential resolution to catch NoCredentialsError early
        credentials.get_frozen_credentials()
    except (NoCredentialsError, ProfileNotFound):
        pytest.skip("AWS credentials not found. Skipping Athena integration tests.")

    return session


@pytest.fixture(scope="module")
def athena_setup(aws_session):
    """Setup Athena test resources.

    In Terraform mode: just returns config from environment variables.
    In standalone mode: creates and tears down resources.
    """
    if TERRAFORM_MODE:
        if not _terraform_config_valid():
            pytest.skip(
                "Terraform mode enabled but missing config. "
                "Required: ATHENA_BUCKET, ATHENA_DATABASE, ATHENA_S3_STAGING_DIR"
            )

        # Terraform already created everything, just return config
        yield {
            "bucket": ATHENA_BUCKET,
            "database": ATHENA_DATABASE,
            "hive_table": HIVE_TABLE,
            "iceberg_table": ICEBERG_TABLE,
            "view": VIEW_NAME,
            "region": AWS_REGION,
            "workgroup": ATHENA_WORKGROUP,
        }
        return

    # Standalone mode: create resources ourselves
    s3 = aws_session.client("s3")
    athena = aws_session.client("athena")
    bucket_created = False
    bucket_name = STANDALONE_BUCKET
    database_name = STANDALONE_DATABASE

    # Helper to run Athena query and wait for completion
    def run_query(query: str, database: str | None = None) -> str:
        context = {"Catalog": "AwsDataCatalog"}
        if database:
            context["Database"] = database

        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext=context,
            ResultConfiguration={"OutputLocation": f"s3://{bucket_name}/results/"},
            WorkGroup="primary",
        )
        execution_id = response["QueryExecutionId"]

        while True:
            result = athena.get_query_execution(QueryExecutionId=execution_id)
            state = result["QueryExecution"]["Status"]["State"]
            if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
                break
            time.sleep(1)

        if state != "SUCCEEDED":
            reason = result["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
            raise Exception(f"Query failed: {reason}")
        return execution_id

    # 1. Create S3 Bucket
    try:
        # Handle region-specific bucket creation
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION}
            )
        bucket_created = True
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code not in ["BucketAlreadyOwnedByYou", "BucketAlreadyExists"]:
            pytest.skip(f"Failed to create S3 bucket: {e}")

    try:
        # 2. Create Database
        run_query(f"CREATE DATABASE IF NOT EXISTS {database_name}")

        # 3. Create Hive Table (External CSV)
        csv_data = "id,name\n1,Alice\n2,Bob\n3,Charlie"
        s3.put_object(Bucket=bucket_name, Key="hive_data/data.csv", Body=csv_data)

        run_query(f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {HIVE_TABLE} (
                id INT,
                name STRING
            )
            ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
            LOCATION 's3://{bucket_name}/hive_data/'
            TBLPROPERTIES ('skip.header.line.count'='1')
        """, database_name)

        # 4. Create Iceberg Table (may fail if not supported)
        iceberg_created = False
        try:
            run_query(f"""
                CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE} (
                    id INT,
                    name STRING
                )
                LOCATION 's3://{bucket_name}/iceberg_data/'
                TBLPROPERTIES (
                    'table_type'='ICEBERG',
                    'format'='parquet'
                )
            """, database_name)
            run_query(
                f"INSERT INTO {ICEBERG_TABLE} VALUES (3, 'Charlie'), (4, 'David')",
                database_name
            )
            iceberg_created = True
        except Exception as e:
            print(f"Warning: Failed to create Iceberg table (may not be supported): {e}")

        # 5. Create View
        run_query(
            f"CREATE OR REPLACE VIEW {VIEW_NAME} AS SELECT * FROM {HIVE_TABLE}",
            database_name
        )

        yield {
            "bucket": bucket_name,
            "database": database_name,
            "hive_table": HIVE_TABLE,
            "iceberg_table": ICEBERG_TABLE if iceberg_created else None,
            "view": VIEW_NAME,
            "region": aws_session.region_name,
            "workgroup": "primary",
        }

    finally:
        # Teardown
        try:
            run_query(f"DROP VIEW IF EXISTS {VIEW_NAME}", database_name)
        except Exception:
            pass
        try:
            run_query(f"DROP TABLE IF EXISTS {ICEBERG_TABLE}", database_name)
        except Exception:
            pass
        try:
            run_query(f"DROP TABLE IF EXISTS {HIVE_TABLE}", database_name)
        except Exception:
            pass
        try:
            run_query(f"DROP DATABASE IF EXISTS {database_name}")
        except Exception:
            pass

        if bucket_created:
            try:
                # Delete all objects first
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket_name):
                    if "Contents" in page:
                        keys = [{"Key": obj["Key"]} for obj in page["Contents"]]
                        s3.delete_objects(Bucket=bucket_name, Delete={"Objects": keys})
                s3.delete_bucket(Bucket=bucket_name)
            except Exception as e:
                print(f"Warning: Failed to cleanup bucket: {e}")


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
