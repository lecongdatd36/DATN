from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase


class SqlServerPreflightTests(SimpleTestCase):
    def connection(self):
        return patch("apps.accounts.management.commands.check_sqlserver_connection.connection")

    def test_success_reads_server_metadata_and_closes_connection(self):
        output = StringIO()
        with self.connection() as mocked:
            mocked.vendor = "microsoft"
            mocked.settings_dict = {"NAME": "test_database"}
            cursor = mocked.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ("test_database", "16.0.1000.6")
            call_command("check_sqlserver_connection", stdout=output)
            cursor.execute.assert_called_once_with(
                "SELECT DB_NAME(), CAST(SERVERPROPERTY('ProductVersion') AS varchar(128))"
            )
            mocked.close.assert_called_once()
        self.assertIn("connection OK (read-only)", output.getvalue())

    def test_driver_error_does_not_expose_connection_string(self):
        with self.connection() as mocked:
            mocked.vendor = "microsoft"
            mocked.cursor.side_effect = OperationalError("PWD=private-password;host=private-host")
            with self.assertRaises(CommandError) as caught:
                call_command("check_sqlserver_connection")
            mocked.close.assert_called_once()
        self.assertIn("OperationalError", str(caught.exception))
        self.assertNotIn("private-password", str(caught.exception))
        self.assertNotIn("private-host", str(caught.exception))

    def test_wrong_database_stops_the_preflight(self):
        with self.connection() as mocked:
            mocked.vendor = "microsoft"
            mocked.settings_dict = {"NAME": "expected_database"}
            mocked.cursor.return_value.__enter__.return_value.fetchone.return_value = ("other_database", "16.0")
            with self.assertRaisesMessage(CommandError, "unexpected database"):
                call_command("check_sqlserver_connection")

    def test_postgres_profile_is_rejected_without_querying(self):
        with self.connection() as mocked:
            mocked.vendor = "postgresql"
            with self.assertRaisesMessage(CommandError, "QLNH.sqlserver_settings"):
                call_command("check_sqlserver_connection")
            mocked.cursor.assert_not_called()
