# IBM DB2 for i Support

This adapter provides support for IBM DB2 for i (formerly IBM i/AS400/iSeries) using the ODBC driver, which does not require an IBM license.

## Prerequisites

### ODBC Driver Installation

You need to install the IBM i Access ODBC Driver on your system. This driver is freely available and does not require an IBM license.

#### macOS
1. Download IBM i Access Client Solutions from IBM
2. Install the ODBC driver component
3. The driver will typically be named "IBM i Access ODBC Driver"

#### Linux
1. Download IBM i Access ODBC Driver for Linux from IBM
2. Follow the installation instructions for your distribution
3. Verify installation with: `odbcinst -q -d`

#### Windows
1. Download IBM i Access ODBC Driver for Windows from IBM
2. Run the installer
3. The driver will be registered automatically

### Python Dependencies

Install the required Python package:

```bash
pip install sqlit-tui[db2i]
```

Or install pyodbc directly:

```bash
pip install pyodbc
```

## Connection Configuration

### Basic Connection

```python
{
    "name": "my_db2i",
    "db_type": "db2i",
    "host": "your.ibmi.server.com",
    "username": "your_username",
    "password": "your_password",
    "database": "MYLIB"  # Optional: default library/schema
}
```

### Custom ODBC Driver

If you have a different ODBC driver installed, you can specify it:

```python
{
    "name": "my_db2i",
    "db_type": "db2i",
    "host": "your.ibmi.server.com",
    "username": "your_username",
    "password": "your_password",
    "database": "MYLIB",
    "extra_options": {
        "odbc_driver": "iSeries Access ODBC Driver"
    }
}
```

### Connection String Format

The adapter builds an ODBC connection string in the following format:

```
DRIVER={IBM i Access ODBC Driver};SYSTEM=hostname;UID=username;PWD=password;DBQ=library;
```

## Features

### Supported Operations

- ✅ Connect to IBM DB2 for i via ODBC
- ✅ Query execution
- ✅ Browse libraries (databases)
- ✅ Browse tables and views
- ✅ View table columns with data types
- ✅ Stored procedures
- ✅ Sequences
- ✅ Indexes
- ✅ Triggers
- ✅ Cross-library queries

### System Catalogs

The adapter queries the following IBM i system catalogs:

- `QSYS2.SYSTABLES` - Tables and views
- `QSYS2.SYSVIEWS` - View definitions
- `QSYS2.SYSCOLUMNS` - Column information
- `QSYS2.SYSROUTINES` - Stored procedures and functions
- `QSYS2.SYSINDEXES` - Index information
- `QSYS2.SYSTRIGGERS` - Trigger definitions
- `QSYS2.SYSSEQUENCES` - Sequence objects

### Differences from Standard DB2

IBM DB2 for i has some differences from standard DB2:

1. **Libraries vs Databases**: DB2 for i uses "libraries" instead of traditional databases
2. **System Catalogs**: Uses QSYS2 system catalog instead of SYSCAT
3. **ODBC Driver**: Uses IBM i Access ODBC Driver instead of DB2 CLI driver
4. **No License Required**: The ODBC driver is freely available

## Troubleshooting

### Driver Not Found

If you get an error about the ODBC driver not being found:

1. Verify the driver is installed: `odbcinst -q -d` (Linux/macOS)
2. Check the exact driver name in your system
3. Specify the correct driver name in the connection configuration

### Connection Timeout

If connections are timing out:

1. Verify network connectivity to the IBM i server
2. Check firewall rules
3. Ensure the ODBC driver is properly configured
4. Try specifying a port if required by your network configuration

### Character Encoding Issues

If you encounter character encoding problems:

1. Add encoding options to `extra_options`:
   ```python
   "extra_options": {
       "CHARSET": "UTF-8"
   }
   ```

## URL Scheme

You can also use a URL connection string:

```
db2i://username:password@hostname/library
```

## Testing

To run tests for the DB2 for i adapter:

```bash
# Set environment variables
export DB2I_HOST=your.ibmi.server.com
export DB2I_USER=your_username
export DB2I_PASSWORD=your_password
export DB2I_LIBRARY=QGPL

# Run tests
pytest -m db2i
```

## Additional Resources

- [IBM i Access ODBC Driver Documentation](https://www.ibm.com/docs/en/i/)
- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki)
- [IBM i SQL Reference](https://www.ibm.com/docs/en/i/7.4?topic=reference-sql)
