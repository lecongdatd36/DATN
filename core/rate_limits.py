"""Cross-worker request budgets. Store HMAC identifiers, never passwords or raw IPs."""
from datetime import datetime, timedelta
from ipaddress import ip_address, ip_network
import unicodedata
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.crypto import salted_hmac


def client_address(request):
    raw = request.META.get("REMOTE_ADDR", "")
    try:
        address = ip_address(raw)
        trusted = [ip_network(value) for value in settings.TRUSTED_PROXY_CIDRS]
        if not any(address in network for network in trusted):
            return str(address)
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        # Walk from the trusted proxy towards the client. Leftmost is not blindly trusted.
        for value in reversed(forwarded.split(",")):
            if not value.strip():
                continue
            address = ip_address(value.strip())
            if not any(address in network for network in trusted):
                return str(address)
        return str(address)
    except ValueError:
        return raw[:100] or "unknown"


def consume_budgets(budgets, *, at=None):
    from apps.accounts.models import SecurityRateBucket
    now = at or timezone.now()
    stamp = int(now.timestamp())
    keys = []
    for scope, identity, limit, seconds in budgets:
        start = stamp // seconds * seconds
        key = salted_hmac("qlnh.security-rate", f"{scope}:{identity}:{start}", algorithm="sha256").hexdigest()
        keys.append((key, limit, datetime.fromtimestamp(start, tz=now.tzinfo) + timedelta(seconds=seconds)))
    with transaction.atomic():
        rows = []
        for key, limit, expires in sorted(keys):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [int.from_bytes(bytes.fromhex(key)[:8], "big", signed=True)])
            row, _ = SecurityRateBucket.objects.select_for_update().get_or_create(key=key, defaults={"expires_at": expires})
            rows.append((row, limit))
        blocked = [max(1, int((row.expires_at - now).total_seconds()) + 1) for row, limit in rows if row.hits >= limit]
        if blocked:
            return max(blocked)
        for row, _ in rows:
            row.hits += 1
            row.save(update_fields=("hits",))
        SecurityRateBucket.objects.filter(expires_at__lt=now-timedelta(hours=1)).delete()
    return 0


class PublicRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.SECURITY_RATE_LIMIT_ENABLED or request.method != "POST":
            return None
        name = request.resolver_match.view_name if request.resolver_match else ""
        ip = client_address(request)
        budgets = []
        if name in {"accounts:login", "admin:login"} or name.endswith("_admin:login"):
            username = unicodedata.normalize("NFKC", request.POST.get("username", "")[:150]).strip().casefold()
            budgets = [("login-ip", ip, settings.LOGIN_IP_ATTEMPTS, 60),
                ("login-account", username or "empty", settings.LOGIN_ACCOUNT_ATTEMPTS, 300)]
        elif name in {"customer_reservations:lookup", "online_reservations:lookup"}:
            budgets = [("lookup", ip, settings.PUBLIC_LOOKUP_ATTEMPTS, 60)]
        elif name in {"customer_reservations:create", "customer_reservations:check", "online_reservations:create", "online_reservations:review", "online_reservations:table", "online_reservations:preorder"}:
            budgets = [("booking", ip, settings.PUBLIC_BOOKING_ATTEMPTS, 60)]
        if not budgets:
            return None
        try:
            retry_after = consume_budgets(budgets)
        except DatabaseError:
            response = JsonResponse({"error": "Tạm chưa thể xử lý. Vui lòng thử lại sau."}, status=503)
            response["Cache-Control"] = "no-store"
            return response
        if not retry_after:
            return None
        message = "Bạn đã thao tác quá nhiều lần. Vui lòng chờ rồi thử lại."
        if "application/json" in request.headers.get("Accept", "") or request.content_type == "application/json":
            response = JsonResponse({"error": message, "code": "rate_limit", "retry_after": retry_after}, status=429)
        else:
            response = render(request, "429.html", {"retry_after": retry_after}, status=429)
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
        return response
