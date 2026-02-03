"""Integration tests for IBM DB2 for i database operations."""

import pytest

from tests.helpers import BaseDatabaseTests


@pytest.mark.db2i
class TestDb2iIntegration(BaseDatabaseTests):
    """Integration tests for IBM DB2 for i database operations via CLI."""

    @pytest.fixture(scope="class")
    def db_spec(self):
        return dict(
            db_type="db2i",
            display_name="IBM DB2 for i",
            connection_fixture="db2i_connection",
            db_fixture="db2i_db",
        )
