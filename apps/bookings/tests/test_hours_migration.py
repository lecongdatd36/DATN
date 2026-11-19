from datetime import time
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock


class LastArrivalMigrationTests(TestCase):
    def test_custom_schedules_fit_restored_last_arrival_without_changing_hours(self):
        pairs = [(time(9), time(22), time(21)),
                 (time(10), time(20), time(19, 59)),
                 (time(21, 30), time(23), time(21, 30)),
                 (time(0), time(0, 0, 30), time(0))]
        rows = [SimpleNamespace(opening_time=start, closing_time=end, save=Mock())
                for start, end, _ in pairs]
        apps = Mock()
        apps.get_model.return_value.objects.using.return_value.all.return_value = rows
        migration = import_module("apps.bookings.migrations.0013_restore_last_booking_time")
        migration.fit_last_arrival_to_existing_hours(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        for row, (start, end, expected) in zip(rows, pairs):
            self.assertEqual(row.last_booking_time, expected)
            self.assertEqual((row.opening_time, row.closing_time), (start, end))
            self.assertLess(row.last_booking_time, end)
            row.save.assert_called_once_with(update_fields=["last_booking_time"])
