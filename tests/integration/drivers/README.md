# ODBC Driver Installation Tests

Validates that `sqlit/drivers.py` installation commands work on real Linux distributions.

## Run

```bash
./run_tests.sh              # all distros
./run_tests.sh ubuntu       # single distro (ubuntu|debian|rocky|fedora|alpine|opensuse|arch)
./run_tests.sh --clean      # remove containers/images
```

## What It Does

1. Spins up SQL Server 2022 container
2. For each distro: runs `get_install_commands()`, executes them, verifies driver works
3. Tests actual connection to SQL Server

## Requirements

- Docker + Docker Compose
- ~10GB disk space
- ~10 minutes (all distros)

## Not Covered

macOS and Windows cannot be containerized - test manually.
