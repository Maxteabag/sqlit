## Context

sqlit auto-discovers providers: `providers/catalog.py::_discover_providers` walks every subpackage
of `sqlit/domains/connections/providers/` and imports `<name>/provider.py` — skipping subpackages
that have no `provider` module, a tolerance added by the previous change. The moment `provider.py`
exists, the provider is live.

The previous change (`exasol-adapter`, plan.md steps 1-4) landed a complete `ExasolAdapter` with no
`provider.py`, so Exasol is currently inert. This change is the registration step: plan.md's atomic
group `ACT`, steps 5, 6 and 7.

**Why it is atomic.** `tests/test_schema_capabilities.py::TestCatalogConsistency` pins three
invariants at once:

| Test | Assertion | Fails if |
|---|---|---|
| `test_database_type_enum_matches_schema` | `{t.value for t in DatabaseType} == set(get_supported_db_types())` | either the enum member or `provider.py` lands alone |
| `test_provider_schema_ids_match_keys` | `get_connection_schema(t).db_type == t` for every discovered type | `SCHEMA.db_type` is not exactly `"exasol"` |
| `test_display_names_match_schema` | `get_connection_schema(t).display_name == get_display_name(t)` | `SCHEMA.display_name` and `SPEC.display_name` disagree |

Set *equality* is the key word — the enum is not a superset check. There is no ordering of these
three files that keeps the suite green in between, so they ship together.

**Constraints.**

- `pyexasol` is still not installed (the `exasol` extra is plan.md step 8). Registration must not
  need it: everything here is metadata, and the adapter import inside `provider_factory` is lazy.
- No test file is added by this change; its gate is the existing capability suite plus the linters.
- `providers/exasol/adapter.py` is **not** modified. The schema's field names were fixed in the
  previous change by what `connect()` already reads — `authenticator`, `access_token`,
  `refresh_token`, `schema` — so this change adapts the schema to the adapter, not the reverse.

**Reference implementations read for house style:** `providers/teradata/provider.py` and
`providers/hana/provider.py` (the `ProviderSpec` shape and the lazy factory),
`providers/snowflake/schema.py` (an `authenticator` dropdown with conditionally visible credential
fields), `providers/clickhouse/schema.py` (the `+ SSH_FIELDS + TLS_FIELDS` tail).

## Goals / Non-Goals

**Goals:**

- Exasol appears in the connection picker, in `get_supported_db_types()`, and in the CLI.
- The auth dropdown shows exactly the credential fields the selected method needs, and validation
  and the CLI agree with that visibility.
- `tests/test_schema_capabilities.py` stays green at 30 providers.
- No behaviour change for any of the 29 existing providers.
- Registration works with no driver installed.

**Non-Goals:**

- The `exasol` extra, the mypy override, the pytest marker — plan.md step 8.
- Any test file. Exasol's own unit tests are plan.md steps 9-11; this change is gated by the
  existing suite.
- Docker compose service, integration test, CI job — plan.md steps 12-14.
- Docs — plan.md step 15.
- Any change to `adapter.py`.

## Decisions

### D1 — One change, three files, `provider.py` written last

The three files are inseparable (see Context). Within the change the order still matters for the
working tree: `schema.py` and the `config.py` edit first, `provider.py` last. Until `provider.py`
exists, discovery skips the package and the suite is green; the instant it exists, all three
invariants are checked. Writing it last means at most one red interval, at the end, closed by the
gate.

*Alternative considered:* land `schema.py` alone as a "dead" module first. Rejected as pointless —
nothing imports it, so it proves nothing and still leaves the same red interval later.

### D2 — The dropdown field is named `authenticator`, not `auth_type`

`ConnectionConfig.from_dict` special-cases two legacy top-level keys — `auth_type` and
`trusted_connection` — hoisting them into `options` (`domain/config.py:158-161`). A field literally
named `auth_type` would collide with that path and with whatever a legacy MSSQL-era config file
already carries under that key. `authenticator` avoids the collision entirely and mirrors
`providers/snowflake/schema.py`, which made the same choice.

This is also not a free choice here: `adapter.connect()` already reads
`config.get_option("authenticator", "password")`. The name is fixed by the shipped adapter.

### D3 — Declare `username` and `password` explicitly, with `visible_when`

`_username_field()` and `_password_field()` return a **frozen** `SchemaField` with
`visible_when=None`, and `SchemaField` is `@dataclass(frozen=True)`. To hide them under token auth
they must either be rebuilt with `dataclasses.replace` or declared inline. Declared inline, because
that is what `providers/snowflake/schema.py` does for its conditional `password` field, and no
provider in the tree uses `replace` on these helpers.

Hiding them is behaviour, not cosmetics — three separate consumers key off `visible_when`:

| Consumer | Effect of hiding |
|---|---|
| `providers/validation.py:30` | skips `required` checks on hidden fields, so token auth is not blocked by a missing username |
| `cli/helpers.py:65` | `required=True` becomes an argparse-required flag only when `visible_when is None` — so `--username` stays optional |
| `ui/connection_form.py:219`, `ui/validation.py:76`, `ui/field_widgets.py:45` | the field is hidden and skipped in form validation |

`username` keeps `required=True`: under password auth it genuinely is required, and the guard above
means that requirement simply does not apply when the field is hidden. `password` follows the house
pattern of *not* being required — `validation.py:33` explicitly allows an empty `PASSWORD` field so
it can be prompted at connect time.

*Alternative considered:* always show `username`, Snowflake-style, since Snowflake's user is
meaningful under every method. Rejected for Exasol: `connect()` sends `user`/`password` only on the
password branch, so under token auth the field would be visible, CLI-required, and ignored.

### D4 — Append `SSH_FIELDS + TLS_FIELDS`, and set `supports_ssh=True`

`TLS_FIELDS` is what makes `adapter._tls_args()` reachable at all — without a `tls_mode` field,
`get_tls_mode(config)` always sees `default`, and the `require` mode that `exasol/docker-db`'s
self-signed certificate needs would be unselectable. plan.md step 13's integration test connects
with `--tls-mode require`, a CLI flag that exists only because `TLS_FIELDS` is in this tuple.

`SSH_FIELDS` costs nothing — Exasol is a plain TCP endpoint, so sqlit's generic tunnel applies
unmodified, and `supports_ssh=True` matches `hana`, `teradata` and `clickhouse`. `SCHEMA` leaves
`supports_ssh` at its default `True`; `SPEC` states it explicitly, as the other providers do.

### D5 — `display_name` is `"Exasol"` in both `SCHEMA` and `SPEC`

`get_display_name()` resolves from the registered `ProviderSpec`, while
`test_display_names_match_schema` compares that against `SCHEMA.display_name`. The two literals
must match exactly, including case: `"Exasol"` — not `"EXASOL"`, not `"Exasol DB"`. Same for
`db_type` (`"exasol"`) and `default_port` (`"8563"`), each duplicated across the two objects by the
existing house pattern.

*Alternative considered:* have `SPEC` read its `display_name` from `SCHEMA` to remove the
duplication. Rejected — it would deviate from all 29 providers to save one literal, and the
duplication is exactly what the test guards.

### D6 — `DockerDetector` needs `env_vars={}` — plan.md step 7's snippet is invalid

`DockerDetector` (`providers/docker.py:21-28`) declares `env_vars: dict[str, tuple[str, ...]]`
with **no default**, positioned before every defaulted field. The plan's
`DockerDetector(image_patterns=("exasol/docker-db",), default_user="sys")` therefore raises
`TypeError: missing 1 required positional argument` — at *import* time, inside `provider.py`,
inside discovery. The blast radius is all 30 providers, not just Exasol.

`env_vars={}` is the right value, not a placeholder: `exasol/docker-db` takes no credential
environment variables — its `sys` / `exasol` defaults are baked into the image. `get_credentials`
handles the empty mapping natively (`get_first(())` returns `None`, then `default_user` applies),
so a detected container prefills user `sys` and leaves the password to be prompted.

`default_user_requires_password` stays `False`, so `sys` is offered even when no password was
discovered from the environment — matching `postgresql` and `clickhouse`.

*Alternative considered:* also set `default_database="SYS"`. Rejected — Exasol has no database
layer, `supports_multiple_databases` is `False`, and a database value would surface in the endpoint
and in display formatting for no reason.

### D7 — Custom `display_info` rendering `host:port/SCHEMA`

The default (`adapter_provider.py:61-73`) builds `host[:port][/database]` from the TCP endpoint.
Exasol never populates `endpoint.database` — the schema has no `database` field and
`supports_multiple_databases` is `False` — so the default degrades to a bare `host:port` and the
connection list cannot distinguish two connections into the same cluster.

`_display_info` reads `config.get_option("schema", "")` (where `config.py:232-246` deposits it) and
appends `/<schema>` when non-empty, falling back to the default's `host:port` shape otherwise. Only
`motherduck` and `supabase` override this hook today, so the override is deliberate rather than
conventional — justified because `schema` is Exasol's only scoping dimension.

### D8 — The `DATABASE_TYPE_DISPLAY_ORDER` entry is a silent requirement

Two additions to `domain/config.py`, with very different failure modes:

- `DatabaseType.EXASOL` — omitted, `test_database_type_enum_matches_schema` fails loudly.
- `DATABASE_TYPE_DISPLAY_ORDER` — `ui/screens/connection.py:331` assigns
  `db_types = DATABASE_TYPE_DISPLAY_ORDER` and builds the picker's `Select` options from exactly
  that list. Nothing else filters it, and `grep` finds **no test** referencing the constant.
  Omitted, every test still passes and Exasol is simply absent from the picker — the change would
  look complete and deliver nothing.

Placement: `EXASOL = "exasol"` between `DB2` and `FIREBIRD` in the enum (which is alphabetical
apart from the `DB2` and `ORACLE`/`ORACLE_LEGACY` entries), and `DatabaseType.EXASOL` after
`DatabaseType.TERADATA` in the display order, whose comment declares it ordered "sqlite first, then
by popularity" — putting Exasol with the other enterprise engines (`DB2`, `HANA`, `TERADATA`) and
ahead of the cloud warehouses.

### D9 — `default_port="8563"` in both objects

8563 is Exasol's WebSocket port. It appears three times: `_port_field("8563")` (the form placeholder
and default), `SCHEMA.default_port` (consumed by `SchemaConfigValidator.normalize`, which backfills
an empty port), and `SPEC.default_port` (consumed by `get_default_port("exasol")`, which
`adapter.connect()` already calls as its port fallback). All three must agree, and the shipped
adapter fixes the value.

Note the interaction: `SchemaConfigValidator.normalize` backfills the port only when a `port` field
exists in the schema — it does, so a config saved with an empty port is normalised to 8563 before
`connect()` ever needs its own fallback.

### D10 — `provider_factory` imports `ExasolAdapter` lazily

`provider.py` is imported for every provider at discovery, i.e. at startup. A module-scope
`from ...exasol.adapter import ExasolAdapter` would import `adapter.py` — and therefore `ssl` and
the whole adapter module — on every launch, for a provider the user may never select. Every existing
provider defers this into the factory body; matching that keeps startup cost flat.

The factory returns `build_adapter_provider(spec, SCHEMA, ExasolAdapter())`, which instantiates the
adapter. `ExasolAdapter` is concrete as of the previous change, so this cannot raise
`TypeError: Can't instantiate abstract class` — but note that this change is the first code path
that ever instantiates it, so the previous change's static-only gate is effectively cashed here.
`SCHEMA` itself is imported at module scope, as in `teradata`/`hana`.

## Risks / Trade-offs

- **The change is red until the last file lands** (D1) → unavoidable; mitigated by writing
  `provider.py` last and by the gate being a single fast test file.
- **`DockerDetector` misuse would break all 30 providers, not just Exasol** (D6) → caught by the
  gate: `test_schema_capabilities.py` cannot even collect if discovery raises, so a `TypeError`
  here fails loudly rather than silently.
- **A missing display-order entry passes every test** (D8) → mitigated by a spec scenario asserting
  `DatabaseType.EXASOL in DATABASE_TYPE_DISPLAY_ORDER` and by an explicit `uv run sqlit` check in
  the tasks. Adding a completeness test for the constant would be the durable fix, but that is a new
  test for shared behaviour and belongs outside this change.
- **Exasol becomes selectable before `pyexasol` is installable via an extra** (step 8) → connecting
  raises sqlit's normal driver-install prompt, naming an `exasol` extra that does not exist yet, so
  the prompt is momentarily unactionable. Accepted: step 8 has no dependencies and can follow
  immediately; the alternative is holding registration behind a `pyproject.toml` edit for no
  technical reason.
- **Three duplicated literals** (`"exasol"`, `"Exasol"`, `"8563"`) across `SCHEMA` and `SPEC` (D5,
  D9) → house pattern, and two of the three duplications are exactly what
  `test_schema_capabilities.py` verifies.
- **`visible_when` predicates are untested by this change** (D3) → plan.md step 9
  (`tests/.../exasol/test_schema.py`) exists precisely for that and depends on this change. The
  spec states the visibility matrix so step 9 has a contract to test against.

## Migration Plan

No migration. All three edits are additive, and no persisted connection config can carry
`db_type: "exasol"` yet — the type did not exist, and `from_dict` defaults an unknown or missing
`db_type` to `"mssql"`.

Rollback is deleting `provider.py`: discovery then skips the package (the tolerance added by the
previous change), `get_supported_db_types()` returns to 29, and the two `config.py` lines become
inert — though `test_database_type_enum_matches_schema` would then fail on the orphaned enum member,
so a full rollback reverts all three files together, for the same reason the change ships as one.

## Open Questions

None blocking. Two deferred:

- Whether `DATABASE_TYPE_DISPLAY_ORDER` deserves a completeness test asserting it covers
  `DatabaseType`. Out of scope here (see Risks); worth raising in the upstream PR.
- Whether the `schema` field should offer a dropdown populated after connect, given the explorer
  already lists schemas. Cosmetic, and no existing provider does this for a schema field.
