"""Run the real mobile UI against a disposable PostgreSQL DB and local Chrome.

The session/fixture endpoints below only exist in this temporary WSGI wrapper;
they are never registered in the application URL configuration.
"""
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
sys.stdout.reconfigure(encoding="utf-8")
import tempfile
import threading
from uuid import uuid4
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.test_settings")
import django
django.setup()

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from apps.orders import services
from apps.orders.models import Invoice, Order, OrderItem, Payment, PromotionCode, QRServiceRequest
from apps.orders.tests.test_mobile import MobileStaffTests
from django.utils import timezone
from django.urls import reverse
from apps.menu.models import Dish
from apps.seating.models import DiningTableQRToken
from datetime import timedelta


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    connection.settings_dict["TEST"]["NAME"] = "test_qlnh_mobile_ui_" + uuid4().hex
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    server = None
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        MobileStaffTests.setUpTestData()
        fixture = MobileStaffTests()
        fixture.order = fixture.ready_to_pay()
        suggestion = Dish.objects.create(code="MB02", name="Trà chanh gợi ý", category=fixture.category, unit=fixture.unit, price=15000)
        for index in range(10):
            Dish.objects.create(code=f"SC{index:02}", name=f"ZZ scroll {index:02}", category=fixture.category, unit=fixture.unit, price=50000)
        qr_token = DiningTableQRToken.objects.create(table=fixture.table)
        model_path = BASE / "artifacts/staff-mobile/recommendation_browser_model.json"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(json.dumps({
            "schema_version": 1, "algorithm": "Apriori", "data_source": "application_export",
            "catalog": [{"dish_id": "train-main", "dish_code": fixture.dish.code, "dish_name": fixture.dish.name},
                        {"dish_id": "train-extra", "dish_code": suggestion.code, "dish_name": suggestion.name}],
            "rules": [{"antecedents": ["train-main"], "consequents": ["train-extra"], "support": 0.4, "confidence": 0.8, "lift": 1.6}],
        }, ensure_ascii=False), encoding="utf-8")
        now = timezone.now()
        PromotionCode.objects.create(code="MOBILE10", name="UI test discount", discount_type="PERCENT", value=10, minimum_order=0,
                                     starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1))
        sessions = {}
        for role in ("CASHIER", "WAITER"):
            client = Client()
            client.force_login(fixture.users[role])
            sessions[role.lower()] = client.cookies[settings.SESSION_COOKIE_NAME].value
        notification_test = {}
        application = get_wsgi_application()

        def respond(start_response, body, content_type="text/html; charset=utf-8", role=None, status="200 OK"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))]
            if role:
                headers.append(("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={sessions[role]}; Path=/; HttpOnly; SameSite=Lax"))
            start_response(status, headers)
            return [body]

        def wsgi(environ, start_response):
            path = environ.get("PATH_INFO", "")
            if path == "/favicon.ico":
                return respond(start_response, "", status="204 No Content")
            if path == "/__mobile_test__/":
                return respond(start_response, (BASE / "scripts/staff_mobile_browser_harness.html").read_text(encoding="utf-8").replace("__AI_QR_URL__", reverse("customer_portal:qr_table", args=[qr_token.token])), role="cashier")
            if path.startswith("/__mobile_test__/role/"):
                role = path.rstrip("/").split("/")[-1]
                return respond(start_response, "OK", role=role if role in sessions else None)
            if path in ("/__mobile_test__/notifications/add/", "/__mobile_test__/notifications/clear/") and environ.get("REQUEST_METHOD") == "POST":
                try:
                    if path.endswith("/add/"):
                        request = QRServiceRequest.objects.create(
                            order=fixture.order, table=fixture.table,
                            request_type=QRServiceRequest.RequestType.WATER,
                        )
                        notification_test["id"] = request.pk
                    else:
                        QRServiceRequest.objects.filter(pk=notification_test.get("id")).update(status=QRServiceRequest.Status.COMPLETED)
                    return respond(start_response, "OK")
                finally:
                    connections.close_all()
            if path == "/__mobile_test__/pos/clear-probe/" and environ.get("REQUEST_METHOD") == "POST":
                try:
                    order = Order.objects.get(pk=fixture.order.pk)
                    item = order.items.get(dish__code="SC04", status=OrderItem.Status.SERVED)
                    services.transition_item(actor=fixture.users["MANAGER"], order_id=order.pk, item_id=item.pk,
                                             expected_revision=order.revision, target=OrderItem.Status.CANCELLED,
                                             reason="Restore desktop browser test fixture")
                    return respond(start_response, "OK")
                finally:
                    connections.close_all()
            if path == "/__mobile_test__/ready/":
                try:
                    order = Order.objects.order_by("-pk").first()
                    for item in order.items.filter(status=OrderItem.Status.PENDING):
                        for target in (OrderItem.Status.COOKING, OrderItem.Status.READY):
                            order.refresh_from_db()
                            services.transition_item(actor=fixture.users["KITCHEN"], order_id=order.pk, item_id=item.pk,
                                                     expected_revision=order.revision, target=target)
                    return respond(start_response, "OK")
                finally:
                    connections.close_all()
            if path.startswith("/__mobile_test__/capture/"):
                page = path.rstrip("/").split("/")[-1]
                order = Order.objects.order_by("-pk").first()
                invoice = Invoice.objects.filter(status=Invoice.Status.PAID).first()
                params = "page=personal" if page == "notifications" else f"page={page}"
                if page in ("order", "checkout", "menu"):
                    params += f"&order={order.pk}"
                if page == "receipt":
                    params += f"&invoice={invoice.pk}"
                elif page == "open":
                    params += f"&table={fixture.table.pk}"
                target_url = reverse("customer_portal:qr_table", args=[qr_token.token]) if page == "qr" else "/sales/mobile/?" + params
                html = f'<!doctype html><meta charset="utf-8"><body style="margin:0;background:#e5ece6;display:grid;justify-content:center;padding:25px 0"><iframe title="Mobile thực tế" src="{target_url}" width="390" height="844" style="border:6px solid #204636;border-radius:18px;background:white"></iframe>'
                connections.close_all()
                return respond(start_response, html, role="cashier")
            if path.startswith("/static/"):
                static_root = (BASE / "static").resolve()
                target = (static_root / path.removeprefix("/static/")).resolve()
                if target.is_relative_to(static_root) and target.is_file():
                    return respond(start_response, target.read_bytes(), mimetypes.guess_type(target)[0] or "application/octet-stream")
                return respond(start_response, "Not found", status="404 Not Found")
            return application(environ, start_response)

        server = make_server("127.0.0.1", 0, wsgi, server_class=ThreadedServer, handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        output = BASE / "artifacts/staff-mobile"
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qlnh-mobile-ui-", ignore_cleanup_errors=True) as profile:
            result = subprocess.run(["node", str(BASE / "scripts/run_mobile_chrome.cjs"), url, profile, str(output)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=140,
                                    env={key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC"}})
            report = result.stdout or result.stderr
            print(report)
            if result.returncode != 0 or "LIVE CHECKS PASSED" not in report:
                raise RuntimeError("Live mobile checks failed")
            assert Payment.objects.count() == 1, "UI must record exactly one payment"
            assert Invoice.objects.filter(status=Invoice.Status.PAID).count() == 1
            newest = Order.objects.order_by("-pk").first()
            assert newest.items.count() == 1, "Rapid menu click must not duplicate dishes"
            assert newest.status == Order.Status.PAYMENT_REQUESTED
        print("Live mobile UI and ledger checks passed; captures: artifacts/staff-mobile")
    finally:
        if server:
            server.shutdown()
            server.server_close()
        connections.close_all()
        runner.teardown_databases(old_config)


if __name__ == "__main__":
    with override_settings(DEBUG=True, ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"],
                           SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
                           X_FRAME_OPTIONS="SAMEORIGIN",
                           APRIORI_MODEL_PATH=BASE / "artifacts/staff-mobile/recommendation_browser_model.json"):
        main()
