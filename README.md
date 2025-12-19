# sqlit

**The lazygit of SQL databases.** Connect to Postgres, MySQL, SQL Server, SQLite, Supabase, Turso, and more from your terminal in seconds.

A lightweight TUI for people who just want to run some queries fast.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

### Multi-database Support
![Database Providers](demos/demo-providers.gif)

### Query History
![Query History](demos/demo-history.gif)


## Features

- **Connection manager UI** - Save connections, switch between databases without CLI args
- **Just run `sqlit`** - No CLI config needed, pick a connection and go
- **Multi-database out of the box** - SQL Server, PostgreSQL, MySQL, SQLite, MariaDB, Oracle, DuckDB, CockroachDB, Supabase, Turso - no adapters to install
- **SSH tunnels built-in** - Connect to remote databases securely with password or key auth
- **Vim-style editing** - Modal editing for terminal purists
- **Query history** - Automatically saves queries per connection, searchable and sortable
- Context-aware help (no need to memorize keybindings)
- Browse databases, tables, views, and stored procedures
- SQL autocomplete for tables, columns, and procedures
- Multiple auth methods (Windows, SQL Server, Entra ID)
- CLI mode for scripting and AI agents
- Themes (Tokyo Night, Nord, and more)
- Auto-detects and installs ODBC drivers (SQL Server)


## Motivation
I usually do my work in the terminal, but I found myself either having to boot up massively bloated GUI's like SSMS or Vscode for the simple task of merely browsing my databases and doing some queries toward them. For the vast majority of my use cases, I never used any of the advanced features for inspection and debugging that SSMS and other feature-rich clients provide.

I had the unfortunate situation where doing queries became a pain-point due to the massive operation it is to open SSMS and it's lack of intuitive keyboard only navigation.

The problem got severely worse when I switched to Linux and had to rely on VS CODE's SQL extension to access my database. Something was not right.

I tried to use some existing TUI's for SQL, but they were not intuitive for me and I missed the immediate ease of use that other TUI's such as Lazygit provides.

sqlit is a lightweight database TUI that is easy to use and beautiful to look at, just connect and query. It's for you that just wants to run queries toward your database without launching applications that eats your ram and takes time to load up. Sqlit supports SQL Server, PostgreSQL, MySQL, SQLite, MariaDB, Oracle, DuckDB, CockroachDB, Supabase, and Turso, and is designed to make it easy and enjoyable to access your data, not painful.


## Installation

### Method 1: `pipx` (Recommended)
```bash
pipx install sqlit-tui
```

### Method 2: `uv`

```bash
uv tool install sqlit-tui
```

### Method 3: `pip`

```bash
pip install "sqlit-tui"
```

## Usage

```bash
sqlit
```

The keybindings are shown at the bottom of the screen.

### Try it without a database

Want to explore the UI without connecting to a real database? Run with mock data:

```bash
sqlit --mock=sqlite-demo
```

### CLI

```bash
# Run a query
sqlit query -c "MyConnection" -q "SELECT * FROM Users"

# Output as CSV or JSON
sqlit query -c "MyConnection" -q "SELECT * FROM Users" --format csv
sqlit query -c "MyConnection" -f "script.sql" --format json

# Create connections for different databases
sqlit connections add mssql --name "MySqlServer" --server "localhost" --auth-type sql
sqlit connections add postgresql --name "MyPostgres" --server "localhost" --username "user" --password "pass"
sqlit connections add mysql --name "MyMySQL" --server "localhost" --username "user" --password "pass"
sqlit connections add cockroachdb --name "MyCockroach" --server "localhost" --port "26257" --database "defaultdb" --username "root"
sqlit connections add sqlite --name "MyLocalDB" --file-path "/path/to/database.db"
sqlit connections add turso --name "MyTurso" --server "libsql://your-db.turso.io" --password "your-auth-token"

# Connect via SSH tunnel
sqlit connections add postgresql --name "RemoteDB" --server "db-host" --username "dbuser" --password "dbpass" \
  --ssh-enabled --ssh-host "ssh.example.com" --ssh-username "sshuser" --ssh-auth-type password --ssh-password "sshpass"

# Temporary (not saved) connection
sqlit connect sqlite --file-path "/path/to/database.db"

# Provider-specific CLI help
sqlit connect -h
sqlit connect supabase -h
sqlit connections add -h
sqlit connections add supabase -h

# Manage connections
sqlit connections list
sqlit connections delete "MyConnection"
```

## Keybindings

| Key | Action |
|-----|--------|
| `i` | Enter INSERT mode |
| `Esc` | Back to NORMAL mode |
| `e` / `q` / `r` | Focus Explorer / Query / Results |
| `s` | SELECT TOP 100 from table |
| `h` | Query history |
| `d` | Clear query |
| `n` | New query (clear all) |
| `y` | Copy query (when query editor is focused) |
| `v` / `y` / `Y` / `a` | View cell / Copy cell / Copy row / Copy all |
| `Ctrl+Q` | Quit |
| `?` | Help |

### Commands Menu (`<space>`)

| Key | Action |
|-----|--------|
| `<space>c` | Connect to database |
| `<space>x` | Disconnect |
| `<space>z` | Cancel running query |
| `<space>e` | Toggle Explorer |
| `<space>f` | Toggle Maximize |
| `<space>t` | Change theme |
| `<space>h` | Help |
| `<space>q` | Quit |

Autocomplete triggers automatically in INSERT mode. Use `Tab` to accept.

You can also receive autocompletion on columns by typing the table name and hitting "."

## Configuration

Connections and settings are stored in `~/.sqlit/`.

## FAQ

### How are sensitive credentials stored?

Connection details are stored in `~/.sqlit/connections.json`, but passwords are stored in your OS keyring when available (macOS Keychain, Windows Credential Locker, Linux Secret Service).

If a keyring backend isn't available, `sqlit` will ask whether to store passwords as plaintext in `~/.sqlit/` (protected permissions). If you decline, you’ll be prompted when needed.

### How does sqlit compare to Harlequin, Lazysql, etc.?

sqlit is inspired by [lazygit](https://github.com/jesseduffield/lazygit) - you can just jump in and there's no need for external documentation. The keybindings are shown at the bottom of the screen and the UI is designed to be intuitive without memorizing shortcuts.

Key differences:
- **No need for external documentation** - Sqlit embrace the "lazy" approach in that a user should be able to jump in and use it right away intuitively. There should be no setup instructions. If python packages are required for certain adapters, sqlit will help you install them as you need them.
- **No CLI config required** - Just run `sqlit` and pick a connection from the UI
- **Lightweight** - While Lazysql or Harlequin offer more features, I experienced that for the vast majority of cases, all I needed was a simple and fast way to connect and run queries. Sqlit is focused on doing a limited amount of things really well.

## Inspiration

sqlit is built with [Textual](https://github.com/Textualize/textual) and inspired by:
- [lazygit](https://github.com/jesseduffield/lazygit) - Simple  TUI for git
- [lazysql](https://github.com/jorgerojas26/lazysql) - Terminal-based SQL client with connection manager

## Contributing

See `CONTRIBUTING.md` for development setup, testing, CI, and CockroachDB quickstart steps.

### Driver Reference

Most of the time you can just run `sqlit` and connect. If a Python driver is missing, `sqlit` will show (and often run) the right install command for your environment.

| Database | Driver package | `pipx` | `pip` / venv |
| :--- | :--- | :--- | :--- |
| SQLite | *(built-in)* | *(built-in)* | *(built-in)* |
| PostgreSQL / CockroachDB / Supabase | `psycopg2-binary` | `pipx inject sqlit-tui psycopg2-binary` | `python -m pip install psycopg2-binary` |
| SQL Server | `pyodbc` | `pipx inject sqlit-tui pyodbc` | `python -m pip install pyodbc` |
| MySQL | `mysql-connector-python` | `pipx inject sqlit-tui mysql-connector-python` | `python -m pip install mysql-connector-python` |
| MariaDB | `mariadb` | `pipx inject sqlit-tui mariadb` | `python -m pip install mariadb` |
| Oracle | `oracledb` | `pipx inject sqlit-tui oracledb` | `python -m pip install oracledb` |
| DuckDB | `duckdb` | `pipx inject sqlit-tui duckdb` | `python -m pip install duckdb` |
| Turso | `libsql-client` | `pipx inject sqlit-tui libsql-client` | `python -m pip install libsql-client` |
| Cloudflare D1 | `requests` | `pipx inject sqlit-tui requests` | `python -m pip install requests` |

**Note:** SQL Server also requires the platform-specific ODBC driver. On your first connection attempt, `sqlit` can help you install it if it's missing.

## Vision
The core purpose of this application is to read Read&Write to a SQL database.
The core elements to achieve this purpose is: CEQR:
C: Connecting
E: Exploring
Q: Querying
R: Viewing results

Connecting: Connecting to a server
Exploring: Understanding the structure and content of the databases
Querying: Executing SQL queries
D: Viewing the results of SQL queries

Additionally, we have requirements 'EAFF':
E: Easy
A: Aesthetically pleasing
F: Fun
F: Fast

If an idea or feature does *not* achieve any of the 'CBQV' elements adhering to all of the 'EAFF' requirements. It does not belong to sqlit.


[E]asy:
Sqlit should not require any external documentation at all. It must prioritize intuitiveness above all.

[A]esthetically pleasing:
Sqlit should not render one unnecessary pixel. It should prioritize beauty above anything. Minimalism over bloat.

Fun:
Sqlit aims make fulfilling its core purpose be an enjoyable experience for the user, even a source of pleasure.

Fast:
Sqlit aims to fulfill its core purpose for the user, with intention to giving the user the results they want with as few actions as possible.


Essentially, sqlit aims to do CRUD on SQL really well.

This implies this tool is more suited for developer's daily use than an database administrator.
Every feature in sqlit should have a target audience in which they will use it every time they use sqlit.
If nobody is going to a feature every day. It does not belong to sqlit.
E.g.
1) advanced query performance debugging -> rarely used -> does not belong in sqlit
2) edit cell key-binding -> a audience who will use this every day -> belongs to sqlit

On complexity:
Minimalism: sqlit aims to abstract away as much complexity as possible from the user, while giving them enough control to achieve CBQV. sqlit should never do anything under the hood that the user might have interest in understanding. Universal state problems deem for magical fixes. Conditional state problems, explicit user awareness. User should never ask "wait, how did it know?" "why is this here?" "why did it work then, but not now?"

Voluntary advanced usage: Anything beyond most essentials to achieve CEQR should be voluntary to be exposed to. Minimal cogntive overhead. Always assume by default our user just wants to perform CRUD with SQL.

The idea is the user is exposed to an interface that's minimalistic and easy, but if they want to become 'power users' they may dig into command menu or see help and memorize.

Advances features should not be advertised on the main tool bar or anywhere else where the user has no say in whether it's rendered, as they take up space and distract from the most essential features for crud.

One state: There should be no settings or preferences with important exception of interface (aesthetics, keyboard bindings). No settings to enable or disable features for conditional behaviour. Do not include a feature that a user finds annoying. Settings to disable a feature is a symptom of this. Anything beyond essential must be sought after if needed, not disabled if unwanted.



Keybindings philosophy:
To make sqlit as fast' as possible, sqlit has a large focus on keybindings.
To make sqlit as 'easy' as possible, all necessary keybindings to do 'CEQR' well, must be visible at all times.
To make sqlit as 'aesthetically pleasing' any keybinding not strictly necessary to perform 'CEQR' in a 'easy' and 'fast' way will be hidden behind help <?> or command menu <space>
Keybindings will favour 'vim' traditions as the core audience is developers who enjoy working in terminals.
We shy away from ^+ commands and will only use them where it is not natural to have a "insert/normal" mode and where input is crucial. (Typical is pop up modals)

Ideal:
It should be easy to use for someone who just started using sqlit.
sqlit should provide fun and a feeling of mastery and satisfaction for those who want to achieve it, by becoming a sql-manipulating wizard with creative keybinding combos.

Designing keybindings decision hierarchy:
1. Intuitive to learn
2. Harmony (we should think about which keybindings are used in sequence, in typical to flow and maximize user mastery satisfaction and opportunity to combine them fast)
3. Traditions (vim, specifically)

Example:
<e> = explorer pane, <q> = query pane, <r> = results pane.
Rationale: E;Q;R satisfies both intuitiveness (each binding is the first letter of the pane), harmony (proximity: qwerty speaks for itself)



## License

MIT
