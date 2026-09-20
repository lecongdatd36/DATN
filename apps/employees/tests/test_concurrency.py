from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings

from apps.accounts.services import create_account_with_profile
from apps.employees.models import EmployeeProfile


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EmployeeCreationConcurrencyTests(TransactionTestCase):
    # Khôi phục các vị trí/nhóm được seed bởi migration sau mỗi lần flush.
    serialized_rollback = True

    def test_concurrent_creations_in_different_positions_get_distinct_codes(self):
        manager = get_user_model().objects.create_superuser(username="concurrent_admin", password="Admin!5297-secret")
        barrier = Barrier(2)

        def create(number, position):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=manager.pk)
                barrier.wait(timeout=10)
                employee = create_account_with_profile(
                    actor=actor,
                    account_data={"username": f"concurrent{number}"},
                    profile_data={"full_name": f"Concurrent {number}", "phone": f"090000000{number}", "join_date": date.today()},
                    password="Employee!5297-secret", position_code=position,
                )
                return employee.employee_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(create, 1, "WAITER")
            second = pool.submit(create, 2, "KITCHEN")
            codes = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(len(set(codes)), 2)
        self.assertEqual(EmployeeProfile.objects.count(), 2)
