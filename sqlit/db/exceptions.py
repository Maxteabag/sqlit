"""Custom exceptions for the database layer."""


class MissingDriverError(ConnectionError):
    """Exception raised when a required database driver package is not installed."""

    def __init__(self, driver_name: str, extra_name: str, package_name: str):
        self.driver_name = driver_name
        self.extra_name = extra_name
        self.package_name = package_name
        super().__init__(f"Missing driver for {driver_name}")


class MissingODBCDriverError(ConnectionError):
    """Exception raised when a required ODBC driver is not installed (SQL Server)."""

    def __init__(self, selected_driver: str, installed_drivers: list[str]):
        self.selected_driver = selected_driver
        self.installed_drivers = installed_drivers
        super().__init__(f"Missing ODBC driver: {selected_driver}")
