from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management.base import BaseCommand
from django.db.models import Q, F
from django.utils import timezone
from datetime import timedelta
from apps.orders.models import ZaloPayTransaction
from apps.orders.zalopay import GatewayUnavailable
from apps.orders.zalopay_services import query_transaction


class Command(BaseCommand):
    help = "Reconcile pending ZaloPay Sandbox payments when callbacks are missing."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        checked = 0
        candidates = ZaloPayTransaction.objects.filter(Q(status='PENDING') |
            Q(status='ABANDONED', created_at__gte=timezone.now()-timedelta(hours=48)))
        limit = max(1, min(options["limit"], 1000))
        for token in candidates.order_by(F("last_queried_at").asc(nulls_first=True), "created_at", "pk").values_list("token", flat=True)[:limit]:
            try:
                query_transaction(token)
                checked += 1
            except (ImproperlyConfigured, ValidationError, GatewayUnavailable):
                self.stderr.write("Sandbox transaction could not be verified; retained for later reconciliation.")
        self.stdout.write(f"Queried {checked} pending Sandbox transaction(s).")
