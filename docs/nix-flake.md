# Nix Flake Usage

This document describes how to use the Nix flake with optional dependencies.

## Overview

The sqlit Nix flake provides flexible package variants with optional database driver and SSH tunnel support. You can choose between pre-configured variants or create custom builds with exactly the dependencies you need.

## Pre-configured Variants

### Default Package (Recommended)
The default package includes common database drivers and SSH support:
```bash
nix run github:Maxteabag/sqlit
# or
nix profile install github:Maxteabag/sqlit
```

**Included dependencies:**
- SSH tunnel support (sshtunnel, paramiko)
- PostgreSQL driver (psycopg2)
- MySQL driver (pymysql)
- DuckDB driver (duckdb)
- Cloudflare D1 support (requests)

### Minimal Package
For users who only need SQLite support:
```bash
nix run github:Maxteabag/sqlit#sqlit-minimal
# or
nix profile install github:Maxteabag/sqlit#sqlit-minimal
```

**Included dependencies:**
- Only core dependencies (no optional drivers)
- SQLite support (built-in to Python)

### Full Package
For users who want all available dependencies:
```bash
nix run github:Maxteabag/sqlit#sqlit-full
# or
nix profile install github:Maxteabag/sqlit#sqlit-full
```

**Included dependencies:**
- All database drivers available in nixpkgs
- SSH tunnel support
- All cloud database connectors

## Custom Builds

You can create a custom build with exactly the dependencies you need by creating a `flake.nix` in your project:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    sqlit.url = "github:Maxteabag/sqlit";
  };

  outputs = { self, nixpkgs, sqlit }:
    let
      system = "x86_64-linux";  # or your system
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      packages.${system}.default = sqlit.lib.${system}.makeSqlit {
        # Enable only what you need
        enableSSH = true;
        enablePostgres = true;
        enableMySQL = false;
        enableMSSQL = false;
        enableDuckDB = true;
        # ... other options
      };
    };
}
```

Then run:
```bash
nix run
```

## Available Options

All options default to sensible values for common use cases. Set to `true` to enable or `false` to disable:

### SSH Tunnel Support
- `enableSSH` (default: `true`) - Enables SSH tunnel connections

### Popular Database Drivers
- `enablePostgres` (default: `true`) - PostgreSQL, CockroachDB, Supabase
- `enableMySQL` (default: `true`) - MySQL support
- `enableMSSQL` (default: `true`) - SQL Server support (not in nixpkgs, placeholder)
- `enableDuckDB` (default: `true`) - DuckDB analytics database

### Advanced Database Drivers
- `enableOracle` (default: `false`) - Oracle Database (not in nixpkgs)
- `enableMariaDB` (default: `false`) - MariaDB (not in nixpkgs)
- `enableDB2` (default: `false`) - IBM Db2 (not in nixpkgs)
- `enableHANA` (default: `false`) - SAP HANA (not in nixpkgs)
- `enableTeradata` (default: `false`) - Teradata (not in nixpkgs)
- `enableTrino` (default: `false`) - Trino (not in nixpkgs)
- `enablePresto` (default: `false`) - Presto (not in nixpkgs)

### Cloud and Modern Databases
- `enableBigQuery` (default: `false`) - Google BigQuery
- `enableRedshift` (default: `false`) - AWS Redshift (not in nixpkgs)
- `enableClickHouse` (default: `false`) - ClickHouse (not in nixpkgs)
- `enableCloudflareD1` (default: `false`) - Cloudflare D1
- `enableTurso` (default: `false`) - Turso (not in nixpkgs)
- `enableFirebird` (default: `false`) - Firebird SQL (not in nixpkgs)
- `enableSnowflake` (default: `false`) - Snowflake
- `enableAthena` (default: `false`) - AWS Athena (not in nixpkgs)
- `enableFlightSQL` (default: `false`) - Apache Arrow Flight SQL (not in nixpkgs)

### Enable All
- `enableAll` (default: `false`) - Enable all available optional dependencies

## Note on Nixpkgs Availability

Some Python packages are not yet available in nixpkgs. These are marked with comments in the flake and will be skipped during build. If you need these drivers, you can:

1. Use `pipx inject` or `pip install` after installation
2. Use a Python virtual environment alongside the Nix installation
3. Contribute the missing packages to nixpkgs

## Examples

### PostgreSQL and MySQL only
```nix
sqlit.lib.${system}.makeSqlit {
  enableSSH = true;
  enablePostgres = true;
  enableMySQL = true;
  enableDuckDB = false;
}
```

### Cloud databases
```nix
sqlit.lib.${system}.makeSqlit {
  enableBigQuery = true;
  enableSnowflake = true;
  enableAthena = true;
}
```

### Everything available
```nix
sqlit.lib.${system}.makeSqlit {
  enableAll = true;
}
```
