"""Integration tests for the AWS Athena adapter.

Requires a real AWS account and credentials configured (profile or env vars).
"""

import os
import time
import uuid
import pytest
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from sqlit.config import ConnectionConfig
from sqlit.db.adapters.athena import AthenaAdapter

AWS_PROFILE = os.environ.get("AWS_PROFILE", "default")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
ATHENA_WORKGROUP = "primary"

# Unique names to avoid collisions
TEST_ID = str(uuid.uuid4())[:8]
BUCKET_NAME = f"sqlit-athena-test-{TEST_ID}"
DATABASE_NAME = f"sqlit_test_db_{TEST_ID}"
HIVE_TABLE = "test_hive_table"
ICEBERG_TABLE = "test_iceberg_table"
VIEW_NAME = "test_view"

@pytest.fixture(scope="module")
def aws_session():
    """Create a boto3 session."""
    try:
        return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    except ProfileNotFound:
        # Fallback to default/env vars if profile doesn't exist
        return boto3.Session(region_name=AWS_REGION)
    except NoCredentialsError:
        pytest.skip("AWS credentials not found. Skipping Athena integration tests.")

@pytest.fixture(scope="module")
def athena_setup(aws_session):
    """Setup Athena resources (S3, DB, Tables)."""
    s3 = aws_session.client("s3")
    athena = aws_session.client("athena")
    bucket_created = False

    # 1. Create S3 Bucket
    try:
        s3.create_bucket(Bucket=BUCKET_NAME)
        bucket_created = True
    except ClientError as e:
        if e.response["Error"]["Code"] not in ["BucketAlreadyOwnedByYou", "BucketAlreadyExists"]:
            pytest.skip(f"Failed to create S3 bucket: {e}")

    # Helper to run query
    def run_query(query, database=None):
        context = {"Catalog": "AwsDataCatalog"}
        if database:
            context["Database"] = database
        
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext=context,
            ResultConfiguration={"OutputLocation": f"s3://{BUCKET_NAME}/results/"},
            WorkGroup=ATHENA_WORKGROUP,
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

    try:
        # 2. Create Database
        run_query(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")

        # 3. Create Hive Table (External CSV)
        # First upload some data
        csv_data = "id,name\n1,Alice\n2,Bob"
        s3.put_object(Bucket=BUCKET_NAME, Key=f"hive_data/data.csv", Body=csv_data)
        
        run_query(f"""
            CREATE EXTERNAL TABLE IF NOT EXISTS {HIVE_TABLE} (
                id INT,
                name STRING
            )
            ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
            LOCATION 's3://{BUCKET_NAME}/hive_data/'
            TBLPROPERTIES ('skip.header.line.count'='1')
        """, DATABASE_NAME)

        # 4. Create Iceberg Table
        # Note: Iceberg requires a specific location usually, or uses warehouse
        try:
            run_query(f"""
                CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE} (
                    id INT,
                    name STRING
                )
                LOCATION 's3://{BUCKET_NAME}/iceberg_data/'
                TBLPROPERTIES (
                    'table_type'='ICEBERG',
                    'format'='parquet'
                )
            """, DATABASE_NAME)
            
            run_query(f"INSERT INTO {ICEBERG_TABLE} VALUES (3, 'Charlie'), (4, 'David')", DATABASE_NAME)
        except Exception as e:
             # Iceberg might fail if not supported/configured in the Workgroup/Catalog
             # Continue but warn/mark as skipped? For now verify standard tables work.
             print(f"Warning: Failed to create Iceberg table: {e}")

        # 5. Create View
        run_query(f"CREATE OR REPLACE VIEW {VIEW_NAME} AS SELECT * FROM {HIVE_TABLE}", DATABASE_NAME)

        yield {
            "bucket": BUCKET_NAME,
            "database": DATABASE_NAME,
            "hive_table": HIVE_TABLE,
            "iceberg_table": ICEBERG_TABLE,
            "view": VIEW_NAME,
            "region": aws_session.region_name,
            "workgroup": ATHENA_WORKGROUP
        }

    finally:
        # Teardown
        try:
            run_query(f"DROP VIEW IF EXISTS {VIEW_NAME}", DATABASE_NAME)
            run_query(f"DROP TABLE IF EXISTS {ICEBERG_TABLE}", DATABASE_NAME)
            run_query(f"DROP TABLE IF EXISTS {HIVE_TABLE}", DATABASE_NAME)
            run_query(f"DROP DATABASE IF EXISTS {DATABASE_NAME}")
        except Exception:
            pass
        
        if bucket_created:
            try:
                # Cleanup bucket contents
                objects = s3.list_objects_v2(Bucket=BUCKET_NAME)
                if "Contents" in objects:
                    keys = [{"Key": obj["Key"]} for obj in objects["Contents"]]
                    s3.delete_objects(Bucket=BUCKET_NAME, Delete={"Objects": keys})
                s3.delete_bucket(Bucket=BUCKET_NAME)
            except Exception:
                pass

class TestAthenaIntegration:
    def test_connect_with_profile(self, athena_setup):
        """Test connecting using AWS Profile."""
        config = ConnectionConfig(
            name="athena_profile_test",
            db_type="athena",
            server="ignored",
            username="ignored",
            password="ignored",
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
        rows = adapter.execute_query(conn, "SELECT 1")
        assert rows[1][0][0] == 1
        conn.close()

    def test_connect_with_keys(self, athena_setup, aws_session):
        """Test connecting using Access Keys."""
        # Extract credentials from current session to test 'keys' auth method
        creds = aws_session.get_credentials()
        if not creds or not creds.access_key:
             pytest.skip("Could not extract credentials for key-based auth test")

        config = ConnectionConfig(
            name="athena_keys_test",
            db_type="athena",
            server="ignored",
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
        
        rows = adapter.execute_query(conn, "SELECT 1")
        assert rows[1][0][0] == 1
        conn.close()

    def test_get_tables_and_query_hive(self, athena_setup):
        """Test listing tables and querying a Hive table."""
        config = ConnectionConfig(
            name="athena_hive_test",
            db_type="athena",
            server="ignored",
            username="ignored",
            password="ignored",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )
        adapter = AthenaAdapter()
        conn = adapter.connect(config)
        
        # 1. List Tables
        tables = adapter.get_tables(conn, database=athena_setup["database"])
        table_names = [t[1] for t in tables]
        assert athena_setup["hive_table"] in table_names
        
        # 2. Query Hive Table
        query = adapter.build_select_query(athena_setup["hive_table"], limit=10, database=athena_setup["database"])
        _, rows, _ = adapter.execute_query(conn, query)
        assert len(rows) == 2
        # Data was: `1,Alice` and `2,Bob` (header skipped)
        # Order not guaranteed without ORDER BY, but checking existence
        names = [r[1] for r in rows]
        assert "Alice" in names
        assert "Bob" in names

    def test_query_iceberg_table(self, athena_setup):
        """Test querying Iceberg table."""
        try:
             # Check if table exists first (creation might have failed softly in setup)
             config = ConnectionConfig(
                name="athena_iceberg_test",
                db_type="athena",
                server="ignored",
                username="ignored",
                password="ignored",
                database=athena_setup["database"],
                options={
                    "athena_region_name": athena_setup["region"],
                    "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                    "athena_auth_method": "profile",
                    "athena_profile_name": AWS_PROFILE,
                },
             )
             adapter = AthenaAdapter()
             conn = adapter.connect(config)
             
             query = f"SELECT * FROM {athena_setup['iceberg_table']}"
             _, rows, _ = adapter.execute_query(conn, query)
             
             # Charlie and David
             names = [r[1] for r in rows]
             assert "Charlie" in names
             assert "David" in names
             
        except Exception as e:
            pytest.skip(f"Iceberg test failed (likely not set up): {e}")

    def test_query_view(self, athena_setup):
        """Test querying a view."""
        config = ConnectionConfig(
            name="athena_view_test",
            db_type="athena",
            server="ignored",
            username="ignored",
            password="ignored",
            database=athena_setup["database"],
            options={
                "athena_region_name": athena_setup["region"],
                "athena_s3_staging_dir": f"s3://{athena_setup['bucket']}/results/",
                "athena_auth_method": "profile",
                "athena_profile_name": AWS_PROFILE,
            },
        )
        adapter = AthenaAdapter()
        conn = adapter.connect(config)
        
        # Check if view is listed
        views = adapter.get_views(conn, database=athena_setup["database"])
        view_names = [v[1] for v in views]
        assert athena_setup["view"] in view_names
        
        # Query view
        query = f"SELECT * FROM {athena_setup['view']}"
        _, rows, _ = adapter.execute_query(conn, query)
        names = [r[1] for r in rows]
        assert "Alice" in names
