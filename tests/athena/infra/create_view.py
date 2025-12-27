#!/usr/bin/env python3
"""Create Athena view using boto3.

Usage:
    python create_view.py <database> <workgroup> <s3_staging_dir> <region>
"""

import sys
import time
import boto3


def create_view(database: str, workgroup: str, s3_staging_dir: str, region: str) -> None:
    """Create test_view in Athena."""
    athena = boto3.client("athena", region_name=region)

    query = f"CREATE OR REPLACE VIEW test_view AS SELECT * FROM {database}.test_hive_table"

    # Start query
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": s3_staging_dir},
    )
    execution_id = response["QueryExecutionId"]

    # Wait for completion
    while True:
        result = athena.get_query_execution(QueryExecutionId=execution_id)
        state = result["QueryExecution"]["Status"]["State"]

        if state == "SUCCEEDED":
            print(f"View created successfully (execution_id={execution_id})")
            return
        elif state in ("FAILED", "CANCELLED"):
            reason = result["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
            print(f"Failed to create view: {reason}", file=sys.stderr)
            sys.exit(1)

        time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <database> <workgroup> <s3_staging_dir> <region>", file=sys.stderr)
        sys.exit(1)

    create_view(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
