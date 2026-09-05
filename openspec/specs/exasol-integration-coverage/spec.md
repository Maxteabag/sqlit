# exasol-integration-coverage Specification

## Purpose
Defines what running the repository's shared database suite against a live Exasol server proves, and
the dedicated CI job that runs it. Every other Exasol test in the repo runs against a `MagicMock`,
which agrees with whatever the adapter asks of it; these requirements are the only place the
adapter's contract with pyexasol is checked in both directions.

Two inherited tests cannot apply as written and are overridden rather than deleted, each with its
reason stated in the skip or the comment. `test_docker_container_connection` cannot work because
`exasol/docker-db` publishes no credentials through any environment variable and a discovery-built
config carries no `tls_mode`, so it would verify TLS against the image's self-signed certificate -
both properties of the image, neither fixable from `tests/`. `test_primary_key_detection` is
re-issued through the call shape the application actually uses, because the base version passes a
lowercase name and no schema, and pyexasol's metadata patterns are case-sensitive `LIKE` patterns
that the adapter narrows further to `LIKE ''`.

The exclusion of the integration file from the driver-free unit job is a requirement rather than an
incidental setting: that job's exclude list is matched by filename, so the file and its `--ignore`
have to land together or the job collects a test whose container it never starts.

Scope boundaries: the server and fixtures this suite consumes live in
`exasol-integration-harness`; the adapter behaviour being asserted lives in `exasol-adapter` and
`exasol-provider-registration`; the mocked unit coverage lives in `exasol-unit-coverage`.

## Requirements
### Requirement: Exasol runs the shared database integration suite

`tests/test_exasol.py` SHALL run the repository's shared database test suite against a live Exasol
server, including the suite's `LIMIT` coverage.

#### Scenario: Suite is bound to the Exasol provider

- **WHEN** `tests/test_exasol.py` is collected
- **THEN** it defines a single test class deriving from the shared base class that includes the
  `LIMIT` test, configured with database type `exasol`, display name `Exasol`, and the Exasol
  connection and database fixtures

#### Scenario: Suite passes against a running server

- **WHEN** `uv run pytest tests/test_exasol.py -v` is run with an Exasol container up and the
  `exasol` extra installed
- **THEN** every inherited test either passes or skips for a reason the adapter declares, and none
  fails

#### Scenario: Suite skips without a server

- **WHEN** the same command is run with no Exasol server reachable
- **THEN** every test in the file is skipped

### Requirement: Exasol connection lifecycle is verified through the CLI

The Exasol test file SHALL verify that a connection can be created and deleted through the sqlit
CLI, independently of the fixture that the shared suite uses.

#### Scenario: Connection is created and listed

- **WHEN** an Exasol connection is added with `connections add exasol` and the connection list is
  printed
- **THEN** the command reports success and the listing shows the connection name alongside the
  `Exasol` display name

#### Scenario: Connection is deleted

- **WHEN** that connection is deleted through the CLI
- **THEN** the command reports success and the connection no longer appears in the listing

### Requirement: Capability-driven and image-driven skips are explicit

Tests that cannot apply to Exasol SHALL skip for a stated reason rather than being deleted or
silently passing.

#### Scenario: Unsupported object types self-skip

- **WHEN** the inherited index, trigger and sequence tests run
- **THEN** they skip because `ExasolAdapter` reports those capabilities as unsupported, and the test
  fixture seeds no such objects

#### Scenario: Docker-discovery connection test is skipped with a reason

- **WHEN** the inherited Docker-discovery connection test runs
- **THEN** it is skipped by an override whose message states that `exasol/docker-db` publishes no
  credentials through environment variables and presents a self-signed certificate, so a
  discovery-built configuration cannot connect

#### Scenario: Docker container detection is not skipped

- **WHEN** the inherited Docker container detection test runs with the Exasol container up
- **THEN** it is not overridden, and it passes by detecting the container and its published port

### Requirement: Primary-key detection is verified through the app's call shape

The primary-key test SHALL exercise `get_columns` with the schema and identifier casing that the
application itself supplies, and SHALL still assert the full primary-key contract.

#### Scenario: Columns are requested with an explicit schema and server casing

- **WHEN** the Exasol primary-key test calls the adapter's `get_columns`
- **THEN** it passes the seeded schema and the table name in the casing the server stores, matching
  how the explorer and worker call it with values taken from `get_tables()`

#### Scenario: Primary key flags are asserted both ways

- **WHEN** the returned columns are inspected
- **THEN** the `id` column is flagged as a primary key and every other column is not

### Requirement: The driver-free unit job does not collect the Exasol integration test

The default CI unit job SHALL exclude `tests/test_exasol.py`, in the same commit that introduces the
file, because that job installs no database extras and starts no container.

#### Scenario: Unit job excludes the file

- **WHEN** the unit-test job's pytest invocation in `.github/workflows/ci.yml` is read
- **THEN** its exclude list contains `--ignore=tests/test_exasol.py` alongside the other integration
  test files

#### Scenario: Unit job still passes locally

- **WHEN** that exact command is run locally
- **THEN** collection succeeds and no Exasol integration test is collected

### Requirement: A dedicated CI job runs the Exasol integration suite

`.github/workflows/ci.yml` SHALL contain a job that provisions an Exasol server and runs the Exasol
integration test file, following the same conventions as the repository's other per-database
integration jobs.

#### Scenario: Job installs the driver

- **WHEN** the job's dependency step runs
- **THEN** it installs the test group together with the `exasol` extra

#### Scenario: Job starts the server and waits for it

- **WHEN** the job's server step runs
- **THEN** it starts an `exasol/docker-db` container with the privileges the image needs and the
  database port published, and polls that port until it accepts connections or a bounded number of
  attempts is exhausted, logging each attempt

#### Scenario: Job runs the suite with the harness environment

- **WHEN** the job's test step runs
- **THEN** it invokes pytest on `tests/test_exasol.py` with the Exasol host, port, credential and
  schema environment variables set, and with a per-test timeout large enough for a cold server

#### Scenario: Job is gated like its peers

- **WHEN** the workflow triggers are compared across integration jobs
- **THEN** the Exasol job runs on the same events as the other database jobs, depends on the same
  upstream job, and is neither manually gated nor marked to continue on error
