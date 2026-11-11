"""Chrome storefront -> combo basket -> booking -> fixture deposit -> POS.

Uses a disposable local PostgreSQL database. Copies only public catalog fields
for realistic images, never customer/order data or external banking requests.
"""
import json, mimetypes, os, subprocess, sys, tempfile, threading
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from urllib.parse import parse_qs
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.test_settings")
import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from django.utils import timezone
from apps.menu.models import Category, Unit, Dish, Combo
from apps.orders.models import Order
from apps.reservations.models import Reservation, DepositPayment
from apps.reservations.tests import test_reservations as fixtures


class Quiet(WSGIRequestHandler):
    def log_message(self, *args): pass


class Server(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    if connection.settings_dict["HOST"] not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("Local PostgreSQL only")
    public_menu = list(Dish.objects.exclude(status="INACTIVE").values("code", "name", "description", "price", "image", "thumbnail", "category__name", "unit__name"))
    test_name = "test_qlnh_storefront_" + uuid4().hex
    connection.settings_dict["TEST"]["NAME"] = test_name
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old = runner.setup_databases()
    server = None
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        fixtures.ReservationTests.setUpTestData()
        fixture = fixtures.ReservationTests()
        fixture.dish.status = "INACTIVE"
        fixture.dish.save()
        for data in public_menu:
            category, _ = Category.objects.get_or_create(name=data.pop("category__name"))
            unit, _ = Unit.objects.get_or_create(name=data.pop("unit__name"))
            Dish.objects.create(**data, category=category, unit=unit)
        call_command("seed_combos", verbosity=0)
        call_command("seed_menu_english", verbosity=0)
        combo = Combo.objects.get(code="CB_HENHO")
        extra = Dish.objects.get(name="Trà chanh")
        expected_total = combo.price + extra.price
        original_price = combo.price
        application = get_wsgi_application()
        clock = {"now": fixture.now}
        manager_client = Client()
        manager_client.force_login(fixture.manager)
        manager_cookie = manager_client.cookies[settings.SESSION_COOKIE_NAME].value
        config = {"combo": combo.pk, "combo_name": combo.name,"combo_name_en":combo.name_en, "combo_price": int(combo.price), "extra": extra.pk,
            "extra_name_en":extra.name_en,"extra_category":extra.category_id,
            "total": int(expected_total), "arrival": timezone.localtime(fixture.arrival).strftime("%Y-%m-%dT%H:%M")}

        def respond(start, data, content_type="text/html; charset=utf-8", status="200 OK", headers=None):
            data = data.encode() if isinstance(data, str) else data
            start(status, [("Content-Type", content_type), ("Content-Length", str(len(data))), *(headers or [])])
            return [data]

        def app(environ, start):
            path = environ.get("PATH_INFO", "")
            query = parse_qs(environ.get("QUERY_STRING", ""))
            if path == "/__storefront_test__/config":
                return respond(start, json.dumps(config), "application/json")
            if path == "/__storefront_test__/login":
                return respond(start, "", status="302 Found", headers=[("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={manager_cookie}; Path=/; HttpOnly; SameSite=Lax"), ("Location", reverse("menu:combo_list"))])
            if path == "/__storefront_test__/bank":
                payment = DepositPayment.objects.get(txn_ref=query["vnp_TxnRef"][0])
                connections.close_all()
                return respond(start, f'<h1>LOCAL bank fixture</h1><form method="post" action="/__storefront_test__/confirm?ref={payment.txn_ref}"><button id="confirm-fixture">Confirm signed fixture payment</button></form>')
            if path == "/__storefront_test__/confirm" and environ["REQUEST_METHOD"] == "POST":
                payment = DepositPayment.objects.select_related("reservation").get(txn_ref=query["ref"][0])
                response = Client().get(reverse("online_reservations:ipn"), fixture.callback(payment))
                assert response.json()["RspCode"] == "00"
                target = reverse("online_reservations:detail", args=[payment.reservation.access_token])
                connections.close_all()
                return respond(start, "", status="302 Found", headers=[("Location", target)])
            if path == "/__storefront_test__/arrival":
                clock["now"] = fixture.arrival
                return respond(start, reverse("online_reservations:manage_detail", args=[Reservation.objects.get().pk]))
            if path.startswith("/static/"):
                target = finders.find(path.removeprefix("/static/"))
                if target and Path(target).is_file():
                    return respond(start, Path(target).read_bytes(), mimetypes.guess_type(target)[0] or "application/octet-stream")
            result = list(application(environ, start))
            connections.close_all()
            return result

        server = make_server("127.0.0.1", 0, app, server_class=Server, handler_class=Quiet)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        language_run = "--language" in sys.argv
        output = ROOT / ("artifacts/homepage-preview/language" if language_run else "artifacts/homepage-preview/combos")
        output.mkdir(parents=True, exist_ok=True)
        with patch("django.utils.timezone.now", side_effect=lambda: clock["now"]), override_settings(VNPAY_PAYMENT_URL=base+"/__storefront_test__/bank"), tempfile.TemporaryDirectory(prefix="cq-combo-ui-", ignore_cleanup_errors=True) as profile:
            driver="scripts/run_customer_language_chrome.cjs" if language_run else "scripts/run_storefront_combos_chrome.cjs"
            result = subprocess.run(["node", str(ROOT/driver), base, profile, str(output)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150)
            print(result.stdout or result.stderr)
            if result.returncode:
                raise RuntimeError("Storefront browser checks failed")
        row = Reservation.objects.get()
        assert row.subtotal == expected_total
        assert row.combo_snapshot[0]["unit_price"] == str(original_price)
        assert Order.objects.get().total == expected_total
        assert DepositPayment.objects.filter(status="PAID").count() == 1
        assert Combo.objects.count() == 3
        print("Verified one booking, one deposit and preserved combo price through catalog edit/check-in. Disposable DB only.")
    finally:
        if server:
            server.shutdown(); server.server_close()
        connections.close_all()
        with connection._nodb_cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()", [test_name])
        runner.teardown_databases(old)


if __name__ == "__main__":
    with override_settings(DEBUG=True, ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"], SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, VNPAY_TMN_CODE="TESTCODE", VNPAY_HASH_SECRET="test-only-deposit-secret"):
        main()
