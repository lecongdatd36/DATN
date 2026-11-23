from datetime import timedelta
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import SecurityRateBucket
from core.rate_limits import client_address, consume_budgets


@override_settings(SECURITY_RATE_LIMIT_ENABLED=True, LOGIN_ACCOUNT_ATTEMPTS=2, LOGIN_IP_ATTEMPTS=100)
class RateLimitTests(TestCase):
    def test_login_attempts_share_database_budget_and_return_retry_after(self):
        url = reverse("accounts:login")
        for _ in range(2):
            self.assertEqual(self.client.post(url, {"username": "private-user", "password": "wrong"}).status_code, 200)
        result = self.client.post(url, {"username": "PRIVATE-USER", "password": "wrong"}, HTTP_ACCEPT="application/json")
        self.assertEqual(result.status_code, 429)
        self.assertGreater(int(result["Retry-After"]), 0)
        self.assertEqual(result.json()["code"], "rate_limit")
        for bucket in SecurityRateBucket.objects.all():
            self.assertNotIn("private-user", bucket.key)
            self.assertNotIn("127.0.0.1", bucket.key)

    @override_settings(LOGIN_IP_ATTEMPTS=2)
    def test_untrusted_forwarded_header_cannot_rotate_ip_budget(self):
        url = reverse("accounts:login")
        for number in range(3):
            result = self.client.post(url, {"username": f"user-{number}", "password": "wrong"}, HTTP_X_FORWARDED_FOR=f"10.1.1.{number}")
        self.assertEqual(result.status_code, 429)

    def test_counter_resets_on_next_window(self):
        now = timezone.now().replace(second=0, microsecond=0)
        self.assertEqual(consume_budgets([("test", "identity", 1, 60)], at=now), 0)
        self.assertGreater(consume_budgets([("test", "identity", 1, 60)], at=now), 0)
        self.assertEqual(consume_budgets([("test", "identity", 1, 60)], at=now+timedelta(minutes=1)), 0)

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_only_trusted_proxy_chain_is_used(self):
        factory = RequestFactory()
        request = factory.get("/", REMOTE_ADDR="10.1.1.1", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 10.2.2.2")
        self.assertEqual(client_address(request), "2.2.2.2")
        request.META["REMOTE_ADDR"] = "3.3.3.3"
        self.assertEqual(client_address(request), "3.3.3.3")

    @override_settings(PUBLIC_BOOKING_ATTEMPTS=1, PUBLIC_LOOKUP_ATTEMPTS=1)
    def test_public_booking_and_lookup_are_limited_separately(self):
        create, lookup = reverse("customer_reservations:create"), reverse("customer_reservations:lookup")
        self.assertEqual(self.client.post(create, {}).status_code, 200)
        self.assertEqual(self.client.post(create, {}).status_code, 429)
        self.assertEqual(self.client.post(lookup, {}).status_code, 200)
        self.assertEqual(self.client.post(lookup, {}).status_code, 429)
