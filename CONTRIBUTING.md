# Contributing

Thank you for considering a contribution to sqlit! This guide walks you through setting up your environment, running the test suite, and understanding the CI expectations.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Maxteabag/sqlit.git
   cd sqlit
   ```

2. Install in development mode with test dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Running Tests

### SQLite Tests (No Docker Required)

SQLite tests can run without any external dependencies:

```bash
pytest tests/ -v -k sqlite
```

### Full Test Suite (Requires Docker)

To run the complete test suite including SQL Server, PostgreSQL, MySQL, MariaDB, FirebirdSQL, Oracle, DuckDB, and CockroachDB tests:

1. Start the test database containers:
   ```bash
   docker compose -f docker-compose.test.yml up -d
   ```

2. Wait for the databases to be ready (about 30-45 seconds), then run tests:
   ```bash
   pytest tests/ -v
   ```

You can leave the containers running between test runs - the test fixtures handle database setup/teardown automatically. Stop them when you're done developing:

```bash
docker compose -f docker-compose.test.yml down
```

### Running Tests for Specific Databases

```bash
pytest tests/ -v -k sqlite      # SQLite only
pytest tests/ -v -k mssql       # SQL Server only
pytest tests/ -v -k PostgreSQL  # PostgreSQL only
pytest tests/ -v -k MySQL       # MySQL only
pytest tests/ -v -k cockroach   # CockroachDB only
pytest tests/ -v -k firebird    # FirebirdSQL only
```

### Environment Variables

The database tests can be configured with these environment variables:

**SQL Server:**
| Variable | Default | Description |
|----------|---------|-------------|
| `MSSQL_HOST` | `localhost` | SQL Server hostname |
| `MSSQL_PORT` | `1434` | SQL Server port |
| `MSSQL_USER` | `sa` | SQL Server username |
| `MSSQL_PASSWORD` | `TestPassword123!` | SQL Server password |

**PostgreSQL:**
| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `testuser` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `TestPassword123!` | PostgreSQL password |
| `POSTGRES_DATABASE` | `test_sqlit` | PostgreSQL database |

**MySQL:**
| Variable | Default | Description |
|----------|---------|-------------|
| `MYSQL_HOST` | `localhost` | MySQL hostname |
| `MYSQL_PORT` | `3306` | MySQL port |
| `MYSQL_USER` | `root` | MySQL username |
| `MYSQL_PASSWORD` | `TestPassword123!` | MySQL password |
| `MYSQL_DATABASE` | `test_sqlit` | MySQL database |

**CockroachDB:**
| Variable | Default | Description |
|----------|---------|-------------|
| `COCKROACHDB_HOST` | `localhost` | CockroachDB hostname |
| `COCKROACHDB_PORT` | `26257` | CockroachDB port |
| `COCKROACHDB_USER` | `root` | CockroachDB username |
| `COCKROACHDB_PASSWORD` | `` | CockroachDB password (empty for the included Docker container) |
| `COCKROACHDB_DATABASE` | `test_sqlit` | CockroachDB database |

**FirebirdSQL:**
| Variable | Default | Description |
|----------|---------|-------------|
| `FIREBIRD_HOST` | `localhost` | Firebird hostname |
| `FIREBIRD_PORT` | `3050` | Firebird port |
| `FIREBIRD_USER` | `testuser` | Firebird username |
| `FIREBIRD_PASSWORD` | `TestPassword123!` | Firebird password |
| `FIREBIRD_DATABASE` | `/var/lib/firebird/data/test_sqlit.fdb` | Firebird database path or alias | 

### CockroachDB Quickstart (Docker)

1. Start the included CockroachDB container:
   ```bash
   docker compose -f docker-compose.test.yml up -d cockroachdb
   ```
2. Create a connection (default container runs insecure mode on port `26257` with `root` user):
   ```bash
   sqlit connection create \
     --name "LocalCockroach" \
     --db-type cockroachdb \
     --server "localhost" \
     --port "26257" \
     --database "defaultdb" \
     --username "root"
   ```
3. Launch sqlit and connect:
   ```bash
   sqlit
   ```

## CI/CD

The project uses GitHub Actions for continuous integration:

- **Build**: Verifies the package builds on Python 3.10-3.13
- **SQLite Tests**: Runs SQLite integration tests (no external dependencies)
- **SQL Server Tests**: Runs SQL Server integration tests with Docker service
- 

### Vision

The core purpose of this application is to read Read&Write to a SQL database.
The core elements to achieve this purpose is: CEQR:

- C: Connecting
- E: Exploring
- Q: Querying
- R: Viewing results

Connecting: Connecting to a server
Exploring: Understanding the structure and content of the databases
Querying: Executing SQL queries
D: Viewing the results of SQL queries

Additionally, we have requirements 'EAFF':

- E: Easy
- A: Aesthetically pleasing
- F: Fun
- F: Fast

If an idea or feature does *not* achieve any of the 'CBQV' elements adhering to all of the 'EAFF' requirements. It does not belong to sqlit.

**[E]asy:**
Sqlit should not require any external documentation at all. It must prioritize intuitiveness above all.

**[A]esthetically pleasing:**
Sqlit should not render one unnecessary pixel. It should prioritize beauty above anything. Minimalism over bloat.

**Fun:**
Sqlit aims make fulfilling its core purpose be an enjoyable experience for the user, even a source of pleasure.

**Fast:**
Sqlit aims to fulfill its core purpose for the user, with intention to giving the user the results they want with as few actions as possible.

Essentially, sqlit aims to do CRUD on SQL really well.

This implies this tool is more suited for developer's daily use than an database administrator.
Every feature in sqlit should have a target audience in which they will use it every time they use sqlit.
If nobody is going to a feature every day. It does not belong to sqlit.
E.g.

1) advanced query performance debugging -> rarely used -> does not belong in sqlit
2) edit cell key-binding -> a audience who will use this every day -> belongs to sqlit

**On complexity:**
Minimalism: sqlit aims to abstract away as much complexity as possible from the user, while giving them enough control to achieve CBQV. sqlit should never do anything under the hood that the user might have interest in understanding. Universal state problems deem for magical fixes. Conditional state problems, explicit user awareness. User should never ask "wait, how did it know?" "why is this here?" "why did it work then, but not now?"

Voluntary advanced usage: Anything beyond most essentials to achieve CEQR should be voluntary to be exposed to. Minimal cogntive overhead. Always assume by default our user just wants to perform CRUD with SQL.

The idea is the user is exposed to an interface that's minimalistic and easy, but if they want to become 'power users' they may dig into command menu or see help and memorize.

Advances features should not be advertised on the main tool bar or anywhere else where the user has no say in whether it's rendered, as they take up space and distract from the most essential features for crud.

One state: There should be no settings or preferences with important exception of interface (aesthetics, keyboard bindings). No settings to enable or disable features for conditional behaviour. Do not include a feature that a user finds annoying. Settings to disable a feature is a symptom of this. Anything beyond essential must be sought after if needed, not disabled if unwanted.

**Keybindings philosophy:**
To make sqlit as fast' as possible, sqlit has a large focus on keybindings.
To make sqlit as 'easy' as possible, all necessary keybindings to do 'CEQR' well, must be visible at all times.
To make sqlit as 'aesthetically pleasing' any keybinding not strictly necessary to perform 'CEQR' in a 'easy' and 'fast' way will be hidden behind help <?> or command menu <space>
Keybindings will favour 'vim' traditions as the core audience is developers who enjoy working in terminals.
We shy away from ^+ commands and will only use them where it is not natural to have a "insert/normal" mode and where input is crucial. (Typical is pop up modals)

**Ideal:**
It should be easy to use for someone who just started using sqlit.
sqlit should provide fun and a feeling of mastery and satisfaction for those who want to achieve it, by becoming a sql-manipulating wizard with creative keybinding combos.

**Designing keybindings decision hierarchy:**

1. Intuitive to learn
2. Harmony (we should think about which keybindings are used in sequence, in typical to flow and maximize user mastery satisfaction and opportunity to combine them fast)
3. Traditions (vim, specifically)

**Example:**
<e> = explorer pane, <q> = query pane, <r> = results pane.
Rationale: E;Q;R satisfies both intuitiveness (each binding is the first letter of the pane), harmony (proximity: qwerty speaks for itself)

- **PostgreSQL Tests**: Runs PostgreSQL integration tests with Docker service
- **MySQL Tests**: Runs MySQL integration tests with Docker service
- **Firebird Tests**: Runs Firebird integration tests with Docker service
- **MariaDB/Oracle/DuckDB/CockroachDB Tests**: Runs the remaining database integration tests with Docker service where applicable
- **Full Test Suite**: Runs all tests across every supported database

Pull requests must pass all CI checks before merging.
