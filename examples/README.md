# Nix Flake Examples

This directory contains example configurations for building custom sqlit variants with the Nix flake.

## custom-flake.nix

An example showing how to create a custom sqlit build with only the database drivers you need.

This example enables:
- SSH tunnel support
- PostgreSQL driver
- MySQL driver

And disables all other optional dependencies.

### How to use:

1. Copy the file to your project:
   ```bash
   cp examples/custom-flake.nix your-project/flake.nix
   ```

2. Modify the parameters to suit your needs:
   - Set `enableSSH = true` if you need SSH tunnel support
   - Enable the database drivers you need (e.g., `enablePostgres = true`)
   - Disable the ones you don't need (e.g., `enableOracle = false`)

3. Run your custom sqlit:
   ```bash
   cd your-project
   nix run
   ```

### Available Parameters

See `docs/nix-flake.md` for a complete list of all available parameters and their defaults.

### Quick Reference

Common database parameters:
- `enableSSH` - SSH tunnel support
- `enablePostgres` - PostgreSQL, CockroachDB, Supabase
- `enableMySQL` - MySQL
- `enableMSSQL` - SQL Server
- `enableDuckDB` - DuckDB analytics database
- `enableOracle` - Oracle Database
- `enableBigQuery` - Google BigQuery
- `enableSnowflake` - Snowflake
- `enableAll` - Enable all available dependencies

## Tips

1. **Start minimal, add what you need**: Begin with all options disabled, then enable only what you need.

2. **Check nixpkgs availability**: Some Python packages are not in nixpkgs. See `docs/nix-flake.md` for details.

3. **Use pre-configured variants for common cases**: If you just need common databases, use the default package instead:
   ```bash
   nix run github:Maxteabag/sqlit
   ```
