"""Use disposable PostgreSQL data for a Sandbox API smoke test or browser QA.

Default: sends create/query to the official Sandbox only, never attempts payment.
--browser: uses a mocked HTTP transport and real application callback/settlement.
"""
import json
import mimetypes
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from uuid import uuid4
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.settings")
import django
django.setup()
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from django.urls import reverse
from apps.orders import zalopay, zalopay_services
from apps.orders.models import Invoice, ZaloPayTransaction
from apps.orders.tests import test_integrated_flow as fixtures
from apps.orders.tests.test_zalopay import SANDBOX, receipt, response


class Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class Server(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def browser(order, actor):
    client = Client()
    client.force_login(actor)
    cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    application = get_wsgi_application()

    def app(environ, start):
        path = environ.get("PATH_INFO", "")
        def send(body, kind="text/html", status="200 OK", extra=None):
            data = body.encode() if isinstance(body, str) else body
            start(status, [("Content-Type", kind), ("Content-Length", str(len(data))), *(extra or [])])
            return [data]
        if path == "/__zalopay_test__/login":
            return send("", status="302 Found", extra=[("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Lax"),
                ("Location", reverse("sales:workspace")+f"?order={order.pk}")])
        if path == "/__zalopay_test__/config":
            return send(json.dumps({"order": order.pk}), "application/json")
        if path == "/__zalopay_test__/confirm" and environ.get("REQUEST_METHOD") == "POST":
            row = ZaloPayTransaction.objects.get()
            payload = Client().post(reverse("zalopay:callback"), receipt(row), content_type="application/json").json()
            connections.close_all()
            return send(json.dumps(payload), "application/json")
        if path.startswith("/static/"):
            root = Path(settings.STATIC_ROOT).resolve()
            target = (root/path.removeprefix("/static/")).resolve()
            if target.is_relative_to(root) and target.is_file():
                return send(target.read_bytes(), mimetypes.guess_type(target)[0] or "application/octet-stream")
            return send("", status="404 Not Found")
        return application(environ, start)

    server = make_server("127.0.0.1", 0, app, server_class=Server, handler_class=Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="zalopay-ui-", ignore_cleanup_errors=True) as profile:
            output = BASE/"artifacts/zalopay/browser"
            output.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["node", str(BASE/"scripts/run_zalopay_chrome.cjs"), f"http://127.0.0.1:{server.server_port}",
                profile, str(output)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            print(result.stdout or result.stderr)
            if result.returncode:
                raise RuntimeError("ZaloPay browser verification failed")
        assert ZaloPayTransaction.objects.get().status == "PAID" and Invoice.objects.count() == 1
    finally:
        server.shutdown()
        server.server_close()


def run():
    assert settings.DATABASES["default"].get("HOST") in ("localhost", "127.0.0.1", "::1", ""), "Disposable tests require local PostgreSQL"
    connection.settings_dict["TEST"]["NAME"] = "test_qlnh_zalopay_"+uuid4().hex
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old = runner.setup_databases()
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        fixtures.IntegratedRestaurantFlowTests.setUpTestData()
        fixture = fixtures.IntegratedRestaurantFlowTests()
        order = fixture.ready_order_for_payment()
        if "--browser" in sys.argv:
            def gateway(operation_url, **kwargs):
                return response({"return_code": 3, "is_processing": True} if operation_url.endswith("/query") else {"return_code": 1})
            with override_settings(**SANDBOX), patch("apps.orders.zalopay.httpx.post", side_effect=gateway):
                browser(order, fixture.users["CASHIER"])
        else:
            zalopay.configuration()
            row = zalopay_services.create_order_payment(actor=fixture.users["CASHIER"], order_id=order.pk,
                base_url=settings.PUBLIC_BASE_URL or "https://localhost")
            report = {"sandbox_only": True, "disposable_database": True, "create": row.response_data,
                "checkout_url_received": bool(row.order_url), "status": row.status}
            if row.status == "PENDING":
                row = zalopay_services.query_transaction(row.token)
                report.update(query=row.response_data, status=row.status)
            assert not Invoice.objects.exists(), "Smoke test must never complete a payment"
            report["invoice_created"] = False
            output = BASE/"artifacts/zalopay"
            output.mkdir(parents=True, exist_ok=True)
            (output/"sandbox-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report))
            if report["create"].get("return_code") != 1 or not report["checkout_url_received"]:
                raise RuntimeError("Sandbox did not provide a checkout URL; inspect sanitized return codes")
    finally:
        connections.close_all()
        test_name = connection.settings_dict["NAME"]
        assert re.fullmatch(r"test_qlnh_zalopay_[a-f0-9]{32}", test_name)
        with connection._nodb_cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()", [test_name])
        runner.teardown_databases(old)


if __name__ == "__main__":
    with override_settings(DEBUG=True, ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"],
            SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, SECURE_SSL_REDIRECT=False,
            STORAGES={**settings.STORAGES, "staticfiles":{"BACKEND":"django.contrib.staticfiles.storage.StaticFilesStorage"}}):
        run()
