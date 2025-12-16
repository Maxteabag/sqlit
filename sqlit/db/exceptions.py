"""Custom exceptions for the database layer."""


class MissingDriverError(ConnectionError):
    """Exception raised when a required database driver package is not installed."""

    def __init__(self, driver_name: str, extra_name: str, package_name: str):
        self.driver_name = driver_name
        self.extra_name = extra_name
        self.package_name = package_name
        super().__init__(f"Missing driver for {driver_name}")
