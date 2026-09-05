## 1. Establish the facts before writing any prose

Design D3: documented values are read out of the code, never recalled. Do this group first — its
output is what group 2 and 3 transcribe.

- [x] 1.1 Extract every `EXASOL_`-prefixed name and its literal `os.environ.get` fallback from
      `tests/fixtures/exasol.py` (`grep -n 'EXASOL_' tests/fixtures/exasol.py`). Expect six:
      `EXASOL_HOST`, `EXASOL_PORT`, `EXASOL_USER`, `EXASOL_PASSWORD`, `EXASOL_SCHEMA`,
      `EXASOL_READY_TIMEOUT`. If the set differs from six, the table follows the code, not this
      plan.
- [x] 1.2 Confirm the driver distribution name from `pyproject.toml` (`grep -n 'exasol' pyproject.toml`)
      — the `exasol = [...]` extra is the source of truth for the package the Driver Reference row
      names.
- [x] 1.3 Confirm the compose service name and profile in `infra/docker/docker-compose.test.yml`, so
      the `CONTRIBUTING.md` sentence names a profile that actually starts it.
- [x] 1.4 Record the widest cell in each column of the Driver Reference table (`README.md:277-297`)
      and confirm each Exasol cell is no wider, per design D6 — this is what keeps the insertion
      from reflowing every other row.

## 2. `README.md`

- [x] 2.1 Add `Exasol` to the supported-database sentence at `README.md:28`, immediately after
      `Teradata` (design D1). Change nothing else in the sentence — same engines, same order, same
      trailing `and osquery.`
- [x] 2.2 Insert one Driver Reference row between `Spanner` and `Apache Arrow Flight SQL` (design
      D2): Database `Exasol`, Driver package `pyexasol`, `pipx` cell
      `pipx inject sqlit-tui pyexasol`, `pip` / venv cell `python -m pip install pyexasol`. Pad the
      cells to the existing column widths from task 1.4 so no neighbouring row shifts.
- [x] 2.3 Verify against the spec: `git diff README.md` shows exactly two insertions and zero
      modified lines elsewhere; the package name matches task 1.2.

## 3. `CONTRIBUTING.md`

- [x] 3.1 Add Exasol to the enterprise-container list at `CONTRIBUTING.md:49`, alongside Db2, Trino,
      Presto and Oracle 11g. Leave the `docker compose ... --profile enterprise up -d` command
      below it untouched — it already starts every service in the profile.
- [x] 3.2 Add an `**Exasol:**` table to the Environment Variables section, matching the shape of the
      neighbouring tables (same bold label, same `| Variable | Default | Description |` header, same
      separator row), with one row per variable from task 1.1 and defaults copied from it verbatim.
- [x] 3.3 Add the readiness note with the Exasol material (design D5): Exasol needs minutes rather
      than seconds, and an open port 8563 is not yet a database that will authenticate. Do **not**
      edit the existing "about 30-45 seconds" line — it stays correct for the default profile.
- [x] 3.4 Verify against the spec: the set of variables in the new table equals the set from task
      1.1, and every default is character-identical to the fixture's fallback.

## 4. Verify and close out

- [x] 4.1 `git diff --stat` names exactly two files: `README.md` and `CONTRIBUTING.md`. Any third
      path means something outside this change's scope was touched.
- [x] 4.2 Read the full `git diff` and confirm no table row, list item or paragraph other than the
      four insertions moved or reflowed (design D6).
- [x] 4.3 Run the pre-commit hooks against the two files (`uv run pre-commit run --files README.md
      CONTRIBUTING.md`) — `trailing-whitespace` and `end-of-file-fixer` are the two these edits can
      trip. There is no markdown linter in this repo, so this is the whole automated gate (design
      D7).
- [x] 4.4 Re-read each added claim and confirm it traces to code that exists today — the registered
      provider, the `exasol` extra, the compose service, the fixture module. Nothing may describe
      intended behaviour, and nothing may imply introspection works in the casing/schema cases the
      step 12-14 session found broken.
- [x] 4.5 Mark step 15 `done` in plan.md's Status table, update the progress count to 15 / 15, and
      append the session-log line the plan's protocol requires.
