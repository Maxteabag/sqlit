## Why

Exasol is now a registered, unit-tested, integration-tested provider — and it is invisible in
both documents a person reads before touching this repo. `README.md:28` enumerates every supported
engine and does not name Exasol; its Driver Reference table (`README.md:277-297`) tells users which
package to install when a driver is missing and has no `pyexasol` row. `CONTRIBUTING.md:49` names
the enterprise-profile containers as "(Db2, Trino, Presto, Oracle 11g)" and its Environment
Variables section (`CONTRIBUTING.md:82-186`) documents the env vars for eleven engines — neither
mentions the `exasol` compose service or the `EXASOL_*` variables that `tests/fixtures/exasol.py`
actually reads.

Until this lands, a contributor who starts the enterprise profile has no way to know Exasol is in
it, and a user whose connection fails on a missing driver gets no install command. This is plan.md
step 15, the last `todo` in a 15-step plan.

## What Changes

- **Modified** `README.md` — Exasol added to the supported-database sentence at line 28, positioned
  after Teradata to match the connection picker's display order established in plan.md step 6; and a
  `pyexasol` row added to the Driver Reference table with its `pipx inject` and `pip install`
  commands, in the position the table's existing ordering implies.
- **Modified** `CONTRIBUTING.md` — Exasol added to the enterprise-container list at line 49; a new
  **Exasol:** environment-variable table in the Environment Variables section, documenting the six
  variables `tests/fixtures/exasol.py` reads with their real defaults; and a note that the Exasol
  container needs far longer than the "about 30-45 seconds" line 54 quotes for the standard profile.
- No changes to any file under `sqlit/`, `tests/`, `infra/`, `.github/` or `pyproject.toml`. This
  change is documentation only. The behaviour being documented already exists and is verified.

## Capabilities

### New Capabilities

- `exasol-documentation`: the user-facing and contributor-facing documentation surface for the
  Exasol provider — that `README.md` lists Exasol among supported engines and gives the driver
  install command, and that `CONTRIBUTING.md` tells a contributor how to bring up the Exasol test
  container and which environment variables configure the tests against it. Each documented value
  must match the code that reads it, which is the requirement that makes this capability testable
  rather than decorative.

### Modified Capabilities

None. Nothing in `openspec/specs/exasol-adapter`, `exasol-driver-packaging`,
`exasol-integration-coverage`, `exasol-integration-harness`, `exasol-provider-registration` or
`exasol-unit-coverage` changes; this change describes their outcome to readers.

## Impact

- **Documented values are a contract with code, not prose.** Every default in the new env-var table
  is read from a specific line of `tests/fixtures/exasol.py` (`EXASOL_HOST`=`localhost`,
  `EXASOL_PORT`=`8563`, `EXASOL_USER`=`sys`, `EXASOL_PASSWORD`=`exasol`,
  `EXASOL_SCHEMA`=`TEST_SQLIT`, `EXASOL_READY_TIMEOUT`=`300`). A wrong default here is worse than
  no table — it sends a contributor debugging their environment instead of the code.
- **`EXASOL_READY_TIMEOUT` is undocumented elsewhere and has no analogue in any other engine's
  table.** It exists because the step 12-14 session measured `exasol/docker-db` opening port 8563 at
  21s but refusing every login until 101s. Omitting it leaves the one knob a contributor on slow
  hardware will need out of the docs entirely.
- **Boot time is a support question waiting to happen.** `CONTRIBUTING.md:54` says "about 30-45
  seconds"; Exasol needs minutes on a cold pull of a ~4 GB image. A contributor who waits 45 seconds
  and sees connection refused will reasonably conclude the container is broken.
- **Driver Reference table placement**: the table lists 18 of ~30 engines and omits Db2, SAP HANA,
  Teradata, Trino, Presto and RedShift, so Exasol's prose-order neighbours are all absent. See
  design D2 for the ordering rule chosen and why.
- **Upstream review surface**: both files are top-level project documents in `Maxteabag/sqlit`, so
  every line is read by the maintainer. Diff minimalism matters more here than anywhere else in the
  Exasol work — the change must not reflow, reformat or "improve" adjacent rows.
- **Not affected**: no test runs, no CI job, no dependency. Verification is a read-through against
  the code the tables claim to describe, plus the existing markdown lint in pre-commit if it covers
  these files.
