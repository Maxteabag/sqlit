{
  description = "A terminal UI for SQL databases";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        lib = pkgs.lib;
        pyPkgs = pkgs.python3.pkgs;

        # Helper function to build sqlit with optional dependencies
        makeSqlit = {
          # SSH tunnel support
          enableSSH ? true,
          # Popular database drivers
          enablePostgres ? true,
          enableMySQL ? true,
          enableMSSQL ? false,  # Not available in nixpkgs
          # Advanced database drivers
          enableOracle ? false,
          enableMariaDB ? false,
          enableDB2 ? false,
          enableHANA ? false,
          enableTeradata ? false,
          enableTrino ? false,
          enablePresto ? false,
          # Cloud and modern databases
          enableBigQuery ? false,
          enableRedshift ? false,
          enableDuckDB ? true,
          enableClickHouse ? false,
          enableCloudflareD1 ? false,
          enableTurso ? false,
          enableFirebird ? false,
          enableSnowflake ? false,
          enableAthena ? false,
          enableFlightSQL ? false,
          # Enable all optional dependencies
          enableAll ? false,
        }:

        let
          ref =
            if self ? sourceInfo && self.sourceInfo ? ref
            then self.sourceInfo.ref
            else "";
          tag =
            if lib.hasPrefix "refs/tags/v" ref
            then lib.removePrefix "refs/tags/v" ref
            else if lib.hasPrefix "refs/tags/" ref
            then lib.removePrefix "refs/tags/" ref
            else if lib.hasPrefix "v" ref
            then lib.removePrefix "v" ref
            else "";
          shortRev = if self ? shortRev then self.shortRev else "dirty";
          version = if tag != "" then tag else "0.0.0+${shortRev}";

          # Determine if we should enable each dependency
          withSSH = enableAll || enableSSH;
          withPostgres = enableAll || enablePostgres;
          withMySQL = enableAll || enableMySQL;
          withMSSQL = enableAll || enableMSSQL;
          withOracle = enableAll || enableOracle;
          withMariaDB = enableAll || enableMariaDB;
          withDB2 = enableAll || enableDB2;
          withHANA = enableAll || enableHANA;
          withTeradata = enableAll || enableTeradata;
          withTrino = enableAll || enableTrino;
          withPresto = enableAll || enablePresto;
          withBigQuery = enableAll || enableBigQuery;
          withRedshift = enableAll || enableRedshift;
          withDuckDB = enableAll || enableDuckDB;
          withClickHouse = enableAll || enableClickHouse;
          withCloudflareD1 = enableAll || enableCloudflareD1;
          withTurso = enableAll || enableTurso;
          withFirebird = enableAll || enableFirebird;
          withSnowflake = enableAll || enableSnowflake;
          withAthena = enableAll || enableAthena;
          withFlightSQL = enableAll || enableFlightSQL;

          # Build list of optional dependencies based on flags
          # Note: Some packages are not available in nixpkgs and are documented here:
          # - mssql-python (SQL Server)
          # - oracledb (Oracle)
          # - mariadb (MariaDB) 
          # - ibm_db (DB2)
          # - hdbcli (SAP HANA)
          # - teradatasql (Teradata)
          # - trino (Trino)
          # - presto-python-client (Presto)
          # - redshift-connector (Redshift)
          # - clickhouse-connect (ClickHouse)
          # - libsql (Turso)
          # - firebirdsql (Firebird)
          # - pyathena (Athena)
          # - adbc-driver-flightsql (Apache Arrow Flight SQL)
          # Users needing these can install via pipx inject or pip after installation
          
          optionalDeps = lib.optionals withSSH [
            pyPkgs.sshtunnel
            pyPkgs.paramiko
          ] ++ lib.optionals withPostgres [
            pyPkgs.psycopg2
          ] ++ lib.optionals withMySQL [
            pyPkgs.pymysql
          ] ++ lib.optionals withBigQuery [
            pyPkgs.google-cloud-bigquery
          ] ++ lib.optionals withDuckDB [
            pyPkgs.duckdb
          ] ++ lib.optionals withCloudflareD1 [
            pyPkgs.requests
          ] ++ lib.optionals withSnowflake [
            pyPkgs.snowflake-connector-python
          ];
        in pyPkgs.buildPythonApplication {
          pname = "sqlit";
          inherit version;
          pyproject = true;

          src = self;

          build-system = [
            pyPkgs.hatchling
            pyPkgs."hatch-vcs"
            pyPkgs."setuptools-scm"
          ];

          nativeBuildInputs = [
            pyPkgs.pythonRelaxDepsHook
          ];

          pythonRelaxDeps = [
            "textual-fastdatatable"
          ];

          SETUPTOOLS_SCM_PRETEND_VERSION = version;

          dependencies = [
            pyPkgs.docker
            pyPkgs.keyring
            pyPkgs.pyperclip
            pyPkgs.sqlparse
            pyPkgs.textual
            pyPkgs."textual-fastdatatable"
          ] ++ optionalDeps;

          pythonImportsCheck = [ "sqlit" ];

          meta = with lib; {
            description = "A terminal UI for SQL databases";
            homepage = "https://github.com/Maxteabag/sqlit";
            license = licenses.mit;
            mainProgram = "sqlit";
          };
        };

        # Default sqlit with common options enabled
        sqlit = makeSqlit {};

        # Minimal sqlit with only built-in SQLite support
        sqlit-minimal = makeSqlit {
          enableSSH = false;
          enablePostgres = false;
          enableMySQL = false;
          enableDuckDB = false;
        };

        # Full-featured sqlit with all available dependencies
        sqlit-full = makeSqlit {
          enableAll = true;
        };
      in {
        packages = {
          inherit sqlit sqlit-minimal sqlit-full;
          default = sqlit;
        };

        # Expose the makeSqlit function so users can create custom variants
        lib.makeSqlit = makeSqlit;

        apps.default = {
          type = "app";
          program = "${sqlit}/bin/sqlit";
        };

        checks = {
          inherit sqlit;
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.python3
            pkgs.hatch
            pyPkgs.pytest
            pyPkgs.pytest-timeout
            pyPkgs.pytest-asyncio
            pyPkgs.pytest-cov
            pyPkgs.pytest-benchmark
            pkgs.ruff
            pyPkgs.mypy
            pkgs.pre-commit
            pyPkgs.build
            pyPkgs.faker
            pyPkgs.ipython
          ];
          inputsFrom = [ sqlit ];
        };
      });
}
