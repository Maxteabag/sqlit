## Why

Exasol is a fully registered, unit-tested provider — but **no code path has ever opened a real
Exasol connection**. Every unit test added by `exasol-unit-coverage` runs against a `MagicMock`,
and a mock agrees with whatever the adapter asks of it by construction: if `conn.meta.list_tables()`
really returns lowercase keys, or `ExaStatement.rowcount` is really an attribute rather than a
method, or `websocket_sslopt` is really spelled differently, the mocked suite stays green. The
adapter's contract with pyexasol is currently unverified in both directions.

Upstream `Maxteabag/sqlit` backs every non-file-based provider with a Docker-driven integration job
in `.github/workflows/ci.yml`. A provider PR without one is missing the repo's own convention. This
change adds that job and the harness it needs. It is plan.md steps 12, 13 and 14 — the `INT` atomic
group, taken together because step 13 alone leaves the default CI job collecting a test that needs a
container it does not have.

## What Changes

- **Modified** `infra/docker/docker-compose.test.yml` — a new `exasol` service under the existing
  `enterprise` profile (alongside `db2` / `oracle11g` / `trino`), because `exasol/docker-db:latest-8`
  is a multi-gigabyte image that needs `privileged: true`, a long boot and a
  `stop_grace_period: 120s` to shut down cleanly. Ports `${EXASOL_PORT:-8563}:8563`.
- **New** `tests/fixtures/exasol.py` — modelled on `tests/fixtures/clickhouse.py`: env-var constants
  (`EXASOL_HOST`/`PORT`/`USER`/`PASSWORD`/`SCHEMA`), an `exasol_available()` TCP guard, a session
  `exasol_server_ready` fixture, an `exasol_db` fixture that drops and recreates the `TEST_SQLIT`
  schema and seeds the objects `BaseDatabaseTests` expects (`test_users` with an `id` primary key,
  `test_products`, the view `test_user_emails`), and an `exasol_connection` fixture that registers a
  sqlit CLI connection. Defaults `sys` / `exasol` — the `docker-db` defaults.
- **Modified** `tests/conftest.py` — one `from tests.fixtures.exasol import *` line in the existing
  alphabetical fixture block.
- **New** `tests/test_exasol.py` — `TestExasolIntegration(BaseDatabaseTestsWithLimit)` with a
  `DatabaseTestConfig(db_type="exasol", display_name="Exasol", ...)`, plus CLI create/delete
  connection tests mirroring `tests/test_clickhouse.py`.
- **Modified** `.github/workflows/ci.yml` — `--ignore=tests/test_exasol.py` added to the unit-test
  job's exclude list, and a new `test-exasol` job modelled on `test-clickhouse`
  (`uv sync --group test --no-dev --extra exasol`, start the container, poll port 8563, run
  `pytest tests/test_exasol.py`).
- No changes to any file under `sqlit/`. The adapter is being exercised, not modified. If the
  container disagrees with it, that is a finding for a follow-up change.

## Capabilities

### New Capabilities

- `exasol-integration-harness`: a reproducible local and CI Exasol instance plus the pytest fixtures
  that seed it — including the two hard constraints that the fixture module imports cleanly with no
  `pyexasol` installed, and that every fixture skips rather than fails when the container is absent.
- `exasol-integration-coverage`: the shared database test suite runs against a real Exasol server,
  and does so in a dedicated CI job without being collected by the driver-free unit job.

### Modified Capabilities

None. `openspec/specs/exasol-adapter` and `openspec/specs/exasol-provider-registration` describe the
behaviour this change verifies against a live server; no requirement in either changes.
`openspec/specs/exasol-driver-packaging` already registered the `exasol` pytest marker — this change
consumes nothing new from it (see design D6).

## Impact

- **CI cost**: one new job pulling `exasol/docker-db:latest-8` (~4 GB) and waiting several minutes
  for the database to accept connections. Gated the same way as every other integration job — on
  push and PR, `needs: build` — per the decision recorded in design D7.
- **CI safety**: the unit job's exclude list is *filename-based*, so `tests/test_exasol.py` and the
  `--ignore` for it must land in the same commit. This is why plan.md marks 13 + 14 atomic.
- **`tests/conftest.py` import surface**: `conftest.py` is imported by the driver-free unit job, so
  the new fixture module cannot import `pyexasol` at module level. It imports it inside `exasol_db`
  and skips on `ImportError`, exactly as `tests/fixtures/clickhouse.py` does for
  `clickhouse_connect`.
- **TLS**: `docker-db` presents a self-signed certificate, so the connection fixture must pass
  `--tls-mode require`. This is not incidental — it makes the integration test the first thing to
  exercise the `tls_mode` → `encryption` + `websocket_sslopt` mapping against a real TLS handshake.
- **Identifier case**: Exasol folds unquoted identifiers to uppercase. The shared suite's
  assertions already tolerate uppercase column names (`data[0].get("name") or data[0].get("NAME")`,
  `"id,name" in result.stdout.lower()`), and the seed DDL stays unquoted so `test_users` and
  `TEST_USERS` resolve to the same object. See design D3.
- **Self-skipping base tests**: `test_get_indexes`, `test_get_triggers`, `test_get_sequences` and the
  three `*_definition` tests skip on `session.adapter.supports_*`, all of which `ExasolAdapter`
  reports `False`. The fixture therefore seeds no index, trigger or sequence.
- **Not affected**: no `sqlit/` source, no `pyproject.toml`, no `uv.lock`, no documentation. Docs are
  plan.md step 15.
