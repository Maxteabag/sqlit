<p align="center">
  <img src="assets/favorites/logo.png" alt="sqlit logo" width="200">
</p>

<h1 align="center">sqlit</h1>

<p align="center">
  <strong>The lazygit of SQL databases.</strong><br>
  Connect and query your database from your terminal in seconds.
</p>

<p align="center">
  <a href="https://github.com/Maxteabag/sqlit/stargazers"><img src="https://img.shields.io/github/stars/Maxteabag/sqlit?style=flat&color=yellow" alt="GitHub Stars"></a>
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
</p>

---

### *Connect*
Sqlit supports all major DBMS's: SQL Server, PostgreSQL, MySQL, SQLite, MariaDB, FirebirdSQL, Oracle, DuckDB, CockroachDB, ClickHouse, Snowflake, Supabase, CloudFlare D1 and Turso.
![Database Providers](demos/demo-providers.gif)

### **Query**
Syntax highlighting. History. VIM-like combos.
![Query History](demos/demo-history.gif)
##### **Results**
 Inspect data, filter based on content, supports fuzzy search, loads millions of rows without any problem.
![Filter results](demos/demo-filter/demo-filter.gif)

##### **Docker discovery**
Finds running docker sql resources. Connect to your local test servers in seconds without any configuation.
![Filter results](demos/demo-docker-picker.gif)



## Features

- **Connection manager** - Save connections, switch between databases without CLI args
- **Just run `sqlit`** - No CLI config needed, pick a connection and go
- **Multi-database out of the box** - SQL Server, PostgreSQL, MySQL, SQLite, MariaDB, FirebirdSQL, Oracle, DuckDB, CockroachDB, ClickHouse, Snowflake, Supabase, CloudFlare D1, Turso - no adapters to install
- **Docker** Connect directly to database docker container
- **SSH tunnels built-in** - Connect to remote databases securely with password or key auth
- Secure credentials - Stores your credentials on your OS's credentials store
- **Vim-style editing** - Modal editing for terminal purists
- **Query history** - Automatically saves queries per connection, searchable and sortable
- **Filter results** - Find the data you're looking for without squinting your eyes in the results view
- **Context-aware help** - No need to memorize keybindings
- **Browse databases** - View tables, views, stored procedures, indexes, triggers and sequences
- **Autocomplete** - tables, columns, and procedures
- **CLI mode** - executing sql has never been this easy
- Themes (Rose Pine, Tokyo Night, Nord, Gruvbox)
- **Dependency wizard** - User friendly installation for required packages and drivers


## Motivation

Throughout my career, the undesputed truth was that SSMS was the only respectable way to access a database. It didn't matter that I wasn't a DBA, or that I didn't need complex performance graphs. I was expected to install a gigabyte-heavy behemoth that took ages to launch all for the mere purpose of running a few queries to update and view a couple of rows.

When I switched to Linux, I was suddenly unable to return to the devil I know, and I asked myself: _how do I access my data now?_

The popular answer was VS Code's SQL extension. But why should we developers launch a heavy Electron app designed for coding just to execute SQL?

I had recently grown fond of Terminal UI's for their speed and keybinding focus. I looked for SQL TUIs, but the options were sparse. The ones I found lacked the user-friendliness and immediate "pick-up-and-go" nature of tools I loved, like `lazygit`, and I shortly returning to vscode sql extension.

Something wasn't right. I asked myself, why is it that running SQL queries can't be enjoyable? So I created `sqlit`.

`sqlit` is for the developer who just wants to query their database with a user friendly UI without their RAM being eaten alive. It is a lightweight, beautiful, and keyboard-driven TUI designed to make accessing your data enjoyable, fast and easy like it should be-- all from inside your favorite terminal.

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
sqlit connections add firebird --name "MyFirebird" --server "localhost" --username "user" --password "pass" --database "employee"

# Connect via SSH tunnel
sqlit connections add postgresql --name "RemoteDB" --server "db-host" --username "dbuser" --password "dbpass" \
  --ssh-enabled --ssh-host "ssh.example.com" --ssh-username "sshuser" --ssh-auth-type password --ssh-password "sshpass"

# Temporary (not saved) connection
sqlit connect sqlite --file-path "/path/to/database.db"

# Connect via URL - scheme determines database type (postgresql://, mysql://, sqlite://, etc.)
sqlit postgresql://user:pass@localhost:5432/mydb
sqlit mysql://root@localhost/testdb
sqlit sqlite:///path/to/database.db

# Save a connection via URL
sqlit connections add --url dbtype://user:pass@host/db --name "MyDB"

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

If a keyring backend isn't available, `sqlit` will ask whether to store passwords as plaintext in `~/.sqlit/` (protected permissions). If you decline, you'll be prompted when needed.

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
| ClickHouse | `clickhouse-connect` | `pipx inject sqlit-tui clickhouse-connect` | `python -m pip install clickhouse-connect` |
| Turso | `libsql-client` | `pipx inject sqlit-tui libsql-client` | `python -m pip install libsql-client` |
| Cloudflare D1 | `requests` | `pipx inject sqlit-tui requests` | `python -m pip install requests` |
| Snowflake | `snowflake-connector-python` | `pipx inject sqlit-tui snowflake-connector-python` | `python -m pip install snowflake-connector-python` |
| Firebird | `firebirdsql` | `pip install firebirdsql` | `python -m pip install firebirdsql` |

**Note:** SQL Server also requires the platform-specific ODBC driver. On your first connection attempt, `sqlit` can help you install it if it's missing.

### SSH Tunnel Support

SSH tunnel functionality requires additional dependencies. Install with the `ssh` extra:

| Method | Command |
| :--- | :--- |
| pipx | `pipx install 'sqlit-tui[ssh]'` |
| uv | `uv tool install 'sqlit-tui[ssh]'` |
| pip | `pip install 'sqlit-tui[ssh]'` |

If you try to create an SSH connection without these dependencies, sqlit will detect this and show you the exact command to install them for your environment.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Maxteabag/sqlit&type=Date)](https://star-history.com/#Maxteabag/sqlit&Date)

## License

MIT
