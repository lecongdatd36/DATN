"""Verify workforce forms and kiosk rejection using an isolated PostgreSQL DB.

Chrome receives its own temporary profile and fake camera. No employee biometric
data or real business database is used. Test session endpoints exist only here.
"""
from datetime import timedelta
from contextlib import ExitStack
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from uuid import uuid4
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer
from socketserver import ThreadingMixIn

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "QLNH.test_settings")
import django
django.setup()

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db import connection, connections
from django.test import Client, override_settings
from django.test.runner import DiscoverRunner
from django.utils import timezone
from apps.workforce.models import Attendance, FaceChallenge, FaceProfile, KioskDevice, WorkSchedule, WorkShift
from apps.workforce.tests.test_workforce import fixtures, vector


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main():
    connection.settings_dict["TEST"]["NAME"] = "test_qlnh_attendance_ui_"+uuid4().hex
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old = runner.setup_databases()
    server = None
    try:
        connection.settings_dict["CONN_MAX_AGE"] = 0
        manager, user, employee, other, shift, device = fixtures()
        from apps.orders.models import Order, Invoice
        from apps.inventory.models import Ingredient
        for index, amount in enumerate((125000,235000)):
            order=Order.objects.create(order_code=f'UI{index+1:03}',status='COMPLETED',total_amount=amount)
            Invoice.objects.create(order=order,invoice_code=f'UI{index+1:03}',status='PAID',total=amount,
                closed_at=timezone.now()-timedelta(days=index))
        Ingredient.objects.create(code='UIRICE',name='Gạo thử giao diện',unit='kg',stock_quantity=1,low_stock_threshold=2)
        from apps.seating.models import Area, DiningTable
        area=Area.objects.create(name='Khu kiểm tra giao diện')
        for seats in (2,4,6):DiningTable.objects.create(code=f'UI{seats}',name=f'Bàn {seats} chỗ',capacity=seats,area=area)
        device.delete()
        client = Client()
        client.force_login(manager)
        session = client.cookies[settings.SESSION_COOKIE_NAME].value
        config = {"employee": employee.pk, "day": str(timezone.localdate()+timedelta(days=1)),
            "booking_start":(timezone.localtime()+timedelta(days=1)).replace(hour=18,minute=0).strftime('%Y-%m-%dT%H:%M')}
        face_mode = {"mode": "camera", "counter": 0}
        real_now = timezone.now
        clock = {"seconds": 0}
        application = get_wsgi_application()

        def respond(start, data, content_type="text/html; charset=utf-8", headers=None, status="200 OK"):
            data = data.encode("utf-8") if isinstance(data, str) else data
            start(status, [("Content-Type", content_type), ("Content-Length", str(len(data))), *(headers or [])])
            return [data]

        def app(environ, start):
            path = environ.get("PATH_INFO", "")
            if path == "/__workforce_test__/manager":
                return respond(start, "", headers=[("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={session}; Path=/; HttpOnly; SameSite=Lax"), ("Location", "/cham-cong/ca-lam/")], status="302 Found")
            if path == "/__workforce_test__/config":
                return respond(start, json.dumps(config), "application/json")
            if path == "/__workforce_test__/advance" and environ.get("REQUEST_METHOD") == "POST":
                clock["seconds"] += 120
                return respond(start, "OK")
            if path.startswith("/__workforce_test__/face-mode/") and environ.get("REQUEST_METHOD") == "POST":
                mode = path.rsplit("/", 1)[-1]
                if mode not in ("camera", "preview-known", "known", "known-clock"):
                    return respond(start, "Invalid mode", status="400 Bad Request")
                # Synthetic vector fixture, never a real employee's biometric.
                if mode != "camera":
                    FaceProfile.objects.get_or_create(employee=other, defaults={"embeddings":[vector()], "consent_at":timezone.now()})
                if mode == "known-clock":
                    now = timezone.now()
                    WorkSchedule.objects.create(employee=other, shift=shift, shift_name="Ca kiểm thử hiện tại", work_date=timezone.localdate(),
                        starts_at=now-timedelta(minutes=10), ends_at=now+timedelta(hours=2), status="PUBLISHED", created_by=manager)
                face_mode["mode"] = mode
                connections.close_all()
                return respond(start, "OK")
            if path in ("/cham-cong/diem-cham-cong/api/", "/cham-cong/khuon-mat/kiem-thu/api/") and face_mode["mode"] != "camera":
                def fake_extract(encoded):
                    challenge = FaceChallenge.objects.filter(device__isnull=True, used_at__isnull=True).order_by("-created_at").first()
                    yaw = .23
                    if challenge and challenge.step == 1:
                        yaw += -.14 if challenge.poses[1] == "LEFT" else .14
                    face_mode["counter"] += 1
                    return {"vector":vector(), "yaw":yaw, "hash":f"browser-fixture-{face_mode['counter']}"}
                # Only inference is replaced; real CSRF, sessions, face matching,
                # challenge validation, shift checks and database writes run.
                with patch("apps.workforce.face.extract_frame", side_effect=fake_extract):
                    return application(environ, start)
            if path.startswith("/static/"):
                root = (BASE / "static").resolve()
                target = (root / path.removeprefix("/static/")).resolve()
                if target.is_relative_to(root) and target.is_file():
                    return respond(start, target.read_bytes(), mimetypes.guess_type(target)[0] or "application/octet-stream")
                return respond(start, "", status="404 Not Found")
            return application(environ, start)

        server = make_server("127.0.0.1", 0, app, server_class=ThreadedServer, handler_class=QuietHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        output = BASE / "artifacts/attendance/browser"
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="qlnh-attendance-ui-", ignore_cleanup_errors=True) as profile, patch(
                "django.utils.timezone.now", side_effect=lambda:real_now()+timedelta(seconds=clock["seconds"])), ExitStack() as stack:
            if '--dashboard' in sys.argv:
                today=timezone.localdate()
                forecast={'ready':True,'is_demo':True,'is_stale':False,'last_update_failed':False,
                    'date_from':today,'date_to':today+timedelta(days=6),'trained_until':today-timedelta(days=1),
                    'published_at':timezone.now(),'mae':5.45,'baseline_mae':7.71,
                    'rows':[{'day':today+timedelta(days=i),'orders':30+2*i} for i in range(7)]}
                # Published-result-shaped fixture for UI only; never trains or
                # overwrites the real forecast artifacts.
                stack.enter_context(patch('apps.reports.forecast.get_order_forecast',return_value=forecast))
                stack.enter_context(patch('apps.reports.views.get_order_forecast',return_value=forecast))
            driver_args=["node", str(BASE / "scripts/run_attendance_chrome.cjs"), f"http://127.0.0.1:{server.server_port}", profile, str(output)]
            if '--dashboard' in sys.argv:
                driver_args.append('--dashboard')
            result = subprocess.run(driver_args,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=130,
                env={key:value for key,value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "COMSPEC"}})
            print(result.stdout or result.stderr)
            if result.returncode:
                raise RuntimeError("Attendance browser checks failed")
        if '--dashboard' in sys.argv:
            assert not Attendance.objects.exists()
            print('Dashboard-only visual checks; no attendance or face registration written. Disposable DB only.')
            return
        assert WorkShift.objects.filter(code="BROWSER").exists()
        assert WorkSchedule.objects.filter(employee=employee, status="PUBLISHED").count() == 1
        assert Attendance.objects.count() == 1, "Only the synthetic inference fixture may record a shift"
        attendance = Attendance.objects.get()
        assert attendance.schedule.employee_id == other.pk
        assert attendance.checked_in_at and attendance.checked_out_at
        assert FaceProfile.objects.count() == 1 and FaceProfile.objects.get().employee_id == other.pk, "No camera enrollment may pass; only the synthetic fixture exists"
        assert not KioskDevice.objects.exists(), "The shared point must not activate devices"
        print("Shared point, missing-shift explanation and IN/OUT ledger verified; successful inference uses a synthetic test fixture.")
    finally:
        if server:
            server.shutdown()
            server.server_close()
        connections.close_all()
        runner.teardown_databases(old)


if __name__ == "__main__":
    with override_settings(DEBUG=True, ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"], SECURE_SSL_REDIRECT=False,
                           SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False):
        main()
