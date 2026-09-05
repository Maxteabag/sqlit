## 1. Plan bookkeeping and preflight

- [x] 1.1 In `plan.md`, set steps 12, 13 and 14 to `wip` in the Status table before touching any
      file. The plan's own protocol requires the whole `INT` group to be taken in one session or not
      at all.
- [x] 1.2 Confirm the environment has the driver: `uv sync --extra exasol` then
      `uv run python -c "import pyexasol; print(pyexasol.__version__)"`. The integration suite is the
      one place that genuinely needs it.
- [x] 1.3 Record the pre-change baseline of the unit-test command from `.github/workflows/ci.yml`
      (lines 70-82) so a new failure can be told apart from the plan's already-logged
      Windows-environment failures.

## 2. Compose service (plan step 12a)

- [x] 2.1 Add an `exasol` service to `infra/docker/docker-compose.test.yml`, placed with the other
      `enterprise`-profile services (`db2`, `oracle11g`, `trino`, `presto`, `impala`):
      `image: exasol/docker-db:latest-8`, `container_name: sqlit-test-exasol`,
      `privileged: true`, `stop_grace_period: 120s`, `ports: ["${EXASOL_PORT:-8563}:8563"]`,
      `profiles: [enterprise]`. Design D1: no `healthcheck` block.
- [x] 2.2 Verify the enterprise profile renders:
      `docker compose -f infra/docker/docker-compose.test.yml --profile enterprise config`.
- [x] 2.3 Verify the default profile is untouched:
      `docker compose -f infra/docker/docker-compose.test.yml config --services` does **not** list
      `exasol`.
- [x] 2.4 Start the container —
      `docker compose -f infra/docker/docker-compose.test.yml --profile enterprise up -d exasol` —
      and note how long it takes before port 8563 accepts a login. That number is the input to task
      6.3's poll count.
- [x] 2.5 Resolve design O3 against the running container: confirm the default SYS credentials
      (`sys` / `exasol`) and whether the image accepts a password override. Record the answer in the
      plan's Session log; if the defaults differ, use the real ones in task 3.2 and 6.4.

## 3. Fixture module (plan step 12b)

- [x] 3.1 Create `tests/fixtures/exasol.py` modelled on `tests/fixtures/clickhouse.py`, importing
      `cleanup_connection`, `is_port_open` and `run_cli` from `tests.fixtures.utils`. Design
      constraint 1: **no module-level `import pyexasol`**.
- [x] 3.2 Add the env-var constants: `EXASOL_HOST` (default `localhost`), `EXASOL_PORT` (`8563`),
      `EXASOL_USER` (`sys`), `EXASOL_PASSWORD` (`exasol`), `EXASOL_SCHEMA` (`TEST_SQLIT`), plus an
      `exasol_available()` helper wrapping `is_port_open`.
- [x] 3.3 Add a session-scoped `exasol_server_ready` fixture: return `False` immediately when
      `exasol_available()` is false; otherwise import `pyexasol` inside the fixture and retry
      `pyexasol.connect(dsn=..., user=..., password=..., encryption=True,
      websocket_sslopt={"cert_reqs": ssl.CERT_NONE}, autocommit=True)` with a sleep until a deadline,
      returning `True` on the first success and `False` if the deadline passes. Design D2 — an open
      port is not readiness.
- [x] 3.4 Add a function-scoped `exasol_db` fixture that skips when `exasol_server_ready` is false,
      skips on `ImportError` for `pyexasol`, then `DROP SCHEMA IF EXISTS TEST_SQLIT CASCADE` /
      `CREATE SCHEMA TEST_SQLIT` / `OPEN SCHEMA TEST_SQLIT`. Design D5.
- [x] 3.5 Seed inside `exasol_db`, all identifiers **unquoted** (design D3): `test_users`
      (`id DECIMAL(18,0) PRIMARY KEY`, `name VARCHAR`, `email VARCHAR`), `test_products`
      (`id`, `name`, `price`, `stock`), the view `test_user_emails` selecting `id, name, email` from
      `test_users` where `email` is non-empty, three `test_users` rows (Alice, Bob, Charlie) and
      three `test_products` rows. Seed **no** index, trigger or sequence.
- [x] 3.6 Wrap the setup in `try/except Exception` → `pytest.skip(f"Failed to setup Exasol schema: {e}")`,
      matching `tests/fixtures/clickhouse.py`. `yield EXASOL_SCHEMA`, then drop the schema in a
      teardown whose own failure is swallowed.
- [x] 3.7 Add a function-scoped `exasol_connection` fixture that `cleanup_connection`s a
      pid-suffixed name, then `run_cli("connections", "add", "exasol", "--name", ..., "--server", ...,
      "--port", ..., "--username", ..., "--password", ..., "--schema", exasol_db,
      "--tls-mode", "require")`, yields the name, and cleans up after. Design D4 — `--tls-mode
      require` is required by the self-signed certificate and is deliberate TLS coverage.
- [x] 3.8 Declare `__all__` listing the constants and fixtures, matching
      `tests/fixtures/clickhouse.py`'s style — `test_exasol.py` reads the constants back through
      `from .conftest import ...`, which relies on the star-import re-export.
- [x] 3.9 Verify the module imports with the driver absent — the constraint the unit CI job imposes.
      Run the unit-test command from `ci.yml` in an environment installed without `--extra exasol`
      (or temporarily rename the installed `pyexasol` package) and confirm no collection error.

## 4. conftest registration (plan step 12c)

- [x] 4.1 Add `from tests.fixtures.exasol import *` to `tests/conftest.py`, in the alphabetical block
      that starts at line 5 — between the `duckdb` and `firebird` imports.
- [x] 4.2 Verify `uv run pytest tests/connections -v` still collects and passes: the conftest is
      importable and nothing regressed.
- [x] 4.3 Verify `uv run pytest tests/ --collect-only -q` succeeds. This is the gate that catches a
      fixture-module import error before CI does.

## 5. Integration test file (plan step 13 — must land with group 6)

- [x] 5.1 Create `tests/test_exasol.py` with
      `class TestExasolIntegration(BaseDatabaseTestsWithLimit)` importing from
      `.test_database_base`. Design D8 — the `WithLimit` superset, not `BaseDatabaseTests` as
      plan.md step 13 says. No `@pytest.mark.exasol` (design D6).
- [x] 5.2 Implement the `config` property returning
      `DatabaseTestConfig(db_type="exasol", display_name="Exasol",
      connection_fixture="exasol_connection", db_fixture="exasol_db",
      create_connection_args=lambda: [])`. Leave `uses_limit` at its `True` default and
      `timezone_datetime_type` at `None` (design O2).
- [x] 5.3 Override `test_docker_container_connection` with an unconditional `pytest.skip` whose
      message states both reasons from design D9: `exasol/docker-db` publishes no credentials through
      environment variables (`SPEC.docker_detector` has `env_vars={}`), and a discovery-built config
      carries no `tls_mode` so it verifies TLS against a self-signed certificate. Do **not** override
      the other two `DockerDiscoveryTests` methods.
- [x] 5.4 Override `test_primary_key_detection` per design D10: load the connection config, open a
      `ConnectionSession`, and call `session.adapter.get_columns(session.connection, "TEST_USERS",
      database=None, schema=EXASOL_SCHEMA)` — the app's call shape. Assert at least three columns,
      that `ID` is flagged primary key, and that no other column is. Comment the override with the
      `LIKE ''` / case-sensitivity reason.
- [x] 5.5 Add `test_create_exasol_connection`, modelled on `tests/test_clickhouse.py:26`: create a
      connection via `cli_runner`, assert `returncode == 0` and `"created successfully"` in stdout,
      assert the name and `"Exasol"` appear in `connection list`, and delete it in a `finally`.
- [x] 5.6 Add `test_delete_exasol_connection`, mirroring the ClickHouse equivalent: create, delete,
      assert `"deleted successfully"`, assert the name is gone from `connection list`.
- [x] 5.7 Run the suite against the live container: `uv run pytest tests/test_exasol.py -v`.
      Every test must pass or skip; nothing may fail.
- [x] 5.8 Read the skip list from 5.7 and confirm each skip has a declared cause: indexes, triggers,
      sequences and the three `*_definition` tests from adapter capability flags; the timezone test
      from `timezone_datetime_type=None`; the Docker-discovery connection test from the 5.3 override.
      Any **other** skip is unexplained — investigate before proceeding.
- [x] 5.9 Stop the container and re-run `uv run pytest tests/test_exasol.py -v`: every test must be
      **skipped**, none errored. This is the guarantee that a laptop without Docker stays green.
- [x] 5.10 Record any place where the live server contradicted the adapter as a finding in the plan's
      Session log. Do **not** edit anything under `sqlit/` — the proposal's Non-Goals exclude it, and
      design O1 already names the follow-up.

## 6. CI wiring (plan step 14 — must land with group 5)

- [x] 6.1 Add `--ignore=tests/test_exasol.py` to the unit-test job's exclude list in
      `.github/workflows/ci.yml`, after the `--ignore=tests/test_clickhouse.py` line (~line 82).
      This must be in the same commit as task 5.1 — the exclude list is filename-based.
- [x] 6.2 Add a `test-exasol` job modelled on `test-clickhouse` (~line 440): `runs-on:
      ubuntu-latest`, `needs: build`, checkout, Python 3.12, `astral-sh/setup-uv@v5`, then
      `uv sync --group test --no-dev --extra exasol`.
- [x] 6.3 Add the server step: `docker run -d --name exasol --privileged -p 8563:8563
      exasol/docker-db:latest-8`, then a `for i in {1..60}` poll on port 8563 sleeping 10s, echoing
      each attempt, and breaking on success. Design D7 — sized from the boot time measured in task
      2.4, with headroom.
- [x] 6.4 Add the test step with `EXASOL_HOST`, `EXASOL_PORT`, `EXASOL_USER`, `EXASOL_PASSWORD` and
      `EXASOL_SCHEMA` in `env:`, running `uv run pytest tests/test_exasol.py -v --timeout=300`.
- [x] 6.5 Confirm the job's triggers, `needs:` and absence of `continue-on-error` match the other
      per-database jobs. Design D7 — no manual gating, no soft failure.
- [x] 6.6 Verify the workflow file parses: `python -c "import yaml,sys;
      yaml.safe_load(open('.github/workflows/ci.yml'))"`.
- [x] 6.7 Run the unit job's exact command (now with the exasol ignore) from `ci.yml:70-82` and
      confirm it collects and passes, with no new failure against the task 1.3 baseline.

## 7. Change gate and plan bookkeeping

- [x] 7.1 Run `uv run ruff check tests` and confirm it is clean for the new and modified files.
- [x] 7.2 Confirm `git status` shows exactly the intended surface: `infra/docker/docker-compose.test.yml`,
      `tests/conftest.py`, `.github/workflows/ci.yml`, new `tests/fixtures/exasol.py`, new
      `tests/test_exasol.py`, plus the change's own openspec files and the pre-existing
      modifications carried by earlier changes. **No file under `sqlit/`.**
- [x] 7.3 In `plan.md`, set steps 12, 13 and 14 to `done` and update the progress count to
      `14 / 15 done`.
- [x] 7.4 Append one `plan.md` Session log row recording: the resolved O3 credentials, the measured
      boot time and the poll count chosen from it, the two base-test overrides (D9, D10) and their
      reasons, the `get_columns` `LIKE ''` finding earmarked for a follow-up change (O1), and the
      `BaseDatabaseTestsWithLimit` deviation from step 13's wording (D8).
- [x] 7.5 Tear down the container:
      `docker compose -f infra/docker/docker-compose.test.yml --profile enterprise down -v`.
