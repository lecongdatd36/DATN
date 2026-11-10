from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone
from apps.workforce import services
from apps.workforce.models import Attendance, WorkSchedule
from .test_workforce import fixtures


class WorkforceConcurrencyTests(TransactionTestCase):
    # Preserve migration-seeded groups/content types like the existing HR suite.
    serialized_rollback = True

    def setUp(self):
        self.manager, self.user, self.employee, self.other, self.shift, self.device = fixtures()

    def race(self, operation):
        barrier = Barrier(2)
        def worker():
            try:
                barrier.wait(timeout=10)
                operation()
                return "saved"
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: worker(), range(2)))

    def test_two_managers_cannot_assign_overlapping_shifts(self):
        results = self.race(lambda: services.assign_schedule(actor=self.manager, employee_id=self.employee.pk,
            shift_id=self.shift.pk, work_date=timezone.localdate()+timedelta(days=1)))
        self.assertCountEqual(results, ["saved", "rejected"])
        self.assertEqual(WorkSchedule.objects.count(), 1)

    def test_simultaneous_clock_in_and_out_each_record_once(self):
        row = services.assign_schedule(actor=self.manager, employee_id=self.employee.pk, shift_id=self.shift.pk,
            work_date=timezone.localdate()+timedelta(days=1))
        services.change_schedule(actor=self.manager, schedule_id=row.pk, revision=1, action="publish")
        with patch("apps.workforce.services.timezone.now", return_value=row.starts_at):
            results = self.race(lambda: services.record_clock(employee_id=self.employee.pk, action="IN", device=self.device))
        self.assertCountEqual(results, ["saved", "rejected"])
        with patch("apps.workforce.services.timezone.now", return_value=row.ends_at):
            results = self.race(lambda: services.record_clock(employee_id=self.employee.pk, action="OUT", device=self.device))
        self.assertCountEqual(results, ["saved", "rejected"])
        self.assertEqual(Attendance.objects.count(), 1)
        self.assertEqual(Attendance.objects.get().checked_out_at, row.ends_at)
