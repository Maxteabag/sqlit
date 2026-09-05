## 1. Driver packaging

Corresponds to plan.md step 8. Unblocks groups 3 and 4.

- [x] 1.1 Add `exasol = ["pyexasol>=2.0.0"]` to `[project.optional-dependencies]` in
      `pyproject.toml`, placed with the other single-provider extras (near `hana` / `teradata`).
- [x] 1.2 Add `"pyexasol>=2.0.0"` to the aggregate `all` extra. Do **not** add it to
      `[project].dependencies` — the lazy import must keep producing sqlit's install prompt.
- [x] 1.3 Add `"pyexasol"` to the `[[tool.mypy.overrides]]` `module` list that sets
      `ignore_missing_imports`. Design D4: this is inert today (mypy excludes `tests/` and `sqlit/`
      names the driver only in a string literal) and is added for consistency with the equally lazy
      `hdbcli` and `teradatasql`.
- [x] 1.4 Add `"exasol: Exasol database tests"` to `[tool.pytest.ini_options].markers`, matching the
      wording of the neighbouring per-database markers. Design D7: nothing in this change uses it;
      it is registered ahead of plan step 13.
- [x] 1.5 Run `uv sync --extra exasol` and confirm it resolves without an error naming Python 3.15
      (design D6 — `pyexasol` caps at `<3.15`, sqlit's `requires-python` has no ceiling). If it
      fails, apply the D6 escape hatch: an inline `; python_version < '3.15'` marker on the **`all`**
      entry only, and record it in the plan's Session log.
- [x] 1.6 Verify the driver is importable: `uv run python -c "import pyexasol; print(pyexasol.__version__)"`.
      Record the resolved version in the plan's Session log — the spec's lower bound is `>=2.0.0`
      but every API detail was verified against 2.3.2.
- [x] 1.7 Confirm `uv.lock` gained a `pyexasol` entry, and check whether `uv` attached a
      `python_full_version < '3.15'` marker to it (design D6).
- [x] 1.8 Note the unrelated lockfile drift for the PR description: `uv.lock` on this branch also
      drops the stale `mariadb` package, because `HEAD`'s `mariadb` extra already points at
      `PyMySQL`. Design D5 — do not try to isolate it, and do not hand-edit `uv.lock`.
- [x] 1.9 Verify: `uv run mypy sqlit` is clean and `uv run ruff check sqlit` is clean.
      **Remember mypy does not verify 1.3** (design D4); 1.6 is that task's real check.

## 2. Test package skeleton

- [x] 2.1 Create `tests/connections/providers/exasol/__init__.py`, empty, matching
      `tests/connections/providers/hana/__init__.py`.
- [x] 2.2 Confirm `uv run pytest tests/connections/providers/exasol/ -v` collects cleanly (zero
      tests, no collection error) before any test file is added.

## 3. Schema visibility tests

Corresponds to plan.md step 9. No driver involved.

- [x] 3.1 Create `tests/connections/providers/exasol/test_schema.py` importing `SCHEMA` from
      `providers.exasol.schema`, with a helper that maps a form-values dict to the set of visible
      field names — a field is visible when `visible_when` is `None` or returns `True`.
- [x] 3.2 Test `{"authenticator": "password"}`: `username` and `password` visible, `access_token`
      and `refresh_token` hidden.
- [x] 3.3 Test `{"authenticator": "access_token"}`: `access_token` visible; `username`, `password`
      and `refresh_token` hidden.
- [x] 3.4 Test `{"authenticator": "refresh_token"}`: `refresh_token` visible; `username`,
      `password` and `access_token` hidden.
- [x] 3.5 Test the empty dict: visibility matches the `password` case, since each predicate defaults
      its lookup to `"password"`.
- [x] 3.6 Test that `server`, `port`, `authenticator` and `schema` carry no `visible_when` and stay
      visible under every authenticator value.
- [x] 3.7 Verify: `uv run pytest tests/connections/providers/exasol/test_schema.py -v`.

## 4. Connect and TLS tests

Corresponds to plan.md step 10. Depends on group 1.

- [x] 4.1 Create `tests/connections/providers/exasol/test_connect.py` with a helper that runs
      `ExasolAdapter().connect(config)` under
      `patch.dict("sys.modules", {"pyexasol": MagicMock()})` and returns the recorded
      `connect` kwargs. Design D2 — seed `sys.modules`; do **not** patch
      `_import_driver_module`, and do **not** rely on the real `pyexasol` being installed.
- [x] 4.2 Add a `ConnectionConfig` builder taking `options` and `extra_options`, building a
      `TcpEndpoint` the way `tests/unit/test_extra_options_passthrough.py` does.
- [x] 4.3 Test password auth (both explicit `"password"` and the unset default): `user` and
      `password` present from the endpoint, **and** `"access_token" not in kwargs` and
      `"refresh_token" not in kwargs`. Design D3 — absence, not emptiness.
- [x] 4.4 Test `authenticator == "access_token"`: `access_token` present; `"user"`, `"password"`
      and `"refresh_token"` all absent as keys.
- [x] 4.5 Test `authenticator == "refresh_token"`: `refresh_token` present; `"user"`, `"password"`
      and `"access_token"` all absent as keys.
- [x] 4.6 Test `dsn == "<host>:<port>"` from the endpoint, and that an endpoint with no port falls
      back to `8563` via `get_default_port("exasol")`.
- [x] 4.7 Test `schema` forwarding: a set `schema` option appears verbatim; an unset one appears as
      the empty string rather than being omitted. Also assert `autocommit is True`.
- [x] 4.8 Test that a config whose `tcp_endpoint` is `None` raises `ValueError` and never calls the
      fake driver's `connect`.
- [x] 4.9 Test `tls_mode="disable"`: `encryption is False` and no `websocket_sslopt` key.
- [x] 4.10 Test `tls_mode="default"` and unset: `encryption is True` and no `websocket_sslopt` key.
- [x] 4.11 Test `tls_mode="require"`: `encryption is True` and
      `websocket_sslopt == {"cert_reqs": ssl.CERT_NONE}`.
- [x] 4.12 Test `verify-ca` and `verify-full`: `encryption is True` and
      `websocket_sslopt["cert_reqs"] == ssl.CERT_REQUIRED`.
- [x] 4.13 Test that a verifying mode with `tls_ca` / `tls_cert` / `tls_key` set forwards them as
      `ca_certs` / `certfile` / `keyfile`, and that with those options unset or whitespace-only
      `websocket_sslopt` contains **only** `cert_reqs`.
- [x] 4.14 Test `extra_options` passthrough of an unknown key, and that `extra_options` overrides a
      computed kwarg such as `encryption` (it is applied last).
- [x] 4.15 Verify: `uv run pytest tests/connections/providers/exasol/test_connect.py -v`.
- [x] 4.16 Confirm the file is driver-independent: the tests still pass in an environment without
      the `exasol` extra (`uv run --no-sync` against a plain `--group test` environment, or a
      temporary rename of the installed package). This is the constraint the default CI job imposes.

## 5. Adapter behaviour tests

Corresponds to plan.md step 11. Depends on group 1.

- [x] 5.1 Create `tests/connections/providers/exasol/test_adapter.py` with a `mock_conn` fixture
      whose `conn.meta.list_*` return **lists of dicts with UPPERCASE keys** and whose
      `conn.meta.execute_snapshot` returns an object with a `fetchall()`. Feeding tuples here would
      pass against an index-based implementation and pin nothing.
- [x] 5.2 Add a statement-mock helper that **always sets `result_type` explicitly**. On a bare
      `MagicMock`, `result_type != "resultSet"` is trivially true, so an unset value makes
      result-set tests pass while asserting nothing (design risk 2).
- [x] 5.3 Test `get_tables` maps `TABLE_SCHEMA` / `TABLE_NAME` to `(schema, name)` tuples in order.
- [x] 5.4 Test `get_views` maps `VIEW_SCHEMA` / `VIEW_NAME` the same way.
- [x] 5.5 Test `get_columns` combines the primary-key snapshot with `list_columns`: `ID` flagged
      primary key, `NAME` not, `list_columns` order preserved.
- [x] 5.6 Test the primary-key lookup goes through `conn.meta.execute_snapshot` (not `conn.execute`),
      filters on `CONSTRAINT_TYPE = 'PRIMARY KEY'`, and passes schema and table as query parameters
      rather than interpolating them.
- [x] 5.7 Test a table with no primary key: every `ColumnInfo.is_primary_key` is false.
- [x] 5.8 Test that `get_columns` with no schema passes `""` to `list_columns`, with a comment
      naming design D8 — this pins a deliberate, unreachable-from-the-UI choice, not a desirable one.
- [x] 5.9 Test `get_procedures` snapshot-executes `SYS.EXA_ALL_SCRIPTS` filtered to
      `SCRIPT_TYPE = 'SCRIPTING'` and returns `SCRIPT_NAME` values.
- [x] 5.10 Test `get_databases`, `get_indexes`, `get_triggers` and `get_sequences` each return `[]`
      **and** touch the connection mock not at all (`mock_conn.mock_calls == []`).
- [x] 5.11 Test the `rowCount` path of `execute_query`: returns `([], [], False)` and calls neither
      `fetchall` nor `fetchmany` (`stmt.fetchall.assert_not_called()`).
- [x] 5.12 Test the `resultSet` path with `max_rows` unset: columns from `column_names()`, all rows
      as tuples, `truncated` false.
- [x] 5.13 Test the truncation boundary: with `max_rows=2`, two available rows give 2 rows and
      `truncated` false; three available rows give 2 rows and `truncated` true.
- [x] 5.14 Test that `fetchmany` is called with `max_rows + 1`.
- [x] 5.15 Test `execute_non_query` **calls** `stmt.rowcount()` as a method and returns an `int`,
      and that no `commit` is issued on the connection.
- [x] 5.16 Test `execute_test_query` runs `conn.execute("SELECT 1")`, takes `fetchval()`, and never
      accesses `conn.cursor`.
- [x] 5.17 Test `quote_identifier` on a plain identifier and on one containing a double quote
      (doubled inside the quoted result).
- [x] 5.18 Test `build_select_query` with a schema (quoted `"S"."T"` plus `LIMIT`) and without one
      (table only, no leading dot).
- [x] 5.19 Verify: `uv run pytest tests/connections/providers/exasol/ -v` — all three files green.

## 6. Change gate and plan bookkeeping

- [x] 6.1 Run `uv run ruff check sqlit tests` and `uv run mypy sqlit`; both clean relative to the
      pre-change baseline.
- [x] 6.2 Confirm no file under `sqlit/` was modified by this change: `git status` shows only
      `pyproject.toml`, `uv.lock` and the new test files (plus the pre-existing modifications to
      `domain/config.py` and `providers/catalog.py` from earlier changes).
- [x] 6.3 Run the default unit job's command from `.github/workflows/ci.yml:70-82` verbatim and
      confirm the new tests are collected and pass with no new failures. Pre-existing
      Windows-environment failures recorded in the plan's Session log stay as they are.
- [x] 6.4 Confirm `uv run pytest --markers` lists `exasol`, and that `uv run pytest -m exasol`
      selects zero tests (expected until plan step 13).
- [x] 6.5 If any test surfaced an adapter bug, record it in the plan's Session log as a finding —
      do **not** fix `sqlit/` source in this change (design Non-Goals).
- [x] 6.6 In `plan.md`, set steps 8, 9, 10 and 11 to `done` in the Status table and update the
      progress count to `11 / 15 done`.
- [x] 6.7 Append a `plan.md` Session log row recording: step 10's open item resolved via
      `patch.dict("sys.modules", ...)` (design D2); the mypy override being inert (D4); the
      `pyexasol` version actually resolved; whether the D6 Python-marker escape hatch was needed;
      and the `mariadb` lockfile drift to disclose in the PR (D5).
