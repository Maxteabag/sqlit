# Example: Custom sqlit build with specific dependencies
#
# This is an example flake.nix that shows how to create a custom
# sqlit build with exactly the dependencies you need.
#
# To use this:
# 1. Copy this file to your project directory as `flake.nix`
# 2. Modify the makeSqlit parameters to enable/disable what you need
# 3. Run: nix run

{
  description = "Custom sqlit build";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    sqlit.url = "github:Maxteabag/sqlit";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, sqlit, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        # Create a custom sqlit with only PostgreSQL and MySQL support
        my-sqlit = sqlit.lib.${system}.makeSqlit {
          # Enable SSH tunneling
          enableSSH = true;
          
          # Enable only PostgreSQL and MySQL
          enablePostgres = true;
          enableMySQL = true;
          
          # Disable everything else
          enableMSSQL = false;
          enableDuckDB = false;
          enableOracle = false;
          enableMariaDB = false;
          enableDB2 = false;
          enableHANA = false;
          enableTeradata = false;
          enableTrino = false;
          enablePresto = false;
          enableBigQuery = false;
          enableRedshift = false;
          enableClickHouse = false;
          enableCloudflareD1 = false;
          enableTurso = false;
          enableFirebird = false;
          enableSnowflake = false;
          enableAthena = false;
          enableFlightSQL = false;
        };
      in {
        packages.default = my-sqlit;
        
        apps.default = {
          type = "app";
          program = "${my-sqlit}/bin/sqlit";
        };
      });
}
