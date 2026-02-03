# Quick Start: IBM DB2 for i

This guide will help you quickly get started with IBM DB2 for i support in sqlit.

## Prerequisites Checklist

- [ ] IBM i Access ODBC Driver installed on your system
- [ ] Network access to your IBM i server
- [ ] Valid credentials (username and password)
- [ ] Python 3.10 or higher

## Installation

### Step 1: Install sqlit with DB2i support

```bash
pip install sqlit-tui[db2i]
```

Or if you want all database drivers:

```bash
pip install sqlit-tui[all]
```

### Step 2: Verify ODBC Driver Installation

**macOS/Linux:**
```bash
odbcinst -q -d | grep -i "ibm i"
```

**Expected output:**
```
[IBM i Access ODBC Driver]
```

If the driver is not found, download and install it from IBM.

## Quick Connection Test

### Using Python

```python
from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.providers.catalog import get_provider

# Create connection config
config = ConnectionConfig(
    name="test_connection",
    db_type="db2i",
    tcp_endpoint=TcpEndpoint(
        host="your.ibmi.server.com",
        database="QGPL",  # Default library
        username="your_username",
        password="your_password",
    ),
)

# Get provider and connect
provider = get_provider("db2i")
conn = provider.connection_factory.connect(config)

# Test query
columns, rows, truncated = provider.query_executor.execute_query(
    conn, 
    "SELECT * FROM QSYS2.SYSTABLES FETCH FIRST 5 ROWS ONLY"
)

print(f"Successfully connected! Retrieved {len(rows)} rows")
print(f"Columns: {columns}")

conn.close()
```

### Using sqlit CLI

If sqlit has a CLI interface, you can use:

```bash
sqlit connect db2i://username:password@hostname/library
```

## Common Connection Options

### Minimal Connection (with defaults)
```python
{
    "db_type": "db2i",
    "host": "ibmi.example.com",
    "username": "myuser",
    "password": "mypass"
}
```

### With Default Library
```python
{
    "db_type": "db2i",
    "host": "ibmi.example.com",
    "database": "MYLIB",  # Sets default library for queries
    "username": "myuser",
    "password": "mypass"
}
```

### With Custom ODBC Driver
```python
{
    "db_type": "db2i",
    "host": "ibmi.example.com",
    "username": "myuser",
    "password": "mypass",
    "extra_options": {
        "odbc_driver": "iSeries Access ODBC Driver"
    }
}
```

### With Character Encoding
```python
{
    "db_type": "db2i",
    "host": "ibmi.example.com",
    "username": "myuser",
    "password": "mypass",
    "extra_options": {
        "CHARSET": "UTF-8",
        "NAM": "1"  # SQL naming convention
    }
}
```

## Troubleshooting

### Error: "Data source name not found"

**Cause:** ODBC driver is not installed or not found.

**Solution:**
1. Verify ODBC driver installation: `odbcinst -q -d`
2. Install IBM i Access ODBC Driver if missing
3. Specify the exact driver name in `extra_options`:
   ```python
   "extra_options": {"odbc_driver": "Your Driver Name Here"}
   ```

### Error: "Connection refused" or "Timeout"

**Cause:** Network connectivity issues.

**Solution:**
1. Verify the hostname/IP is correct
2. Check firewall rules
3. Ensure the IBM i server is accessible from your network
4. Try pinging the server: `ping ibmi.example.com`

### Error: "Login failed" or "Invalid credentials"

**Cause:** Incorrect username or password.

**Solution:**
1. Verify credentials with your IBM i administrator
2. Ensure the user has appropriate permissions
3. Check if the password has special characters that need escaping

### Error: "Library not found"

**Cause:** The specified default library doesn't exist.

**Solution:**
1. Verify the library name is correct (case-sensitive on IBM i)
2. Check if you have access to the library
3. Try connecting without specifying a default library first

## Sample Queries

### List All Libraries
```sql
SELECT DISTINCT TABLE_SCHEMA 
FROM QSYS2.SYSTABLES 
WHERE TABLE_SCHEMA NOT LIKE 'Q%' 
ORDER BY TABLE_SCHEMA
```

### List Tables in a Library
```sql
SELECT TABLE_NAME 
FROM QSYS2.SYSTABLES 
WHERE TABLE_SCHEMA = 'MYLIB' 
  AND TABLE_TYPE = 'T'
ORDER BY TABLE_NAME
```

### View Table Columns
```sql
SELECT COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
FROM QSYS2.SYSCOLUMNS
WHERE TABLE_SCHEMA = 'MYLIB'
  AND TABLE_NAME = 'MYTABLE'
ORDER BY ORDINAL_POSITION
```

### List Stored Procedures
```sql
SELECT ROUTINE_NAME, ROUTINE_SCHEMA
FROM QSYS2.SYSROUTINES
WHERE ROUTINE_TYPE = 'PROCEDURE'
  AND ROUTINE_SCHEMA NOT LIKE 'Q%'
ORDER BY ROUTINE_NAME
```

## Next Steps

1. **Read the full documentation**: See [README.md](sqlit/domains/connections/providers/db2i/README.md)
2. **Check out examples**: See [example.py](sqlit/domains/connections/providers/db2i/example.py)
3. **Run tests**: `pytest -m db2i` (requires test environment)

## Getting Help

- IBM i SQL Reference: https://www.ibm.com/docs/en/i/7.4?topic=reference-sql
- pyodbc Documentation: https://github.com/mkleehammer/pyodbc/wiki
- IBM i Access Client Solutions: https://www.ibm.com/support/pages/ibm-i-access-client-solutions

## Environment Variables for Testing

If you want to run the integration tests:

```bash
export DB2I_HOST=ibmi.example.com
export DB2I_USER=testuser
export DB2I_PASSWORD=testpass
export DB2I_LIBRARY=TESTLIB
export DB2I_ODBC_DRIVER="IBM i Access ODBC Driver"

pytest -m db2i
```
