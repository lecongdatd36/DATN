from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import BaseCommand
from apps.orders.models import ZaloPayTransaction
from apps.orders.zalopay import GatewayUnavailable
from apps.orders.zalopay_services import query_transaction


class Command(BaseCommand):
    help = "Reconcile pending ZaloPay Sandbox payments when callbacks are missing."

    def handle(self, *args, **options):
        checked = 0
        for token in ZaloPayTransaction.objects.filter(status="PENDING").order_by("created_at").values_list("token", flat=True)[:100]:
            try:
                query_transaction(token)
                checked += 1
            except (ImproperlyConfigured, ValidationError, GatewayUnavailable):
                self.stderr.write("Sandbox transaction could not be verified; retained for later reconciliation.")
        self.stdout.write(f"Queried {checked} pending Sandbox transaction(s).")
