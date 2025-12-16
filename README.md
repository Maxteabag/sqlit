# sqlit

**The lazygit of SQL databases.** Connect to Postgres, MySQL, SQL Server, SQLite, Supabase, Turso, and more from your terminal in seconds.

A lightweight TUI for people who just want to run some queries fast.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

### Multi-database Support
![Database Providers](demo-providers.gif)

### Query History
![Query History](demo-history.gif)


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

This is the recommended method. It installs `sqlit-tui` and its dependencies in an isolated environment, preventing any conflicts with your other Python projects.

1.  **Install pipx:** If you don't have pipx, you can install it with:
    ```bash
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath
    ```
    *(You may need to restart your terminal after this step)*

2.  **Install sqlit-tui:**
    ```bash
    pipx install sqlit-tui
    ```

3.  **Install Drivers:** To add database drivers, use `pipx inject`. The application will guide you if a driver is missing, but you can also pre-install them. For example:
    ```bash
    # To add PostgreSQL support
    pipx inject sqlit-tui psycopg2-binary

    # To add MySQL support
    pipx inject sqlit-tui mysql-connector-python
    ```

### Method 2: `pip` (Alternative)

*(Note: To avoid dependency conflicts, installing in a virtual environment is recommended.)*

You can install `sqlit-tui` and drivers directly with `pip` using "extras". The application will guide you if a driver is missing.

```bash
# To install with PostgreSQL and MySQL support
pip install "sqlit-tui[postgres,mysql]"

# To add a driver to an existing installation
pip install "sqlit-tui[mariadb]"

# To install all drivers
pip install "sqlit-tui[all]"
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
sqlit connection create --name "MySqlServer" --db-type mssql --server "localhost" --auth-type sql
sqlit connection create --name "MyPostgres" --db-type postgresql --server "localhost" --username "user" --password "pass"
sqlit connection create --name "MyMySQL" --db-type mysql --server "localhost" --username "user" --password "pass"
sqlit connection create --name "MyCockroach" --db-type cockroachdb --server "localhost" --port "26257" --database "defaultdb" --username "root"
sqlit connection create --name "MyLocalDB" --db-type sqlite --file-path "/path/to/database.db"
sqlit connection create --name "MyTurso" --db-type turso --server "libsql://your-db.turso.io" --password "your-auth-token"

# Connect via SSH tunnel
sqlit connection create --name "RemoteDB" --db-type postgresql --server "db-host" --username "dbuser" --password "dbpass" \
  --ssh-enabled --ssh-host "ssh.example.com" --ssh-username "sshuser" --ssh-auth-type password --ssh-password "sshpass"

# Manage connections
sqlit connection list
sqlit connection delete "MyConnection"
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

Credentials are stored in plain text in a protected directory (`~/.sqlit/`) with restricted file permissions (700/600).

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

While the application will guide you to install missing drivers, you can also pre-install them.

| Database | `pip install` Command | `pipx inject` Command |
| :--- | :--- | :--- |
| SQLite | *(built-in)* | *(built-in)* |
| PostgreSQL | `pip install "sqlit-tui[postgres]"` | `pipx inject sqlit-tui psycopg2-binary` |
| CockroachDB | `pip install "sqlit-tui[cockroachdb]"` | `pipx inject sqlit-tui psycopg2-binary` |
| Supabase | `pip install "sqlit-tui[postgres]"` | `pipx inject sqlit-tui psycopg2-binary` |
| SQL Server | `pip install "sqlit-tui[mssql]"` | `pipx inject sqlit-tui pyodbc` |
| MySQL | `pip install "sqlit-tui[mysql]"` | `pipx inject sqlit-tui mysql-connector-python` |
| MariaDB | `pip install "sqlit-tui[mariadb]"` | `pipx inject sqlit-tui mariadb` |
| Oracle | `pip install "sqlit-tui[oracle]"` | `pipx inject sqlit-tui oracledb` |
| DuckDB | `pip install "sqlit-tui[duckdb]"` | `pipx inject sqlit-tui duckdb` |
| Turso | `pip install "sqlit-tui[turso]"` | `pipx inject sqlit-tui libsql-client`|
| Cloudflare D1 | `pip install "sqlit-tui[d1]"` | `pipx inject sqlit-tui requests` |

**Note:** SQL Server also requires the platform-specific ODBC driver. On your first connection attempt, `sqlit` can help you install it if it's missing.

## License

MIT
