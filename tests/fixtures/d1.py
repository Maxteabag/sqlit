"""D1 fixtures."""

from __future__ import annotations

import json
import os
import time
from urllib import error, request

import pytest

from tests.fixtures.utils import cleanup_connection, is_port_open, run_cli

# D1 connection settings for Docker (miniflare)
D1_HOST = os.environ.get("D1_HOST", "localhost")
D1_PORT = int(os.environ.get("D1_PORT", "8787"))
D1_ACCOUNT_ID = "test-account"
D1_DATABASE = "test-d1"
D1_API_TOKEN = "test-token"
os.environ["D1_API_BASE_URL"] = f"http://{D1_HOST}:{D1_PORT}"


class _D1Client:
    """Minimal D1 client using the local miniflare worker endpoints."""

    def __init__(self, account_id: str, api_token: str) -> None:
        self._account_id = account_id
        self._api_token = api_token
        self._base_url = os.environ.get("D1_API_BASE_URL", f"http://{D1_HOST}:{D1_PORT}")

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=10) as resp:
                body = resp.read()
        except error.HTTPError as exc:
            body = exc.read()
            try:
                payload = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                raise RuntimeError(f"D1 API error {exc.code}: {body.decode('utf-8', 'ignore')}") from exc
            raise RuntimeError(payload.get("errors") or payload) from exc
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    def list_databases(self) -> list[dict]:
        data = self._request("GET", f"/client/v4/accounts/{self._account_id}/d1/database")
        return data.get("result", [])

    def create_database(self, name: str) -> None:
        results = self.list_databases()
        if not any(db.get("name") == name for db in results):
            raise RuntimeError(f"D1 database '{name}' not found in miniflare")

    def execute(self, db_name: str, sql: str) -> dict | None:
        payload = self._request(
            "POST",
            f"/client/v4/accounts/{self._account_id}/d1/database/{db_name}/execute",
            {"sql": sql},
        )
        if not payload.get("success", False):
            errors = payload.get("errors") or []
            message = errors[0].get("message") if errors else "D1 execute failed"
            raise RuntimeError(message)
        return payload.get("result")


def d1_available() -> bool:
    """Check if D1 (miniflare) is available."""
    return is_port_open(D1_HOST, D1_PORT)


@pytest.fixture(scope="session")
def d1_server_ready() -> bool:
    """Check if D1 is ready and return True/False."""
    if not d1_available():
        return False
    client = _D1Client(D1_ACCOUNT_ID, D1_API_TOKEN)
    for _ in range(10):
        try:
            client.list_databases()
            return True
        except Exception:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="function")
def d1_db(d1_server_ready: bool) -> str:
    """Set up D1 test database."""
    if not d1_server_ready:
        pytest.skip("D1 is not available")

    try:
        # Use local D1 API endpoints to set up test data
        client = _D1Client(D1_ACCOUNT_ID, D1_API_TOKEN)

        # Create the database if it doesn't exist
        client.create_database(D1_DATABASE)

        # Start from a clean schema to keep tests idempotent.
        client.execute(D1_DATABASE, "DROP VIEW IF EXISTS test_user_emails")
        client.execute(D1_DATABASE, "DROP TRIGGER IF EXISTS trg_test_users_audit")
        client.execute(D1_DATABASE, "DROP INDEX IF EXISTS idx_test_users_email")
        client.execute(D1_DATABASE, "DROP TABLE IF EXISTS test_products")
        client.execute(D1_DATABASE, "DROP TABLE IF EXISTS test_users")

        # Create tables and insert data
        client.execute(
            D1_DATABASE,
            """
            CREATE TABLE IF NOT EXISTS test_users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            )
            """,
        )

        client.execute(
            D1_DATABASE,
            """
            CREATE TABLE IF NOT EXISTS test_products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER DEFAULT 0
            )
            """,
        )

        client.execute(
            D1_DATABASE,
            """
            CREATE VIEW IF NOT EXISTS test_user_emails AS
            SELECT id, name, email FROM test_users WHERE email IS NOT NULL
            """,
        )

        # Create test index for integration tests
        client.execute(
            D1_DATABASE,
            "CREATE INDEX IF NOT EXISTS idx_test_users_email ON test_users(email)",
        )

        # Create test trigger for integration tests
        client.execute(
            D1_DATABASE,
            """
            CREATE TRIGGER IF NOT EXISTS trg_test_users_audit
            AFTER INSERT ON test_users
            BEGIN
                SELECT 1;
            END
            """,
        )

        client.execute(
            D1_DATABASE,
            """
            INSERT INTO test_users (id, name, email) VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com'),
            (3, 'Charlie', 'charlie@example.com')
            """,
        )

        client.execute(
            D1_DATABASE,
            """
            INSERT INTO test_products (id, name, price, stock) VALUES
            (1, 'Widget', 9.99, 100),
            (2, 'Gadget', 19.99, 50),
            (3, 'Gizmo', 29.99, 25)
            """,
        )

    except Exception as e:
        pytest.skip(f"Failed to setup D1 database: {e}")

    yield D1_DATABASE


@pytest.fixture(scope="function")
def d1_connection(d1_db: str) -> str:
    """Create a sqlit CLI connection for D1 and clean up after test."""
    connection_name = f"test_d1_{os.getpid()}"
    cleanup_connection(connection_name)

    run_cli(
        "connections",
        "add",
        "d1",
        "--name",
        connection_name,
        "--host",
        D1_ACCOUNT_ID,
        "--password",
        D1_API_TOKEN,
        "--database",
        d1_db,
    )

    yield connection_name
    cleanup_connection(connection_name)


__all__ = [
    "D1_ACCOUNT_ID",
    "D1_API_TOKEN",
    "D1_DATABASE",
    "D1_HOST",
    "D1_PORT",
    "d1_available",
    "d1_connection",
    "d1_db",
    "d1_server_ready",
]
