## ADDED Requirements

### Requirement: Local Exasol test server

The test compose stack SHALL provide an Exasol service that a developer can start on demand, and
that service SHALL NOT be started by the default `docker compose up`.

#### Scenario: Service is declared under the opt-in profile

- **WHEN** `docker compose -f infra/docker/docker-compose.test.yml --profile enterprise config` is run
- **THEN** the rendered configuration contains an `exasol` service built from an `exasol/docker-db`
  image, running `privileged`, publishing container port `8563` on `${EXASOL_PORT:-8563}`, and
  declaring a `stop_grace_period` of at least 120 seconds

#### Scenario: Default profile is unchanged

- **WHEN** `docker compose -f infra/docker/docker-compose.test.yml config --services` is run with no
  profile
- **THEN** `exasol` is absent from the listed services, so no developer pulls a multi-gigabyte image
  without asking for it

### Requirement: Fixture module imports without the driver

`tests/fixtures/exasol.py` SHALL be importable in an environment where `pyexasol` is not installed,
because `tests/conftest.py` star-imports it and is loaded by the driver-free unit CI job.

#### Scenario: Collection succeeds with no exasol extra installed

- **WHEN** the unit-test command from `.github/workflows/ci.yml` is run in an environment installed
  with `uv sync --group test --no-dev` (no `--extra exasol`)
- **THEN** collection completes with no `ImportError` and no collection error from `tests/conftest.py`

#### Scenario: Driver is imported lazily

- **WHEN** `tests/fixtures/exasol.py` is inspected
- **THEN** it contains no module-level `import pyexasol`, and every `pyexasol` import sits inside a
  fixture body guarded so that an `ImportError` becomes `pytest.skip`, not a test failure

### Requirement: Fixtures skip rather than fail when the server is absent

Every Exasol fixture SHALL resolve to a skip when no reachable Exasol server is available, so that a
full `pytest tests/` run stays green on a machine with no Docker.

#### Scenario: No container running

- **WHEN** nothing is listening on the configured Exasol host and port
- **THEN** tests depending on the Exasol fixtures are reported as skipped, and no exception escapes
  a fixture

#### Scenario: Driver missing but container present

- **WHEN** an Exasol server is reachable but `pyexasol` is not installed
- **THEN** the fixtures skip with a message naming the missing driver

### Requirement: Readiness gate tolerates a slow boot

The readiness fixture SHALL confirm readiness by opening a real database connection, retrying until
a deadline, rather than trusting an open port — Exasol accepts TCP connections on its port well
before it will accept a login.

#### Scenario: Server is still booting

- **WHEN** the port is open but the database refuses connections
- **THEN** the readiness fixture retries until its deadline, and only then reports the server as
  unavailable

#### Scenario: Server becomes ready during the wait

- **WHEN** the database starts accepting connections before the deadline expires
- **THEN** the readiness fixture reports the server as ready and the dependent tests run

#### Scenario: Readiness is computed once per session

- **WHEN** more than one Exasol test runs in the same session
- **THEN** the readiness check is performed once, because it is session-scoped

### Requirement: Seeded test schema matches the shared suite's expectations

The `exasol_db` fixture SHALL create a dedicated test schema containing exactly the objects the
shared database test suite queries, and SHALL leave no trace of itself behind.

#### Scenario: Schema is seeded

- **WHEN** the `exasol_db` fixture runs
- **THEN** the test schema contains a `test_users` table whose `id` column is a primary key and
  which holds the three rows Alice, Bob and Charlie; a `test_products` table; and a
  `test_user_emails` view
- **AND** the fixture yields the schema name so a connection can be opened against it

#### Scenario: Identifiers resolve unquoted

- **WHEN** the seed DDL is executed
- **THEN** it uses unquoted identifiers, so that Exasol's uppercase folding makes
  `SELECT * FROM test_users` — the form the shared suite issues — resolve to the seeded table

#### Scenario: State does not leak between tests

- **WHEN** one test inserts an extra row into `test_users` and a later test asserts a three-row
  result
- **THEN** the later test still sees three rows, because the fixture recreates the schema per test

#### Scenario: Teardown drops the schema

- **WHEN** a test using `exasol_db` finishes, whether it passed or failed
- **THEN** the test schema is dropped, and a teardown failure does not fail the test

### Requirement: CLI connection fixture negotiates TLS against a self-signed certificate

The `exasol_connection` fixture SHALL register a sqlit connection through the CLI whose TLS settings
succeed against the self-signed certificate that `exasol/docker-db` presents, and SHALL remove that
connection afterwards.

#### Scenario: Connection is created with an encrypting, non-verifying TLS mode

- **WHEN** the `exasol_connection` fixture registers its connection
- **THEN** it passes `--tls-mode require`, so the adapter encrypts the connection without verifying
  the certificate chain, and the connection is usable by the shared suite

#### Scenario: Connection targets the seeded schema

- **WHEN** the connection is created
- **THEN** it carries the seeded schema as its initial schema, so unqualified table names in the
  shared suite's queries resolve without a schema prefix

#### Scenario: Connection is cleaned up

- **WHEN** a test using `exasol_connection` finishes
- **THEN** the connection is deleted from the sqlit connection store

### Requirement: Fixtures are registered and environment-configurable

The Exasol fixtures SHALL be discoverable by the test suite and SHALL take their host, port,
credentials and schema name from environment variables, so the same suite runs against a local
container and against a CI-provided server.

#### Scenario: Fixtures are registered in conftest

- **WHEN** `tests/conftest.py` is read
- **THEN** it star-imports `tests.fixtures.exasol` within its existing alphabetically ordered
  fixture import block

#### Scenario: Connection details are overridable

- **WHEN** `EXASOL_HOST`, `EXASOL_PORT`, `EXASOL_USER`, `EXASOL_PASSWORD` or `EXASOL_SCHEMA` are set
  in the environment
- **THEN** the fixtures use those values instead of their defaults
