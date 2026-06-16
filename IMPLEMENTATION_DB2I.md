# IBM DB2 for i Support - Implementation Summary

## Overview

This implementation adds support for IBM DB2 for i (formerly AS/400, iSeries, System i) using the pyodbc driver with the IBM i Access ODBC Driver. This solution **does not require an IBM license** as it uses the freely available IBM i Access ODBC Driver.

## What Was Implemented

### 1. New Database Adapter
**Location:** `sqlit/domains/connections/providers/db2i/`

#### Files Created:
- `adapter.py` - Main adapter implementation using pyodbc
- `provider.py` - Provider registration
- `schema.py` - Connection schema definition
- `README.md` - Comprehensive documentation
- `example.py` - Usage examples
- `__init__.py` - Package initialization

### 2. Key Features

The adapter provides full support for:

✅ **Connection Management**
- Connect using IBM i Access ODBC Driver (no license required)
- Support for custom ODBC driver names
- Optional port specification
- Default library/schema configuration
- Extra ODBC connection options

✅ **Schema Operations**
- List libraries (equivalent to databases)
- Browse tables and views
- View column definitions with data types
- Inspect primary keys
- View indexes (with uniqueness indicators)
- View triggers
- View sequences
- List stored procedures

✅ **Query Execution**
- Execute SQL queries
- Handle result sets
- Row limiting support
- Cross-library queries

### 3. System Catalog Support

The adapter queries these IBM i system catalogs:
- `QSYS2.SYSTABLES` - Tables and views metadata
- `QSYS2.SYSVIEWS` - View definitions
- `QSYS2.SYSCOLUMNS` - Column information
- `QSYS2.SYSROUTINES` - Stored procedures/functions
- `QSYS2.SYSINDEXES` - Index metadata
- `QSYS2.SYSTRIGGERS` - Trigger definitions
- `QSYS2.SYSSEQUENCES` - Sequence objects
- `QSYS2.SYSCST` - Constraints (for primary keys)

### 4. Dependencies

Added to `pyproject.toml`:
```toml
[project.optional-dependencies]
db2i = ["pyodbc>=5.0.0"]
```

Also included in the `all` extras group.

### 5. Testing Support

**Test Files Created:**
- `tests/fixtures/db2i.py` - Test fixtures for DB2 for i
- `tests/test_db2i.py` - Integration tests

**Test Configuration:**
Environment variables for testing:
- `DB2I_HOST` - IBM i server hostname
- `DB2I_PORT` - Optional port (if required)
- `DB2I_USER` - Username for authentication
- `DB2I_PASSWORD` - Password
- `DB2I_LIBRARY` - Default library/schema
- `DB2I_ODBC_DRIVER` - ODBC driver name (optional)

Run tests with: `pytest -m db2i`

## Connection Examples

### Basic Connection
```python
{
    "name": "my_ibm_i",
    "db_type": "db2i",
    "host": "ibmi.example.com",
    "username": "myuser",
    "password": "mypass",
    "database": "MYLIB"  # Default library
}
```

### With Custom ODBC Driver
```python
{
    "name": "my_ibm_i",
    "db_type": "db2i",
    "host": "ibmi.example.com",
    "username": "myuser",
    "password": "mypass",
    "extra_options": {
        "odbc_driver": "iSeries Access ODBC Driver"
    }
}
```

### URL Format
```
db2i://username:password@hostname/library
```

## Installation Instructions

### 1. Install ODBC Driver

#### macOS
1. Download IBM i Access Client Solutions
2. Install the ODBC driver component
3. Verify: The driver should be named "IBM i Access ODBC Driver"

#### Linux
1. Download IBM i Access ODBC Driver for Linux
2. Follow distribution-specific installation
3. Verify: `odbcinst -q -d`

#### Windows
1. Download and install IBM i Access ODBC Driver
2. Driver is automatically registered

### 2. Install Python Package
```bash
# Install with DB2 for i support
pip install sqlit-tui[db2i]

# Or install all database drivers
pip install sqlit-tui[all]

# Or just install pyodbc separately
pip install pyodbc
```

## Technical Details

### Adapter Class: `Db2iAdapter`

**Base Class:** `CursorBasedAdapter`

**Properties:**
- `name`: "IBM DB2 for i"
- `install_extra`: "db2i"
- `install_package`: "pyodbc"
- `driver_import_names`: ("pyodbc",)
- `supports_multiple_databases`: False (uses libraries instead)
- `supports_cross_database_queries`: True
- `supports_stored_procedures`: True
- `supports_sequences`: True

### ODBC Connection String Format

```
DRIVER={IBM i Access ODBC Driver};
SYSTEM=hostname;
UID=username;
PWD=password;
DBQ=library;
[additional options]
```

## Differences from Standard DB2

1. **Libraries vs Databases**: IBM i uses libraries as the primary organizational unit
2. **System Catalogs**: Uses QSYS2 schema instead of SYSCAT
3. **ODBC-Based**: Uses standard ODBC instead of DB2 CLI
4. **No License Required**: The ODBC driver is freely available from IBM

## Architecture Integration

The DB2 for i provider follows the same pattern as other database providers:

1. **Provider Registration**: Auto-discovered via `provider.py`
2. **Schema Definition**: Connection fields defined in `schema.py`
3. **Adapter Implementation**: Database operations in `adapter.py`
4. **Testing**: Standard test fixtures and integration tests

## Next Steps

To use the new DB2 for i adapter:

1. Ensure the IBM i Access ODBC Driver is installed on your system
2. Install sqlit with DB2i support: `pip install sqlit-tui[db2i]`
3. Create a connection configuration with `db_type="db2i"`
4. Connect to your IBM i server!

## Support Resources

- [IBM i Access ODBC Driver Docs](https://www.ibm.com/docs/en/i/)
- [pyodbc Documentation](https://github.com/mkleehammer/pyodbc/wiki)
- [IBM i SQL Reference](https://www.ibm.com/docs/en/i/7.4?topic=reference-sql)

## Files Modified

1. **sqlit/domains/connections/providers/db2i/** (new directory)
   - `__init__.py`
   - `adapter.py`
   - `provider.py`
   - `schema.py`
   - `README.md`
   - `example.py`

2. **pyproject.toml**
   - Added `db2i = ["pyodbc>=5.0.0"]` to optional dependencies
   - Added `pyodbc>=5.0.0` to `all` extras

3. **tests/fixtures/db2i.py** (new file)
   - Test fixtures for DB2 for i connections

4. **tests/test_db2i.py** (new file)
   - Integration tests for DB2 for i

5. **tests/conftest.py**
   - Added import for DB2i fixtures

## License Note

This implementation uses:
- **pyodbc**: MIT License
- **IBM i Access ODBC Driver**: Freely available from IBM, no license fee required

The IBM i Access ODBC Driver can be downloaded from IBM at no cost and does not require purchasing an IBM DB2 license.
