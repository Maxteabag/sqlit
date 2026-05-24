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

        # Extras mirror project.optional-dependencies in pyproject.toml,
        # limited to drivers packaged in nixpkgs. Others (mssql-python,
        # oracledb, mariadb, ibm_db, hdbcli, teradatasql, trino,
        # presto-python-client, redshift-connector, clickhouse-connect,
        # libsql, firebirdsql, pyathena, adbc-driver-flightsql) aren't
        # here; install with `pipx inject` or a custom derivation.
        nixpkgsExtras = {
          ssh = [ pyPkgs.sshtunnel pyPkgs.paramiko ];
          postgres = [ pyPkgs.psycopg2 ];
          cockroachdb = [ pyPkgs.psycopg2 ];
          mysql = [ pyPkgs.pymysql ];
          duckdb = [ pyPkgs.duckdb ];
          bigquery = [ pyPkgs.google-cloud-bigquery ];
          snowflake = [ pyPkgs.snowflake-connector-python ];
          d1 = [ pyPkgs.requests ];
        };

        resolveExtras = names:
          lib.concatLists (map (n:
            nixpkgsExtras.${n} or (throw
              "Unknown sqlit extra '${n}'. Available: ${
                lib.concatStringsSep ", " (builtins.attrNames nixpkgsExtras)
              }")
          ) names);

        # Build sqlit, optionally with a set of driver extras from nixpkgs.
        # Example:  makeSqlit { extras = [ "postgres" "ssh" ]; }
        makeSqlit = { extras ? [] }:
          pyPkgs.buildPythonApplication {
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
            ] ++ (resolveExtras extras);

            pythonImportsCheck = [ "sqlit" ];

            meta = with lib; {
              description = "A terminal UI for SQL databases";
              homepage = "https://github.com/Maxteabag/sqlit";
              license = licenses.mit;
              mainProgram = "sqlit";
            };
          };

        sqlit = makeSqlit { extras = builtins.attrNames nixpkgsExtras; };
      in {
        packages = {
          inherit sqlit;
          default = sqlit;
        };

        lib = { inherit makeSqlit; };

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
