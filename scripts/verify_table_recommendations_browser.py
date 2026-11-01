"""Verify real booking pages in local Chrome using a disposable PostgreSQL database."""
from datetime import timedelta
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlencode
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
from django.urls import reverse
from django.utils import timezone
from apps.bookings.models import Booking
from apps.bookings.tests.test_recommendations import TableRecommendationTests


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    connection.settings_dict["TEST"]["NAME"] = "test_qlnh_table_ui_" + uuid4().hex
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    server = None
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        TableRecommendationTests.setUpTestData()
        fixture = TableRecommendationTests
        client = Client()
        client.force_login(fixture.waiter)
        cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        params = {
            "starts_at": timezone.localtime(fixture.start).strftime("%Y-%m-%dT%H:%M"),
            "party_size": 3, "duration_minutes": 120,
        }
        routes = {
            "staff": reverse("bookings:availability") + "?" + urlencode(params),
            "public": reverse("customer_reservations:check") + "?" + urlencode(params),
            "empty": reverse("customer_reservations:check") + "?" + urlencode({**params, "party_size": 100}),
        }
        application = get_wsgi_application()

        def wsgi(environ, start_response):
            path = environ.get("PATH_INFO", "")
            if path.startswith("/__table_test__/"):
                name = path.rstrip("/").split("/")[-1]
                if name in routes:
                    start_response("302 Found", [("Location", routes[name]),
                        ("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}; Path=/; HttpOnly; SameSite=Lax")])
                    return [b""]
            if path.startswith("/static/"):
                static_root = (BASE / "static").resolve()
                target = (static_root / path.removeprefix("/static/")).resolve()
                if target.is_relative_to(static_root) and target.is_file():
                    start_response("200 OK", [("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")])
                    return [target.read_bytes()]
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"Not found"]
            try:
                return application(environ, start_response)
            finally:
                connections.close_all()

        server = make_server("127.0.0.1", 0, wsgi, server_class=ThreadedServer, handler_class=QuietHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        output = BASE / "artifacts/ai/table-recommendations/browser"
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qlnh-table-ui-", ignore_cleanup_errors=True) as profile:
            result = subprocess.run([
                "node", str(BASE / "scripts/run_table_recommendations_chrome.cjs"),
                f"http://127.0.0.1:{server.server_port}", profile, str(output),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                env={key: value for key, value in os.environ.items() if key.upper() in {
                    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC",
                }})
            print(result.stdout or result.stderr)
            if result.returncode != 0:
                raise RuntimeError("Table recommendation browser checks failed")
        assert Booking.objects.count() == 0, "Preview and navigation must not create any booking"
        print("Browser checks passed; no booking created. Captures: artifacts/ai/table-recommendations/browser")
    finally:
        if server:
            server.shutdown()
            server.server_close()
        connections.close_all()
        runner.teardown_databases(old_config)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    with override_settings(DEBUG=True, ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"],
                          SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False):
        main()
