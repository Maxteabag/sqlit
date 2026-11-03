"""Disposable integration databases. Never targets an existing database server."""

from __future__ import annotations

import json
import secrets
import sqlite3
import subprocess
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.catalog import get_provider


@dataclass(repr=False)
class ProviderCase:
    name: str
    config: ConnectionConfig
    provider: Any
    connection: Any
    database: str | None
    billing: str
    analytics: str
    empty: str
    evidence: str
    expected_rows: dict[str, list[tuple]]

    @property
    def adapter(self):
        return self.provider.connection_factory


def sql(conn, statement):
    cursor = conn.cursor()
    try:
        cursor.execute(statement)
    finally:
        cursor.close()


def seed(case):
    adapter = case.adapter
    q = adapter.quote_identifier
    schemas = [""] if case.name == "sqlite" else [case.billing, case.analytics]
    if case.name != "sqlite":
        for schema in [*schemas, case.empty]:
            sql(case.connection, f"CREATE SCHEMA {q(schema)}")
    for schema in schemas:
        qualified = (q(schema) + ".") if schema else ""
        table = qualified + q("orders")
        sql(case.connection, f"CREATE TABLE {table} ({q('id')} INTEGER PRIMARY KEY, {q('customer')} VARCHAR(80), {q('total')} DECIMAL(10,2))")
        rows = case.expected_rows[schema]
        for ident, customer, total in rows:
            sql(case.connection, f"INSERT INTO {table} VALUES ({ident}, '{customer}', {total})")
        sql(case.connection, f"CREATE VIEW {qualified}{q('open_orders')} AS SELECT * FROM {table}")
        if case.name in {"postgresql", "supabase", "mssql"}:
            column = "customer" if schema == case.billing else "total"
            sql(case.connection, f"CREATE INDEX {q('orders_lookup')} ON {table} ({q(column)})")
            start = 10000 if schema == case.billing else 90000
            sql(case.connection, f"CREATE SEQUENCE {qualified}{q('invoice_number')} START WITH {start}")
            if case.name in {"postgresql", "supabase"}:
                sql(case.connection, f"CREATE FUNCTION {qualified}audit_fn() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$")
                sql(case.connection, f"CREATE TRIGGER orders_audit BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION {qualified}audit_fn()")
                sql(case.connection, f"CREATE PROCEDURE {qualified}close_month() LANGUAGE plpgsql AS $$ BEGIN NULL; END $$")
            else:
                sql(case.connection, f"CREATE TRIGGER {qualified}orders_audit ON {table} AFTER INSERT AS BEGIN SET NOCOUNT ON; END")
                sql(case.connection, f"CREATE PROCEDURE {qualified}close_month AS BEGIN SET NOCOUNT ON; END")


@contextmanager
def docker_database(name, root):
    container = f"sqlit-schema-{name}-{secrets.token_hex(4)}"
    password = "Sqlit-" + secrets.token_hex(12) + "!9"
    env_file = root / f"{name}.env"
    env_file.write_text("POSTGRES_PASSWORD=" + password + "\nPOSTGRES_DB=sqlit_schema_it\n" if name == "postgresql" else "MSSQL_SA_PASSWORD=" + password + "\nACCEPT_EULA=Y\n")
    env_file.chmod(0o600)
    image = "postgres:16-alpine" if name == "postgresql" else "mcr.microsoft.com/mssql/server:2022-latest"
    internal = 5432 if name == "postgresql" else 1433
    started = False
    connection = None
    try:
        subprocess.run(["docker", "run", "-d", "--name", container, "--cpus=2", "--memory=" + ("512m" if name == "postgresql" else "3g"), "--env-file", str(env_file), "-p", f"127.0.0.1::{internal}", image], check=True, capture_output=True)
        started = True
        env_file.unlink()
        state = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
        port = state["NetworkSettings"]["Ports"][f"{internal}/tcp"][0]["HostPort"]
        provider = get_provider(name)
        config = ConnectionConfig.from_dict(
            dict(
                name=f"{provider.metadata.display_name} integration",
                db_type=name,
                server="127.0.0.1",
                port=port,
                database="sqlit_schema_it" if name == "postgresql" else "master",
                username="postgres" if name == "postgresql" else "sa",
                password=password,
                options={"tls_trust_server_certificate": True} if name == "mssql" else {},
            )
        )
        deadline = time.monotonic() + 120
        while True:
            running = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]["State"]
            if not running["Running"]:
                logs = subprocess.run(["docker", "logs", "--tail", "35", container], capture_output=True, text=True)
                raise RuntimeError(f"{name} exited during startup: " + (logs.stdout + logs.stderr).replace(password, "[redacted]"))
            try:
                connection = provider.connection_factory.connect(config)
                sql(connection, "SELECT 1")
                break
            except Exception as error:
                if connection:
                    connection.close()
                    connection = None
                if time.monotonic() > deadline:
                    raise RuntimeError(f"{name} readiness failed: " + str(error).replace(password, "[redacted]")) from None
                time.sleep(1)
        if name == "mssql":
            connection.autocommit = True
            sql(connection, "CREATE DATABASE [sqlit_schema_it]")
            connection.close()
            config = config.with_endpoint(database="sqlit_schema_it")
            connection = provider.connection_factory.connect(config)
            connection.autocommit = True
        yield config, provider, connection, "sqlit_schema_it"
    finally:
        env_file.unlink(missing_ok=True)
        if connection:
            connection.close()
        if started:
            subprocess.run(["docker", "stop", "-t", "20", container], check=True, capture_output=True)
            subprocess.run(["docker", "rm", container], check=True, capture_output=True)


@contextmanager
def provider_database(name, root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    billing = "" if name == "sqlite" else "billing"
    rows = {billing: [(1001, "Northwind Bikes", 1240), (1002, "Harbor Coffee", 385)]}
    if name != "sqlite":
        rows["analytics"] = [(2001, "Monthly revenue", 28500)]

    def case(config, provider, conn, database, evidence):
        result = ProviderCase(name, config, provider, conn, database, billing, "analytics", "empty_lab", evidence, rows)
        seed(result)
        return result

    if name in {"postgresql", "mssql"}:
        with docker_database(name, root) as (config, provider, conn, database):
            yield case(config, provider, conn, database, "live PostgreSQL 16" if name == "postgresql" else "live SQL Server 2022")
    elif name == "supabase":
        # Run Supabase's real adapter against PostgreSQL. Replace only the
        # cloud network destination; never fabricate catalog/query responses.
        from unittest.mock import patch

        import psycopg2

        with docker_database("postgresql", root) as (local_config, _, conn, database):
            provider = get_provider("supabase")
            config = ConnectionConfig.from_dict(
                dict(
                    name="Supabase adapter integration",
                    db_type="supabase",
                    server="placeholder",
                    username="fixture",
                    password=local_config.tcp_endpoint.password,
                    options={"supabase_project_id": "fixture", "supabase_region": "us-east-1", "supabase_aws_shard": "aws-0"},
                )
            )
            real_connect = psycopg2.connect

            def local_transport(*args, **kwargs):
                assert kwargs["host"] == "aws-0-us-east-1.pooler.supabase.com"
                assert kwargs["user"] == "postgres.fixture"
                assert kwargs["database"] == "postgres"
                endpoint = local_config.tcp_endpoint
                kwargs.update(host=endpoint.host, port=endpoint.port, user=endpoint.username, password=endpoint.password, database=database)
                return real_connect(*args, **kwargs)

            with patch("psycopg2.connect", side_effect=local_transport):
                yield case(config, provider, conn, database, "Supabase adapter / local PostgreSQL transport")
    elif name == "sqlite":
        path = root / "fixture.sqlite"
        provider = get_provider(name)
        config = ConnectionConfig.from_dict(dict(name="SQLite fallback integration", db_type="sqlite", file_path=str(path)))
        with closing(sqlite3.connect(path)) as conn:
            result = case(config, provider, conn, None, "local SQLite")
            conn.commit()
            yield result
    elif name == "snowflake":
        import fakesnow

        (root / "fakesnow").mkdir()
        with fakesnow.patch(db_path=root / "fakesnow"):
            config = ConnectionConfig.from_dict(dict(name="Snowflake emulator integration", db_type="snowflake", server="local-emulator", database="SQLIT_SCHEMA_IT", username="fixture", password="fixture", options={"schema": "PUBLIC"}))
            provider = get_provider(name)
            conn = provider.connection_factory.connect(config)
            try:
                yield case(config, provider, conn, "SQLIT_SCHEMA_IT", "Snowflake emulation (fakesnow)")
            finally:
                conn.close()
    else:
        raise ValueError(f"Unknown integration provider: {name}")
