from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from apps.seating.models import DiningTable, SeatingActivityLog
from apps.seating.services import save_area, save_table


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SeatingConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def test_two_actors_cannot_create_duplicate_table_codes(self):
        actors = [get_user_model().objects.create_superuser(username=f"seating_admin_{i}", password="Secret!Test123") for i in range(2)]
        area = save_area(actor=actors[0], name="Tầng 1", is_active=True)
        barrier = Barrier(2)

        def create(actor_id):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                barrier.wait(timeout=10)
                try:
                    save_table(actor=actor, code="b01", area_id=area.pk, capacity=4, is_active=True)
                    return "created"
                except ValidationError as error:
                    return "duplicate" if "code" in error.message_dict else "unexpected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create, actor.pk) for actor in actors]
            results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, ["created", "duplicate"])
        self.assertEqual(DiningTable.objects.count(), 1)
        self.assertEqual(SeatingActivityLog.objects.filter(entity="TABLE").count(), 1)

    def test_area_shutdown_and_table_creation_leave_no_available_table(self):
        actors = [get_user_model().objects.create_superuser(username=f"shutdown_admin_{i}", password="Secret!Test123") for i in range(2)]
        area = save_area(actor=actors[0], name="Tầng 1", is_active=True)
        barrier = Barrier(2)

        def operate(index):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=actors[index].pk)
                barrier.wait(timeout=10)
                if index == 0:
                    save_area(actor=actor, area_id=area.pk, name=area.name, is_active=False)
                    return "closed"
                try:
                    save_table(actor=actor, code="B01", area_id=area.pk, capacity=4, is_active=True)
                    return "created"
                except ValidationError as error:
                    return "blocked" if "area" in error.message_dict else "unexpected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(operate, index) for index in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results[0], "closed")
        self.assertIn(results[1], ("created", "blocked"))
        self.assertFalse(DiningTable.objects.filter(is_active=True, area__is_active=True).exists())
        self.assertEqual(SeatingActivityLog.objects.filter(entity="TABLE").count(), DiningTable.objects.count())
