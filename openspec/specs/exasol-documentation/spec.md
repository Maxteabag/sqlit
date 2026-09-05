# exasol-documentation Specification

## Purpose
Defines the documentation surface for the Exasol provider — the two top-level documents a person
reads before touching this repo. `README.md` names Exasol among the supported engines and carries the
driver install command a user reaches for when sqlit reports a missing driver; `CONTRIBUTING.md`
tells a contributor which compose profile starts the Exasol container, which environment variables
repoint the tests at another server, and that the container needs minutes rather than seconds before
it accepts a login.

Every value documented here is a claim about code that already exists, which is what makes this
capability testable rather than decorative: the driver package is the distribution declared by the
`exasol` extra, the container list names the profile that actually starts the service, and each
documented default equals the fallback the fixture module reads. A table that has drifted from the
code is worse than no table, because it sends a contributor to debug their environment rather than
the value.

Scope boundaries: the extra itself lives in `exasol-driver-packaging`; `DatabaseType` membership and
the picker display order this documentation mirrors live in `exasol-provider-registration`; the
compose service, the fixtures and the `EXASOL_*` variables being described live in
`exasol-integration-harness`; adapter behaviour lives in `exasol-adapter`.

## Requirements
### Requirement: Exasol is listed among supported databases

`README.md` SHALL name Exasol in the sentence that enumerates supported engines, so that a reader
deciding whether sqlit talks to their database can answer the question without reading source.

Placement SHALL follow the connection picker's display order rather than alphabetical order, so the
document and the running application agree on where Exasol sits among the engines.

#### Scenario: Supported-database sentence names Exasol

- **WHEN** the "Supports all major databases:" sentence in `README.md` is read
- **THEN** it contains `Exasol`, positioned immediately after `Teradata`
- **AND** every other engine named in that sentence is unchanged, in the same order, with the
  trailing `and osquery.` still closing the list

#### Scenario: Picker order and README order agree

- **WHEN** the position of Exasol in that sentence is compared with the provider display order used
  by the connection picker
- **THEN** Exasol follows Teradata in both

### Requirement: Driver Reference gives the Exasol install command

The Driver Reference table in `README.md` SHALL carry a row for Exasol naming `pyexasol` as the
driver package, with the `pipx inject` and `pip install` commands spelled out in the same form as
every other row. The table exists so that a user hitting a missing-driver error can copy one command
and continue; a row that omits either column fails that purpose for half its readers.

The package name SHALL be the distribution actually declared by the `exasol` extra in
`pyproject.toml`, not a hand-written approximation of it.

#### Scenario: Exasol row is present and complete

- **WHEN** the Driver Reference table is read
- **THEN** it contains a row whose Database cell is `Exasol`, whose Driver package cell is
  `pyexasol`, whose `pipx` cell is `pipx inject sqlit-tui pyexasol`, and whose `pip` / venv cell is
  `python -m pip install pyexasol`

#### Scenario: Documented package matches the declared extra

- **WHEN** the driver package named in the Exasol row is compared with `exasol = [...]` in
  `pyproject.toml`
- **THEN** both name the `pyexasol` distribution

#### Scenario: Existing rows are untouched

- **WHEN** the diff of `README.md` is inspected
- **THEN** the only change inside the table is the added Exasol row, with no other row's cells,
  spacing or column alignment altered

### Requirement: Enterprise profile documents its Exasol container

`CONTRIBUTING.md` SHALL name Exasol in the list of containers started by the `enterprise` compose
profile. The Exasol service is declared under that profile precisely so it is not pulled by default,
which means a contributor learns it exists only from this list.

#### Scenario: Enterprise container list names Exasol

- **WHEN** the sentence introducing the `--profile enterprise` command in `CONTRIBUTING.md` is read
- **THEN** it names Exasol alongside Db2, Trino, Presto and Oracle 11g
- **AND** the `docker compose ... --profile enterprise up -d` command below it is unchanged, because
  it already starts every service in the profile

### Requirement: Exasol test environment variables are documented with their real defaults

The Environment Variables section of `CONTRIBUTING.md` SHALL carry an Exasol table listing every
`EXASOL_*` variable that `tests/fixtures/exasol.py` reads, and each documented default SHALL equal
the default in that module. A table that drifts from the code is worse than no table: it sends a
contributor to debug their environment rather than the value.

The table SHALL include `EXASOL_READY_TIMEOUT`, which has no analogue in any other engine's table
and is documented nowhere else, because it is the only knob a contributor on slow hardware or a cold
image pull can reach for.

#### Scenario: Every fixture variable appears

- **WHEN** the `EXASOL_`-prefixed names read by `tests/fixtures/exasol.py` are compared with the rows
  of the Exasol table
- **THEN** the two sets are equal, covering `EXASOL_HOST`, `EXASOL_PORT`, `EXASOL_USER`,
  `EXASOL_PASSWORD`, `EXASOL_SCHEMA` and `EXASOL_READY_TIMEOUT`

#### Scenario: Documented defaults match the code

- **WHEN** each default in the table is compared with the fallback passed to `os.environ.get` for the
  same variable
- **THEN** they are identical: `localhost`, `8563`, `sys`, `exasol`, `TEST_SQLIT` and `300`

#### Scenario: Table matches the shape of its neighbours

- **WHEN** the Exasol table is compared with the SQL Server and Db2 tables above it
- **THEN** it uses the same `**Exasol:**` bold label, the same
  `| Variable | Default | Description |` header, and the same separator row

### Requirement: Contributors are told Exasol boots slowly

`CONTRIBUTING.md` SHALL state that the Exasol container takes substantially longer to accept
connections than the "about 30-45 seconds" quoted for the standard profile, and SHALL distinguish
the port opening from the server accepting a login.

Without this, a contributor who waits the documented 45 seconds, sees a refused login and concludes
the container is broken is behaving reasonably — the measured figures are 21 seconds to an open port
and 101 seconds to a first successful login on an already-pulled image.

#### Scenario: Readiness expectation is stated

- **WHEN** the Exasol documentation in `CONTRIBUTING.md` is read
- **THEN** it warns that Exasol needs minutes rather than seconds before it accepts connections, and
  that an open port 8563 does not yet mean the database will authenticate

#### Scenario: The standard-profile timing is not overwritten

- **WHEN** the existing "about 30-45 seconds" guidance is inspected
- **THEN** it is unchanged, because it remains correct for the default profile that most
  contributors run

### Requirement: The change is documentation only

This change SHALL modify no file outside `README.md` and `CONTRIBUTING.md`, and SHALL introduce no
claim about Exasol that the code does not already implement. Documentation lands after the behaviour
it describes; if a sentence cannot be written truthfully, that is a defect to file, not a sentence to
soften.

#### Scenario: No source, test or configuration file changes

- **WHEN** the diff for this change is listed
- **THEN** the only paths are `README.md` and `CONTRIBUTING.md`

#### Scenario: Documented behaviour is already implemented

- **WHEN** each factual claim added to either document is traced
- **THEN** each resolves to existing code or configuration — the provider registration, the `exasol`
  extra, the compose service, or the fixture module — and none describes intended future behaviour
