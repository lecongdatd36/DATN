from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings

from apps.customers import services
from apps.customers.models import Customer, CustomerActivityLog


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CustomerConcurrencyTests(TransactionTestCase):
    serialized_rollback = True

    def test_two_actors_creating_same_phone_commit_one_customer_and_log(self):
        actors = [get_user_model().objects.create_superuser(username=f"concurrent_customer_{i}", password="Secret-test-123!") for i in range(2)]
        barrier = Barrier(2)
        original_save = services._save

        def synchronized_save(customer):
            barrier.wait(timeout=10)
            original_save(customer)

        def create(actor_id):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                try:
                    services.create_customer(actor=actor, full_name="Concurrent customer", phone="0912345678")
                    return "created"
                except ValidationError as error:
                    return "duplicate" if "phone" in error.message_dict else "unexpected"
            finally:
                connections.close_all()

        with patch("apps.customers.services._save", side_effect=synchronized_save):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(create, actor.pk) for actor in actors]
                results = [future.result(timeout=20) for future in futures]
        self.assertCountEqual(results, ["created", "duplicate"])
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(CustomerActivityLog.objects.count(), 1)
