from unittest import skipUnless
from datetime import datetime, timezone
import json
from django.db import connection, IntegrityError, transaction
from django.test import TestCase, SimpleTestCase
from apps.seating.models import Area, DiningTable
from core.db_locks import session_lock
from core.serializers_precise import PreciseEncoder


class PreciseFixtureTests(SimpleTestCase):
    def test_fixtures_keep_sub_millisecond_datetime_digits(self):
        for microseconds in (123456, 450, 999999):
            moment = datetime(2026, 11, 23, 6, 0, microsecond=microseconds, tzinfo=timezone.utc)
            encoded = json.loads(json.dumps(moment, cls=PreciseEncoder))
            self.assertEqual(datetime.fromisoformat(encoded), moment)


@skipUnless(connection.vendor == "microsoft", "SQL Server compatibility checks")
class SqlServerConstraintTests(TestCase):
    def test_datetime_round_trip_keeps_microsecond_precision(self):
        area = Area.objects.create(name="SQL datetime precision")
        moment = datetime(2026, 11, 23, 6, 0, microsecond=123456, tzinfo=timezone.utc)
        Area.objects.filter(pk=area.pk).update(updated_at=moment)
        area.refresh_from_db()
        self.assertEqual(area.updated_at, moment)

    def test_persisted_lower_unique_name_rejects_case_only_duplicates(self):
        Area.objects.create(name="SQL Server Area")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Area.objects.create(name="sql server area")

    def test_blank_names_include_unicode_whitespace(self):
        for value in [" ", "\t\r\n", "\u00a0\u2003"]:
            with self.subTest(value=repr(value)):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Area.objects.create(name=value)

    def test_code_check_preserves_dash_underscore_and_rejects_invalid_values(self):
        area = Area.objects.create(name="SQL code checks")
        for value in ["SQL-01", "SQL_02", "SQL03"]:
            DiningTable.objects.create(area=area, code=value, capacity=4)
        for value in ["lower", "BAD!", "_FIRST", "TRAILING "]:
            with self.subTest(value=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    DiningTable.objects.create(area=area, code=value, capacity=4)

    def test_session_lock_is_released_after_exception(self):
        with self.assertRaisesRegex(ValueError, "rollback message"):
            with session_lock(81723999) as acquired:
                self.assertTrue(acquired)
                raise ValueError("rollback message")
        with session_lock(81723999) as acquired:
            self.assertTrue(acquired)
